# PyInstaller spec file example. Run: pyinstaller pyinstaller.spec
# Adjust paths if necessary

# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis([
    'server.py',
],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('sai-bhajans.html', '.'),
        ('bhajans.db', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
        exclude_binaries=True,
        name='SriSathyaSaiBhajansSlidesServer',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
            a.datas,
            strip=False,
            upx=True,
            upx_exclude=[],
            name='SriSathyaSaiBhajansSlidesServer')