# PowerShell build script for Windows using PyInstaller
# Run from project root in PowerShell

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt pyinstaller

# Build one-file executable; adjust files as needed
pyinstaller --noconfirm --onefile `
	--name "SriSathyaSaiBhajansSlidesServer" `
	--add-data "assets;assets" `
	--add-data "sai-bhajans.html;." `
	--add-data "bhajans.db;." `
	server.py

Write-Host "Build finished. See dist\SriSathyaSaiBhajansSlidesServer.exe" 
