# -*- coding: utf-8 -*-
"""Проверка срабатывания горячей клавиши у запущенного MicToggle."""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ctypes import POINTER, cast  # noqa: E402

from comtypes import CLSCTX_ALL  # noqa: E402
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    """Нужен только для размера union: Windows требует полный sizeof(INPUT)."""

    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def press(vk):
    for up in (False, True):
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(vk, 0, 0x0002 if up else 0, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.04)


def mute() -> bool:
    dev = AudioUtilities.GetMicrophone()
    vol = cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
               POINTER(IAudioEndpointVolume))
    return bool(vol.GetMute())


before = mute()
print("mute before:", before)
press(0x22)  # PgDn
time.sleep(0.6)
after = mute()
print("mute after PgDn:", after)
assert after != before, "горячая клавиша не сработала"

press(0x22)
time.sleep(0.6)
restored = mute()
print("mute after second PgDn:", restored)
assert restored == before
print("HOTKEY OK")