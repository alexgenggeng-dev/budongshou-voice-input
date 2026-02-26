import os
import io
import wave
import pyaudio
import base64
import requests
import pyperclip
import time
import threading
import subprocess
from pynput import keyboard

# ── Audio constants ─────────────────────────────────────────────────────────
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # 16kHz — standard for voice, good quality/size balance
CHUNK = 1024

# ── System prompt (the "brain") ───────────────────────────────────────────────
SYSTEM_PROMPT = """你是一个专为"高效表达"设计的语义重构专家，同时也是一个语音识别纠错引擎。你将直接听到用户的原始语音，你的任务有两个：第一，纠正语音识别中的错误；第二，将内容整理为简洁、可读的文本。

请严格遵守以下规则：

1. 语音识别纠错（优先级最高）：
   - 根据上下文语义，识别并纠正同音字错误（如"的地得"混用、人名/专有名词识别错）。
   - 如果某个词在上下文中明显不合理，判断它是识别错误，替换为语义最合理的词。
   - 修正明显的断句错误，补全被吞掉的字（如句尾的"了"、"吗"、"吧"）。

2. 严格忠实原意：
   - 必须完全基于你听到的语音内容，绝对不能加入用户没说过的观点或数据。
   - 只能删减、去重、调整语序，严禁扩写或凭空捏造。

3. 精炼输出（宁少勿多）：
   - 彻底删除"那个"、"呃"、"然后"、"就是说"、"对对对"等所有口头禅。
   - 合并语义重复的表达，只保留最精炼的一次表述。
   - 保留"我觉得"、"我认为"等主观表达词。
   - 保留英文原词，不要翻译；中英文/数字之间加一个半角空格。
   - 必须输出简体中文，严禁繁体字。

4. 排版结构：
   - 用自然段落，每段聚焦一个意思。
   - 除非说话人明确说了"第一、第二"或"首先、其次、最后"，否则不要加小标题。
   - 使用 Markdown 格式。

只输出整理后的内容，不要任何解释、前言或总结。"""


