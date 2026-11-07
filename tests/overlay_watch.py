# -*- coding: utf-8 -*-
"""Следит за окном оверлея после переключения микрофона."""

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


press()
start = time.monotonic()
hwnd = None
for _ in range(20):
    time.sleep(0.4)
    hwnd = user32.FindWindowW("MicToggleOverlay", None)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print(f"t={time.monotonic() - start:4.1f}s hwnd={hwnd} виден={bool(user32.IsWindowVisible(hwnd))} "
          f"({rect.left},{rect.top}) {rect.right - rect.left}x{rect.bottom - rect.top}")