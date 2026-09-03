# ScreenCast

Lightweight screen and system audio recorder for Windows. Lives in the system tray, captures any monitor with WASAPI loopback audio, compresses to MP4 via FFmpeg. Hotkeys, customizable icon colors, configurable quality settings.

## Features

- Screen recording (any monitor) with resolution scaling (480p / 720p / 1080p)
- System audio capture via WASAPI loopback (speakers, headphones)
- Video + audio compression via FFmpeg (H.264 + AAC)
- System tray icon with state indication:
  - Blue — idle
  - Red — recording
  - Yellow — saving to disk
- Hotkey to start/stop (default `Ctrl+Shift+R`)
- Customizable filename pattern with tokens: `{date}`, `{time}`, `{n}`
- Settings: resolution, FPS, video/audio bitrate, output folder
- Pop-up notifications (can be disabled)
- Customizable tray icon colors

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/AIgrator/ScreenCast.git
cd ScreenCast
uv sync
uv run python recorder.py
```

## Usage

1. Launch the app — tray icon appears (blue)
2. Right-click the icon for the menu
3. Click "Start recording" or use the hotkey `Ctrl+Shift+R`
4. Icon turns red — recording in progress
5. Press the hotkey again — recording stops, icon turns yellow
6. After saving, icon returns to blue

### Menu

- **Start recording** / **Stop recording** — toggle recording
- **Select monitor** — choose which monitor to capture
- **Select audio source** — choose playback device (WASAPI loopback)
- **Settings** — recording parameters and hotkeys
- **Exit** — close the application

### Settings

#### General
- **Hotkeys** — configure start/stop key combination
- **Notifications** — enable/disable pop-up messages
- **Tray icon colors** — customize colors for idle, recording, saving states

#### Path & Filename
- **Output folder** — where videos are saved (default `videos/`)
- **Filename pattern** — strftime format with `{n}` counter:
  - `%Y` `%m` `%d` `%H` `%M` `%S` `%a` `%b` — standard date/time codes
  - `{n}` — auto-incrementing number (scans folder for existing files)
  - `{n:03}` — zero-padded (e.g. `001`, `002`)
- Quick-insert dropdown for common tokens
- Live preview of resulting filename

#### Quality
- **Resolution** — 480p, 720p, 1080p
- **Frame rate** — 10, 15, 20, 25, 30 FPS
- **Video bitrate** — 500–5000 kbps
- **Audio bitrate** — 128, 192, 256, 320 kbps
- **Sample rate** — 44100, 48000 Hz

## Project Structure

```
├── pyproject.toml              # Project config, dependencies
├── recorder.py                 # Entry point, recording, tray, hotkeys
├── src/
│   ├── settings_manager.py     # Settings manager (JSON)
│   └── ui/
│       ├── settings_dialog.py  # Settings dialog with tabs
│       ├── settings_page.py    # Quality tab
│       ├── main_page.py        # General tab
│       ├── file_page.py        # Path & Filename tab
│       └── hotkey_line_edit.py # Hotkey input widget
├── videos/                     # Recordings folder (gitignored)
└── settings.json               # Local settings (gitignored)
```

## Tech Stack

- **Python 3.10+**
- **PyQt6** — GUI, tray, dialogs
- **mss** — screen capture
- **soundcard** — system audio recording (WASAPI loopback)
- **opencv-python** — frame processing
- **imageio-ffmpeg** — bundled FFmpeg for compression
- **pynput** — global hotkeys
- **uv** — package manager

## Output

Recordings are saved to the configured output folder. Default filename pattern: `{date:YYYYMMDD}-{time:HHmmss}.mp4` → `20260903-171530.mp4`.

## License

MIT
