# 🎙️ 不动手 (Typeless) — AI Voice Input Tool

> Speak naturally, get clean structured text. Powered by Google Gemini.

"不动手" is a global voice input tool for macOS. It records audio via a system-wide hotkey, sends raw audio directly to a Gemini multimodal LLM (bypassing traditional STT), and automatically pastes the refined text into your active application.

## ✨ Features

- **Direct Audio → LLM**: No Whisper, no intermediate STT. Raw audio goes straight to Gemini for native understanding of pacing, tone, and mixed languages (Chinese + English).
- **Smart Text Refinement**: Removes filler words, fixes recognition errors (homophones, misheard words), and outputs clean Markdown paragraphs.
- **Global Hotkey**: `Right ⌘ + Right ⌥` to start/stop recording from anywhere.
- **Auto-Paste**: Automatically pastes refined text into your current cursor position.
- **Audio Compression**: Compresses audio ~10x via ffmpeg before upload.
- **Anti-Spam Lock**: Built-in concurrency protection prevents overlapping API requests.

## 🛠 Prerequisites

| Requirement | Install |
|-------------|---------|
| Python 3.9+ | Pre-installed on macOS |
| FFmpeg | `brew install ffmpeg` |
| Gemini API Key | Free at [aistudio.google.com](https://aistudio.google.com/app/apikey) |

## 🚀 Quick Start (Standalone)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install ffmpeg
brew install ffmpeg

# 3. Set your API key
export GEMINI_API_KEY="your_api_key_here"

# 4. Run
python3 scripts/budongshou.py
```

## 🤖 Use as an Antigravity / Claude Skill

If you use [Antigravity](https://antigravity.dev) or Claude Code, you can install this as a Skill so the Agent can start it for you:

1. Copy the entire `voice-input-budongshou` folder into your project's `.claude/skills/` directory:
   ```
   your-project/
   └── .claude/skills/
       └── voice-input-budongshou/   ← copy this whole folder here
           ├── SKILL.md
           ├── README.md
           ├── requirements.txt
           └── scripts/
               └── budongshou.py
   ```
2. Make sure your `GEMINI_API_KEY` is set in your environment.
3. Tell the Agent: **"启动不动手"** — it will start the voice input service for you.

## 🎮 Hotkeys

| Action | Key |
|--------|-----|
| Start / Stop recording | `Right ⌘ + Right ⌥` |
| Cancel recording | `ESC` |

## ⚠️ macOS Permissions

Grant **Accessibility** permission to your terminal app:
**System Settings → Privacy & Security → Accessibility → add Terminal.app or iTerm2.app**

## 🔧 Configuration

### Changing the Gemini Model

Edit the `url` variable in `process_audio()` inside `budongshou.py`. Available models:

| Model | Speed | Notes |
|-------|-------|-------|
| `gemini-2.5-flash` | ⚡ Fastest | Recommended, production-grade |
| `gemini-2.0-flash` | ⚡ Fast | Stable, high quota |
| `gemini-3-flash-preview` | 🐢 Slower | Latest, most capable, preview |

### Customizing the Prompt

Edit the `SYSTEM_PROMPT` variable at the top of `budongshou.py`. By default it fixes recognition errors, removes filler words, preserves mixed English/Chinese, and outputs clean Markdown.

## 📄 License

MIT License
