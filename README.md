# Fortnite Auto OCR (ViGEm + RapidOCR)

Screen-aware Fortnite AFK & loot-tracking automation written from scratch for Windows. Uses **RapidOCR** (`rapidocr-onnxruntime`) to classify game screens (supports both English and Italian Fortnite clients) and sends native controller inputs through a **ViGEm virtual Xbox 360 gamepad**.

## Features

- **Screen-Aware State Machine**: Automatically handles Lobby ready-up, Battle Bus / Ship drop, in-match survival timer, anti-kick movement, Match Recap / Play Again, Discover/wrong-tab recovery, Network Error popups, and Sleep Mode wake-up.
- **Native Virtual Controller (`vigem_bridge.dll`)**: Emulates an Xbox 360 gamepad via ViGEmBus (no mouse/keyboard hijacking).
- **High-Speed Multi-Monitor Capture (`dxgi_bridge.dll`)**: Uses DXGI Desktop Duplication with automatic fallback to GDI `BitBlt`, `mss`, and `PrintWindow`. Handles Per-Monitor v2 DPI scaling and rotated secondary displays (e.g. drawing tablets).
- **Pirate Token & Gizmo Tracking**: Counts session Gizmo drops and automatically stops + alerts when a Pirate Token is detected (visual template matching via `templates/pirate_token.png` + OCR text confirmation).
- **Ban / Suspension Safety**: Immediately halts and saves a debug screenshot + OCR log if an account or matchmaking ban/suspension screen is detected.

## Requirements

- **Windows 10 / 11** (x64)
- **ViGEmBus** driver:
  ```powershell
  winget install ViGEm.ViGEmBus
  ```
  *(Or download the latest installer from [nefarius/ViGEmBus releases](https://github.com/nefarius/ViGEmBus/releases).)*
- **Python 3.10+** (checked in `PATH`)
- **Fortnite** set to **Windowed Fullscreen** (not Exclusive Fullscreen), with the target monitor powered on.

> Precompiled x64 DLLs (`bin/vigem_bridge.dll` and `bin/dxgi_bridge.dll`) are included, so no C++ compiler is required for normal use.

## Quick Start (Plug & Play)

1. Install the **ViGEmBus** driver (`winget install ViGEm.ViGEmBus`).
2. Clone or download this repository.
3. Double-click **`start.bat`**.
   - On first run, `start.bat` automatically creates a local `.venv` and installs all Python dependencies from `requirements.txt`.
4. Launch Fortnite in **Windowed Fullscreen** on the Battle Royale lobby.

### Console Controls

| Key | Action |
| --- | --- |
| `P` | Pause / Resume |
| `T` | Toggle match timer (`180s` / `300s`) |
| `M` | Move Fortnite window to the next display |
| `D` | Save debug snapshot (`debug_capture.png` + `debug_ocr.txt`) |
| `Q` | Quit cleanly and disconnect virtual controller |

## Configuration (`config.json`)

| Key | Default | Description |
| --- | --- | --- |
| `timer_seconds` | `180` | Survival timer duration in seconds before leaving match |
| `drop_from_bus` | `true` | Automatically jump from the Battle Bus / Ship |
| `bus_wait_seconds` | `8` | Seconds to wait on the Bus before jumping |
| `anti_kick_interval_seconds` | `25` | Interval between anti-AFK stick/jump/pickaxe inputs |
| `scan_interval_seconds` | `1.5` | Delay between main-loop OCR scans |
| `strict_mode_match` | `false` | Require explicit `BATTLE ROYALE` OCR text before readying up |
| `allowed_modes` | `["BATTLE ROYALE"]` | Allowed lobby modes |
| `blocked_modes` | `[...]` | Modes that block ready-up (Reload, OG, Creative, etc.) |
| `gizmo_keywords` | `[...]` | OCR keywords counted as Gizmo drops |
| `token_text_keywords` | `[...]` | OCR keywords used for Pirate Token detection |
| `token_template_threshold` | `0.72` | OpenCV template matching threshold for `templates/pirate_token*.png` |
| `gizmo_cooldown_seconds` | `25` | Cooldown between counting duplicate Gizmo detections |

## Custom Token Template

To enable visual icon + text verification for Pirate Token detection, place a cropped screenshot of the token icon at `templates/pirate_token.png` (see `templates/README.txt`).

## Building Native DLLs (Optional)

If you want to rebuild `vigem_bridge.dll` and `dxgi_bridge.dll` from `native/`:

```powershell
cmake -S native -B native/build -A x64
cmake --build native/build --config Release
```

Copy the resulting `.dll` files from `native/build/Release/` into `bin/`.

## Disclaimer

This project is provided for educational and personal automation purposes only. Use at your own risk.
