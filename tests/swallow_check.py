# -*- coding: utf-8 -*-
"""Проверка перехвата: доходит ли PageDown до обычного окна.

Запуск: .venv\\Scripts\\python tests\\swallow_check.py
Печатает "получено: True/False". При включённом перехвате должно быть False.
"""

import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)


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


def press(vk):
    for up in (False, True):
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(vk, 0, 0x0002 if up else 0, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.04)


received = []

root = tk.Tk()
root.title("swallow test")
root.geometry("220x80+40+40")
label = tk.Label(root, text="жду PageDown")
label.pack(expand=True)
root.bind("<KeyPress>", lambda e: (received.append(e.keysym), label.config(text=e.keysym)))


def fire():
    press(0x22)


root.after(1200, fire)
root.after(2200, root.quit)
root.attributes("-topmost", True)
root.update()

hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
root.focus_force()
root.update()
print("окно в фокусе:", user32.GetForegroundWindow() == hwnd)

root.mainloop()

print("получено:", bool(received), received)