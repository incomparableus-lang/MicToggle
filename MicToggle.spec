# -*- mode: python ; coding: utf-8 -*-
"""Сборка MicToggle.exe: PyInstaller, папка dist\MicToggle.

Собирается build.ps1 (он же готовит build\version_info.txt для версии exe).
"""

from pathlib import Path

root = Path(SPECPATH)
version = (root / "VERSION").read_text(encoding="utf-8").strip()

a = Analysis(
    [str(root / "mic_toggle.pyw")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "VERSION"), ".")],
    hiddenimports=[
        # pystray выбирает бэкенд динамически — PyInstaller его не видит
        "pystray._win32",
        "pystray._base",
        "pystray._util",
        "pystray._util.win32",
        # comtypes тянет части пакета неявно
        "comtypes.stream",
        "comtypes.typeinfo",
        "pycaw.pycaw",
        "pycaw.utils",
        "pycaw.callbacks",
        "pycaw.constants",
        "pycaw.magic",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MicToggle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / "MicToggle.ico"),
    version=str(root / "build" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MicToggle",
)