<div align="center">

# Türkçe Sesli Yazma — Turkish Voice Typing

### Speak, and it types. Your voice never leaves your computer.

**A 100% offline, 100% open-source Turkish dictation tool for Windows 11.**
<br>
Press `Win + H`, speak, and the text is typed wherever your cursor is. No cloud, no account, no telemetry.

<br>

![Platform](https://img.shields.io/badge/Windows-11-0078D4?style=for-the-badge&logo=windows11&logoColor=white)
![Offline](https://img.shields.io/badge/Internet-Not%20required-e53935?style=for-the-badge&logo=shield&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-121212?style=for-the-badge)

</div>

---

## The whole point: your voice stays with you

Windows' own voice typing (`Win + H`), your phone keyboard, browser extensions — almost all of them **send your voice to a server**, transcribe it there, and send the text back. Every sentence you say passes through someone else's computer.

**This project does not work that way.**

| | Cloud-based dictation | **Türkçe Sesli Yazma** |
|---|:---:|:---:|
| Where is the audio processed? | On a remote server | **On your own CPU** |
| Internet required? | Every time | **No** (first install only) |
| Account / sign-in | Usually required | **None** |
| Telemetry / logging | Yes | **None** |
| Windows speech services | Used | **Never touched** |
| Source code | Closed | **Open, single file, readable** |

<div align="center">
<img src="assets/how-it-works.svg" alt="Audio is taken from the microphone, transcribed by the local Whisper model, and typed into the active window; no data goes to the internet." width="820" />
</div>

- **Speech recognition runs entirely locally** using OpenAI's open-source [Whisper](https://github.com/openai/whisper) model, executed on the CPU via [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- **The app never reaches the network.** After the model is downloaded, the code is locked down with `HF_HUB_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1`. Unplug the internet and it works exactly the same.
- **Audio is never written to disk.** The recording is kept in RAM only and discarded once it is transcribed.
- **It does not touch Windows.** It needs no services such as SpeechRuntime or ctfmon, and runs fine on systems hardened with tools like O&O ShutUp10.
- **It is verifiable.** The whole app is a single [`dictation.pyw`](dictation.pyw) file. You can read it line by line and see exactly what it does.

---

## Installation: one step

> Even a freshly installed Windows 11 works. **The installer sets up everything itself, including Python.**

### Option 1: One line (recommended)

`Win + R` -> `powershell` -> paste the following, press Enter:

```powershell
irm https://raw.githubusercontent.com/osmnabyram/TextToSpeech-Turkce/main/install.ps1 | iex
```

### Option 2: Download and double-click

1. Use **Code -> Download ZIP** at the top right and extract it to a folder.
2. Double-click **`install.bat`**.

### What does the installer do?

```
1. If Python 3.12 is missing, downloads it from python.org, verifies its signature, installs it silently
2. Creates an isolated virtual environment (venv) under %LOCALAPPDATA%\TurkceSesliYazma
3. Installs the required open-source packages
4. Downloads the Whisper model ONCE (~500 MB)   <- the last moment the internet is used
5. Adds a shortcut to the Startup folder so it launches at boot
6. Starts the app in the background
```

No administrator rights required. Once installation finishes, you never need the internet again.

---

## Usage

| Key | What it does |
|---|---|
| `Win + H` | Starts listening. Text appears live in the panel as you speak |
| `Win + H` (again) | Stops and pastes the text where your cursor is |
| `Esc` | Cancels and types nothing |

Word, browser, Discord, VS Code, Notepad — it works anywhere your cursor is blinking.

- A small, always-on-top red-and-black panel resembling Windows' own `Win + H` panel
- Live audio-level meter
- A system-tray icon (next to the clock) you can exit from
- Starts itself silently at every boot without cluttering the taskbar
- Single-instance lock: it will not open twice by accident

---

## Settings

You can change the values at the top of `%LOCALAPPDATA%\TurkceSesliYazma\dictation.pyw`:

| Setting | Default | Description |
|---|---|---|
| `MODEL_SIZE` | `"small"` | `base` is faster, `medium` is more accurate but slower |
| `LANGUAGE` | `"tr"` | Language to recognize |
| `BEAM_SIZE` | `5` | Higher is more accurate, slower |
| `CHUNK_SECONDS` | `3` | How often the live text is refreshed |
| `INITIAL_PROMPT` | Turkish sample sentence | Guides punctuation and spelling style |

> If you change the model size, run `install.bat` once more to download the new model.

---

## Open-source components used

| Package | Role | License |
|---|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Local speech-recognition engine | MIT |
| [Whisper models](https://github.com/openai/whisper) | Speech-recognition model | MIT |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | Microphone access | MIT |
| [keyboard](https://github.com/boppreh/keyboard) | Captures the `Win + H` shortcut | MIT |
| [NumPy](https://numpy.org) | Audio data processing | BSD |
| [pystray](https://github.com/moses-palmer/pystray) | System-tray icon | LGPL |
| [Pillow](https://python-pillow.org) | Draws the tray icon | MIT-CMU |
| Tkinter | Floating-panel interface | PSF |

---

## Uninstall

Double-click `uninstall.bat`. It removes the app folder and the startup shortcut, and the downloaded models too if you want. Python is left in place.

---

## Requirements

- Windows 11 (expected to work on Windows 10 as well)
- A microphone
- ~1.5 GB free disk (Python + packages + model)
- **No GPU required.** Runs comfortably on an ordinary laptop CPU (for example an i5-1135G7)

---

## License

[MIT](LICENSE). Use it, change it, share it however you like.

<div align="center">
<br>

**Your voice is your data. It should stay that way.**

</div>
