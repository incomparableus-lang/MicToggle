# -*- coding: utf-8 -*-
"""Проверка оверлея: рисуется, виден, клики проходят сквозь него.

Запуск: .venv\\Scripts\\python.exe tests\\overlay_check.py [секунд]
Оверлей показывается на ~10 секунд (для снимка экрана из другого окна),
результат пишется в %TEMP%\\overlay_check.txt.
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import overlay  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
class Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


report = Path(os.environ["TEMP"]) / "overlay_check.txt"
lines = []


def say(text):
    lines.append(text)
    report.write_text("\n".join(lines), encoding="utf-8")


state = {"name": "off"}


def provider():
    return state["name"], True, "top-right", overlay.primary_rect()


ov = overlay.Overlay(provider)
ov.start()
time.sleep(1.2)
ov.tick()          # в приложении это делает поток монитора
time.sleep(0.6)

hwnd = user32.FindWindowW("MicToggleOverlay", None)
say(f"hwnd: {hwnd}")
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w = rect.right - rect.left
h = rect.bottom - rect.top
say(f"окно: {w}x{h} в ({rect.left},{rect.top})")

screen = overlay.primary_rect()
say("ожидаемый угол: {}, {}".format(screen[2] - w - overlay.MARGIN, overlay.MARGIN))

pt = wintypes.POINT(rect.left + w // 2, rect.top + h // 2)
under = user32.WindowFromPoint(pt)
name = ctypes.create_unicode_buffer(256)
user32.GetClassNameW(under, name, 256)
say(f"под оверлеем окно: {under} {name.value} | это наш оверлей: {under == hwnd}")
say("клики проходят сквозь: " + str(under != hwnd))

state["name"] = "live"
ov.tick()
time.sleep(0.5)
say("состояние переключено на live")

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 10
time.sleep(duration)
ov.stop()
say("ok")
print(report.read_text(encoding="utf-8"))