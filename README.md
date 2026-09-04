# ScreenCast

Lightweight screen and system audio recorder for Windows. Lives in the system tray, captures any monitor with WASAPI loopback audio, compresses to MP4 via FFmpeg. Hotkeys, customizable icon colors, configurable quality settings.

## Features

- Screen recording (any monitor) with resolution scaling (480p / 720p / 1080p)
- System audio capture via WASAPI loopback (speakers, headphones — not microphone)
- Video + audio compression via FFmpeg (H.264 + AAC)
- GPU-accelerated capture: DXcam (DXGI Desktop Duplication) or mss (GDI)
- Hardware encoding: NVIDIA NVENC, AMD AMF, Intel Quick Sync (auto-detected)
- Low CPU usage: pipe-based video writing, frame capture optimization
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
- **Video encoder** — Auto (HW detection), libx264, NVIDIA NVENC, AMD AMF, Intel Quick Sync
- **Capture backend** — mss (CPU, GDI) or DXcam (GPU, DXGI Desktop Duplication)
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
- **dxcam** — GPU screen capture (DXGI Desktop Duplication API)
- **mss** — CPU screen capture (GDI fallback)
- **soundcard** — system audio recording (WASAPI loopback)
- **opencv-python** — frame processing, resize, color conversion
- **imageio-ffmpeg** — bundled FFmpeg for compression
- **pynput** — global hotkeys
- **uv** — package manager

## Performance

Recording pipes raw video frames directly to FFmpeg via stdin, and audio via a Windows named pipe. A single FFmpeg process encodes H.264 (GPU via NVENC/AMF/QSV or CPU via libx264) + AAC and writes the final MP4 directly. No temporary files, no separate mux step.

Two capture backends are available:
- **DXcam** (default) — uses DXGI Desktop Duplication API, captures directly from GPU. Lower CPU usage (~2-3% at 1080p30).
- **mss** — uses GDI screenshots, higher CPU usage (~5-8% at 1080p30). Fallback for systems without DXGI support.

Hardware encoding is auto-detected at startup. When available, NVENC/AMF/QSV offloads H.264 encoding to the GPU, further reducing CPU load.

Typical CPU usage:
- DXcam + HW encoding: 2–4% at 1080p 30 FPS
- MSS + HW encoding: 5–8% at 1080p 30 FPS

## License

MIT — see [LICENSE](LICENSE) for details.
