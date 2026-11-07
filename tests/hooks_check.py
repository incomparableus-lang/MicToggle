# -*- coding: utf-8 -*-
"""Проверка низкоуровневых хуков: клавиатура, мышь, режим назначения.

Запуск: .venv\\Scripts\\python tests\\hooks_check.py
(основное приложение MicToggle при этом должно быть закрыто)
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hotkeys  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- SendInput

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP = 0x0080, 0x0100
XBUTTON1 = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_key(vk, up=False):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=0,
                        dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def press_key(vk):
    send_key(vk, up=False)
    time.sleep(0.03)
    send_key(vk, up=True)


def send_mouse(flags, data=0):
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx=0, dy=0, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def press_middle():
    send_mouse(MOUSEEVENTF_MIDDLEDOWN)
    time.sleep(0.03)
    send_mouse(MOUSEEVENTF_MIDDLEUP)


def press_x1():
    # на этой сборке Windows номер кнопки приходит в младшем слове mouseData
    send_mouse(MOUSEEVENTF_XDOWN, XBUTTON1)
    time.sleep(0.03)
    send_mouse(MOUSEEVENTF_XUP, XBUTTON1)


cfg = hotkeys.Config()  # PgDn, мышь не назначена
triggers = []
captured = []

cfg.mouse = "x1"
hooks = hotkeys.Hooks(lambda: cfg, lambda: triggers.append(time.monotonic()),
                      lambda result: captured.append(result))
hooks.start()
time.sleep(0.5)

print("1) PgDn ->", end=" ")
press_key(0x22)
time.sleep(0.3)
assert len(triggers) == 1, triggers
print("сработало")

print("2) удержание PgDn (автоповтор) ->", end=" ")
send_key(0x22)
for _ in range(3):
    time.sleep(0.05)
    send_key(0x22)   # повторы, как при удержании
send_key(0x22, up=True)
time.sleep(0.3)
assert len(triggers) == 2, triggers
print("одно срабатывание, повторы не считаются")

print("3) боковая кнопка мыши (x1) ->", end=" ")
press_x1()
time.sleep(0.3)
assert len(triggers) == 3, triggers
print("сработало")

print("4) кнопка без назначения (средняя) ->", end=" ")
press_middle()
time.sleep(0.3)
assert len(triggers) == 3, triggers
print("игнорируется")

print("5) назначение клавиши: Ctrl+F9 ->", end=" ")
hooks.begin_capture("key")
time.sleep(0.2)
send_key(0x11)          # Ctrl вниз
time.sleep(0.05)
send_key(0x78)          # F9
time.sleep(0.05)
send_key(0x78, up=True)
send_key(0x11, up=True)
time.sleep(0.4)
assert captured and captured[-1] == ("key", 0x78, ["ctrl"]), captured
print(captured[-1])

print("6) Esc отменяет назначение ->", end=" ")
hooks.begin_capture("mouse")
time.sleep(0.2)
press_key(0x1B)
time.sleep(0.3)
assert captured[-1] is None, captured
print("отменено")

print("7) назначение кнопки мыши ->", end=" ")
hooks.begin_capture("mouse")
time.sleep(0.2)
press_x1()
time.sleep(0.3)
assert captured[-1] == ("mouse", "x1"), captured
print(captured[-1])

hooks.stop()
time.sleep(0.3)
print("ALL OK")