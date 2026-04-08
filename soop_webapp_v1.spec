# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules("faster_whisper")
hiddenimports += collect_submodules("google.generativeai")
hiddenimports += collect_submodules("ctranslate2")

block_cipher = None

added_files = [
    ("webapp\\index.html", "webapp"),
    ("ffmpeg.exe", "."),
    ("ffprobe.exe", "."),
]

package_datas = []
package_datas += collect_data_files("faster_whisper")
package_datas += collect_data_files("ctranslate2")

a = Analysis(
    ["soop_webapp_v1.py"],
    pathex=[],
    binaries=[],
    datas=added_files + package_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SOOPWebApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SOOPWebApp",
)