class VoiceInputBot:
    def __init__(self):
        self.is_recording = False
        self.is_processing = False  # Lock to prevent concurrent API requests
        self.audio_frames = []
        self.pressed_keys = set()
        self.hotkey_held = False
        self.source_app_bundle = None

        self.p = pyaudio.PyAudio()
        self.stream = None

    # ── macOS helpers ─────────────────────────────────────────────────────────

    def notify(self, message, title="🎤 不动手"):
        """Show a macOS notification."""
        try:
            subprocess.run(
                ['osascript', '-e', f'display notification "{message}" with title "{title}"'],
                timeout=3, capture_output=True
            )
        except Exception:
            pass

    def get_frontmost_bundle(self):
        """Get bundle ID of the currently frontmost app."""
        script = '''
        tell application "System Events"
            set frontProc to first process whose frontmost is true
            return bundle identifier of frontProc
        end tell
        '''
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=4
            )
            bundle = result.stdout.strip()
            return bundle if bundle else None
        except Exception as e:
            print(f"⚠️  Could not get frontmost bundle: {e}")
            return None

    def activate_by_bundle(self, bundle_id):
        """Switch focus back to the source app."""
        if not bundle_id:
            return
        try:
            subprocess.run(['open', '-b', bundle_id], timeout=3)
            time.sleep(0.7)  # Let the OS settle focus
        except Exception as e:
            print(f"⚠️  Could not activate '{bundle_id}': {e}")

    def paste_via_osascript(self):
        """Simulate Cmd+V using AppleScript keystroke.

        System Events requires Accessibility permission for Terminal.
        Grant it in: System Settings → Privacy & Security → Accessibility → add Terminal/iTerm2.
        """
        try:
            result = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to keystroke "v" using command down'],
                timeout=3, capture_output=True, text=True
            )
            if result.returncode != 0:
                # Fallback: pynput keystroke
                print("⚠️  osascript paste failed, trying pynput fallback…")
                k = keyboard.Controller()
                k.press(keyboard.Key.cmd)
                k.press('v')
                k.release('v')
                k.release(keyboard.Key.cmd)
        except Exception as e:
            print(f"⚠️  Paste error: {e}")

    # ── API ───────────────────────────────────────────────────────────────────

    def get_api_key(self):
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    # ── Audio ─────────────────────────────────────────────────────────────────

    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.is_recording:
            self.audio_frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def start_recording(self):
        self.source_app_bundle = self.get_frontmost_bundle()
        print(f"\n🎤 [Recording Started] Source app: {self.source_app_bundle}")
        self.notify("录音中… 再按热键停止，ESC 取消", title="🎤 不动手")
        self.is_recording = True
        self.audio_frames = []
        try:
            self.stream = self.p.open(
                format=FORMAT, channels=CHANNELS, rate=RATE,
                input=True, frames_per_buffer=CHUNK,
                stream_callback=self.audio_callback
            )
            self.stream.start_stream()
        except Exception as e:
            print(f"❌ Failed to open mic: {e}")
            self.is_recording = False
            self.notify("❌ 麦克风打开失败")

    def stop_recording(self, cancel=False):
        self.is_recording = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if cancel:
            print("🚫 [Cancelled] Recording discarded.")
            self.notify("已取消录音", title="🚫 不动手")
            self.audio_frames = []
        else:
            print("⏹️  [Stop Recording] Processing audio...")
            self.notify("处理中…", title="⚙️ 不动手")
            threading.Thread(target=self.process_audio, daemon=True).start()

    # ── Core processing ───────────────────────────────────────────────────────

    def process_audio(self):
        if not self.audio_frames:
            print("⚠️  No audio data recorded.")
            self.notify("未检测到音频", title="⚠️ 不动手")
            return

        self.is_processing = True  # lock!

        try:
            # Step 1: Build WAV in memory
            print("⚙️  Encoding audio (WAV)…")
            wav_buffer = io.BytesIO()
            wf = wave.open(wav_buffer, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(self.audio_frames))
            wf.close()
            wav_bytes = wav_buffer.getvalue()
            wav_size_kb = len(wav_bytes) / 1024
    
            # Step 2: Compress WAV → MP3 via ffmpeg (≈10× smaller)
            mime_type = "audio/wav"
            audio_bytes = wav_bytes
            try:
                result = subprocess.run(
                    [
                        'ffmpeg', '-y',
                        '-f', 'wav', '-i', 'pipe:0',      # stdin = WAV
                        '-codec:a', 'libmp3lame',
                        '-q:a', '5',                       # VBR quality 5 (~130kbps)
                        '-f', 'mp3', 'pipe:1'              # stdout = MP3
                    ],
                    input=wav_bytes,
                    capture_output=True,
                    timeout=15
                )
                if result.returncode == 0 and result.stdout:
                    audio_bytes = result.stdout
                    mime_type = "audio/mp3"
                    mp3_size_kb = len(audio_bytes) / 1024
                    print(f"🗜️  Compressed: WAV {wav_size_kb:.0f} KB → MP3 {mp3_size_kb:.0f} KB ({mp3_size_kb/wav_size_kb*100:.0f}%)")
                else:
                    print(f"⚠️  ffmpeg failed (rc={result.returncode}), using WAV fallback")
            except Exception as e:
                print(f"⚠️  ffmpeg error: {e}, using WAV fallback")
    
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    
            api_key = self.get_api_key()
            if not api_key:
                print("❌ GEMINI_API_KEY not set!")
                self.notify("❌ 未设置 GEMINI_API_KEY", title="不动手")
                return
    
            print("🌐 Sending audio to Gemini (3-flash-preview)…")
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-3-flash-preview:generateContent?key={api_key}"
            )
    
            payload = {
                "contents": [{
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
                        {"text": "请处理这段语音。"}
                    ]
                }],
                "systemInstruction": {
                    "parts": [{"text": SYSTEM_PROMPT}]
                },
                "generationConfig": {
                    "temperature": 0.2
                }
            }
    
            try:
                resp = requests.post(url, json=payload, timeout=120)
                if resp.status_code != 200:
                    print(f"❌ API Error ({resp.status_code}): {resp.text[:300]}")
                    self.notify(f"❌ API 错误 ({resp.status_code})", title="不动手")
                    return
    
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        if text:
                            self.paste_text(text)
                            return
    
                block_reason = data.get("promptFeedback", {}).get("blockReason")
                if block_reason:
                    print(f"❌ Blocked: {block_reason}")
                    self.notify("❌ 被安全过滤屏蔽", title="不动手")
                else:
                    print("❌ No text in response.")
                    self.notify("❌ 模型未返回文本", title="不动手")

            except requests.exceptions.Timeout:
                print("❌ Request timed out.")
                self.notify("❌ 请求超时，请重试", title="不动手")
            except Exception as e:
                print(f"❌ Request Error: {e}")
                self.notify(f"❌ 请求失败: {str(e)[:40]}", title="不动手")
        finally:
            self.is_processing = False  # Ensure unlock!

    def paste_text(self, text):
        print(f"✨ Result:\n{'─'*40}\n{text}\n{'─'*40}")

        # 1. Copy to clipboard first (always succeeds)
        pyperclip.copy(text)
        time.sleep(0.15)

        # 2. Restore focus to the original app
        if self.source_app_bundle:
            print(f"🔄 Restoring focus to: {self.source_app_bundle}")
            self.activate_by_bundle(self.source_app_bundle)

        # 3. Simulate Cmd+V via osascript (works without Accessibility permission for pynput)
        #    Note: System Events still needs Accessibility.  If it also fails, user can Cmd+V manually.
        self.paste_via_osascript()
        print("✅ Paste keystroke sent!")
        self.notify(
            f"✅ 已粘贴：{text[:30]}{'…' if len(text) > 30 else ''}",
            title="不动手"
        )

    # ── Hotkey listener ───────────────────────────────────────────────────────

    def on_press(self, key):
        self.pressed_keys.add(key)

        # Toggle: Right Cmd + Right Option
        if keyboard.Key.cmd_r in self.pressed_keys and keyboard.Key.alt_r in self.pressed_keys:
            if not self.hotkey_held:
                self.hotkey_held = True
                if not self.is_recording:
                    self.start_recording()
                else:
                    self.stop_recording(cancel=False)

        # Cancel: ESC
        if key == keyboard.Key.esc and self.is_recording:
            self.stop_recording(cancel=True)

    def on_release(self, key):
        self.pressed_keys.discard(key)
        if keyboard.Key.cmd_r not in self.pressed_keys or keyboard.Key.alt_r not in self.pressed_keys:
            self.hotkey_held = False

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        print("🤖 '不动手' Voice Input — Ready")
        print("=" * 45)
        print("热键    : 右 ⌘ + 右 ⌥  →  开始 / 停止录音")
        print("取消    : 录音中按 ESC")
        print("反馈    : 右上角系统通知")
        print("=" * 45)
        print("Listening for hotkeys…\n")

        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nExiting…")
                self.p.terminate()


if __name__ == '__main__':
    bot = VoiceInputBot()
    bot.run()
