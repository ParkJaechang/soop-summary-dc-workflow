# SOOP WebApp Packaging Guide

## Overview
This project runs a local FastAPI server and serves the UI from `webapp/index.html`. When launched directly, it opens the browser automatically on `http://127.0.0.1:8765`.
The recommended packaging flow is:
1. Build a standalone Windows executable with PyInstaller.
2. Wrap that build with Inno Setup for an installer experience.

## Runtime Files
The installer includes the app, Python runtime from PyInstaller, and bundled ffmpeg binaries. Internet is only needed for the first Whisper model download and Gemini API access.
These files need to ship together:
- `soop_webapp_v1.py`
- `webapp/index.html`
- `ffmpeg.exe`
- `ffprobe.exe`
- Python dependencies from `requirements_webapp.txt`
- Whisper model cache folder created on first run: `models`

## Local Development
Install dependencies:
```powershell
python -m pip install -r requirements_webapp.txt
```

Run locally:
```powershell
python soop_webapp_v1.py
```

Or use:
```powershell
.\run_webapp.bat
```

## Build with PyInstaller
Install build tools:
```powershell
python -m pip install pyinstaller
```

Create the executable:
```powershell
pyinstaller --noconfirm --clean soop_webapp_v1.spec
```

Build output:
- `dist\\SOOPWebApp\\SOOPWebApp.exe`

## Create Installer with Inno Setup
1. Install Inno Setup.
2. Open `installer\\SOOPWebApp.iss`.
3. Build the installer.

Expected output:
- `installer\\Output\\SOOPWebAppSetup.exe`

## Git Checklist
Recommended files to commit:
- `soop_webapp_v1.py`
- `webapp/index.html`
- `requirements_webapp.txt`
- `run_webapp.bat`
- `install_webapp.bat`
- `build_webapp.bat`
- `soop_webapp_v1.spec`
- `installer\\SOOPWebApp.iss`
- `docs\\SOOP_WEBAPP_PACKAGING.md`

## First Run on a Clean PC
1. Install `SOOPWebAppSetup.exe`.
2. Launch the app.
3. The browser opens automatically.
4. The first Local STT run downloads the selected Whisper model into the app `models` folder.
5. Later runs reuse the downloaded model.

## Notes
- The folder picker uses the local Windows folder dialog through Tk.
- Gemini requests can hit free-tier quota limits.
- `ffmpeg.exe` and `ffprobe.exe` are expected next to the executable.
