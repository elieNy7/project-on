# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

spec_root = Path(globals().get("SPECPATH", ".")).resolve()


def data_file(relative_path, target_dir):
    src = spec_root / relative_path
    if not src.exists():
        raise FileNotFoundError(f"Required installer resource missing: {src}")
    return (str(src), target_dir)


presentation_files = (
    "config.json",
    "fonts.css",
    "index.html",
    "obs.html",
    "obs-config.json",
    "obs-script.js",
    "obs-style.css",
    "script.js",
    "slide.json",
    "style.css",
)

font_files = (
    "Bebas_Neue/BebasNeue-Regular.ttf",
    "Google_Sans/static/GoogleSans-Regular.ttf",
    "Google_Sans/static/GoogleSans-Medium.ttf",
    "Google_Sans/static/GoogleSans-SemiBold.ttf",
    "Google_Sans/static/GoogleSans-Bold.ttf",
    "Google_Sans/static/GoogleSans-Italic.ttf",
    "Poppins/Poppins-Regular.ttf",
    "Poppins/Poppins-Medium.ttf",
    "Poppins/Poppins-SemiBold.ttf",
    "Poppins/Poppins-Bold.ttf",
    "Poppins/Poppins-Italic.ttf",
    "Poppins/Poppins-Light.ttf",
    "Noto_Sans/static/NotoSans-Regular.ttf",
    "Noto_Sans/static/NotoSans-Bold.ttf",
    "Oswald/static/Oswald-Regular.ttf",
    "Oswald/static/Oswald-Bold.ttf",
)

ndi_arch = "x64" if sys.maxsize > 2**32 else "x86"

# Runtime resources only. Source PDFs, import scripts, backups, bible_json and
# unused font families are intentionally excluded from the installer.
added_files = [
    data_file("data/project_on.db", "data"),
    data_file("assets/logo.ico", "assets"),
    data_file("assets/logo/app icon.png", "assets/logo"),
    data_file(f"ndi/bin/Processing.NDI.Lib.{ndi_arch}.dll", "ndi/bin"),
]

added_files += [
    data_file(f"presentation/{name}", "presentation")
    for name in presentation_files
]

added_files += [
    data_file(f"assets/fonts/{name}", f"assets/fonts/{Path(name).parent.as_posix()}")
    for name in font_files
]

# Default projection backgrounds (gradients + Christian symbol watermarks).
# Seeded into the user backgrounds folder on first launch.
added_files += [
    (str(p), "assets/backgrounds")
    for p in sorted((spec_root / "assets" / "backgrounds").glob("*.png"))
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'winreg',
        'sqlite3',
        'html',
        're',
        'json',
        'pathlib',
        'shutil',
        'numpy',
        'NDIlib',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
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
    name='Project-On',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Project-On',
)
