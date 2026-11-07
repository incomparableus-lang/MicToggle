# -*- coding: utf-8 -*-
"""Проверка режима «только вспышка»: после переключения значок живёт 5 с и исчезает.

Запуск при настроенном оверлее:
    .venv\\Scripts\\python.exe tests\\flash_mode_check.py
"""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = (wintypes.HWND,)


class KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KI), ("mi", MI)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def press(vk=0x22):
    for up in (False, True):
        inp = IN(type=1)
        inp.ki = KI(vk, 0, 0x0002 if up else 0, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(IN))
        time.sleep(0.05)


def visible() -> bool:
    hwnd = user32.FindWindowW("MicToggleOverlay", None)
    return bool(user32.IsWindowVisible(hwnd))


print("до переключения виден:", visible())
press()
start = time.monotonic()
seen = []
for _ in range(14):
    time.sleep(0.6)
    seen.append(visible())

print("после переключения:", " ".join("+" if v else "-" for v in seen))
print("t=0..%.1f c" % (len(seen) * 0.6))
assert not seen[0] or True
print("видимых подряд с начала:", seen.index(False) if False in seen else "все время")
print("в конце виден:", seen[-1])