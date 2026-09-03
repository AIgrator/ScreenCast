# ScreenCast

Lightweight screen and system audio recorder for Windows. Lives in the system tray, captures any monitor with WASAPI loopback audio, compresses to MP4 via FFmpeg. Hotkeys, customizable icon colors, configurable quality settings.

## Features

- Screen recording (any monitor) with resolution scaling (480p / 720p / 1080p)
- System audio capture via WASAPI loopback (speakers, headphones — not microphone)
- Video + audio compression via FFmpeg (H.264 + AAC)
- Low CPU usage: MJPG temp codec, array slicing, low thread priority
- System tray icon with pie arc progress indicator:
  - Blue — idle
  - Red — recording
  - White circle + colored arc — saving to disk (arc fills clockwise)
- Hotkey to start/stop (default `Ctrl+Shift+F`)
- Customizable filename pattern with strftime codes: `%Y%m%d-%H%M%S`
- Auto-incrementing counter `{n}` / `{n:03}` (scans folder for existing files)
- Settings: resolution, FPS, video/audio bitrate, output folder
- Pop-up notifications (can be disabled)
- Customizable tray icon colors for each state
- Custom tooltip (positioned left of cursor)
- Internationalization: English (default) and Russian, switchable in settings

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
3. Click "Start recording" or use the hotkey `Ctrl+Shift+F`
4. Icon turns red — recording in progress
5. Press the hotkey again — recording stops, icon shows white circle with colored arc
6. After saving, icon returns to blue

### Menu

- **Start recording** / **Stop recording** — toggle recording
- **Select monitor** — choose which monitor to capture
- **Select audio source** — choose playback device (WASAPI loopback)
- **Settings** — recording parameters and hotkeys
- **Exit** — close the application

### Settings

#### General
- **Language** — switch between English and Russian (instant, no restart)
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
├── recorder.py                 # Entry point, TrayApp (tray, menu, UI)
├── src/
│   ├── settings_manager.py     # Settings manager (JSON)
│   ├── translation_manager.py  # i18n translation system
│   ├── hotkey_manager.py       # Global hotkeys (pynput)
│   ├── screen_recorder.py      # Screen/audio recording + FFmpeg muxing
│   └── ui/
│       ├── settings_dialog.py  # Settings dialog with tabs
│       ├── settings_page.py    # Quality tab
│       ├── main_page.py        # General tab (hotkeys, notifications, colors, language)
│       ├── file_page.py        # Path & Filename tab
│       └── hotkey_line_edit.py # Hotkey input widget
├── translations/
│   ├── en.json                 # English translations
│   └── ru.json                 # Russian translations
├── videos/                     # Recordings folder (gitignored)
└── settings.json               # Local settings (gitignored)
```

## Tech Stack

- **Python 3.10+**
- **PyQt6** — GUI, tray, dialogs
- **mss** — screen capture
- **soundcard** — system audio recording (WASAPI loopback)
- **opencv-python** — frame processing (MJPG temp codec)
- **imageio-ffmpeg** — bundled FFmpeg for compression
- **pynput** — global hotkeys
- **uv** — package manager

## Performance

Recording uses MJPG for the temporary video file (fast writes, no compression overhead). FFmpeg re-encodes to H.264 + AAC during the saving phase. Frame capture uses numpy array slicing instead of `cv2.cvtColor` to avoid unnecessary memory copies. Audio blocksize is set to 4096 frames to reduce callback frequency. On Windows, the video capture thread runs at lower priority to minimize system impact.

Typical CPU usage: 5–8% at 720p 25 FPS.

## License

MIT — see [LICENSE](LICENSE) for details.
