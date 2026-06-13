#!/usr/bin/env bash
# Build script for Linux/macOS using PyInstaller (run on target OS)
set -euo pipefail
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pyinstaller

# Build one-file executable; note use ':' to separate add-data on Unix
pyinstaller --noconfirm --onefile \
  --name "SriSathyaSaiBhajansSlidesServer" \
  --add-data "assets:assets" \
  --add-data "sai-bhajans.html:." \
  --add-data "bhajans.db:." \
  server.py

echo "Build finished. See dist/server (or dist/server.exe on Windows)."