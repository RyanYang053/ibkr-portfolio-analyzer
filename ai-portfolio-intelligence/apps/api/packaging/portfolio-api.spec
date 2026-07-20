# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile spec for the Portfolio Analyzer Tauri sidecar."""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parents[0]  # apps/api

a = Analysis(
    [str(root / "scripts" / "desktop_entrypoint.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "app.main",
        "keyring",
        "keyring.backends",
        "bcrypt",
        "passlib.handlers.bcrypt",
        "passlib.handlers.pbkdf2",
        "passlib.utils.compat",
        "passlib.utils",
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

# onefile: Tauri externalBin expects a single executable named with a target triple.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="portfolio-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
