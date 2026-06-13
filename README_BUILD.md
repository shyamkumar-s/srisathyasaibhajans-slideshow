Packaging the Bhajans app

This document shows how to build standalone executables for Windows, macOS, and Linux using PyInstaller.

Prerequisites
- Python 3.10+ and pip
- Git (optional)
- On macOS: Xcode command line tools

Quick steps (per OS)

Windows (PowerShell):

```powershell
.\build-windows.ps1
```

Linux / macOS:

```bash
./build-linux.sh
```

Notes
- PyInstaller `--add-data` path separator is `;` on Windows and `:` on macOS/Linux.
- The app uses absolute paths for assets and DB when bundled; `server.py` contains a helper to find the bundle path.
- One-file builds extract into a temporary folder at runtime; large data (DB) can be bundled alongside using `--onedir` instead.

If you want CI builds, I can produce a GitHub Actions workflow that runs these commands on each runner and publishes artifacts.
