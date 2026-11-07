# -*- coding: utf-8 -*-
"""Заглушка «полноэкранной игры»: чёрное окно без рамки на весь экран.

Окно не topmost — как настоящее borderless-окно игры. Через пару секунд
заглушка сама снимает снимок верхнего правого угла (чтобы не отбирать фокус
у себя же) и пишет результат проверки детектора в %TEMP%\\stub.txt.

    .venv\\Scripts\\python.exe tests\\fullscreen_stub.py [секунд]
"""

import os
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import overlay  # noqa: E402
from PIL import ImageGrab  # noqa: E402

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 12
report = Path(os.environ["TEMP"]) / "stub.txt"

root = tk.Tk()
root.overrideredirect(True)
root.geometry("1920x1080+0+0")
root.configure(bg="black")
tk.Label(root, text="ПОЛНОЭКРАННАЯ ИГРА (заглушка)", fg="#333333", bg="black",
         font=("Segoe UI", 20)).pack(expand=True)
root.update()

# безрамочное окно само фокус не получает — просим явно
hwnd = overlay.user32.GetAncestor(root.winfo_id(), overlay.GA_ROOT)
root.lift()
root.focus_force()
overlay.user32.SetForegroundWindow(hwnd)
root.update()
(Path(os.environ["TEMP"]) / "stub_hwnd.txt").write_text(str(hwnd), encoding="utf-8")


def capture():
    rect_my = overlay.fullscreen_rect_for(hwnd)
    rect_fg = overlay.foreground_fullscreen()
    img = ImageGrab.grab(bbox=(1420, 0, 1920, 140))
    img.save(Path(os.environ["TEMP"]) / "ov-stub.png")
    report.write_text(f"hwnd={hwnd}\nfullscreen_rect(мое окно)={rect_my}\n"
                      f"fullscreen_rect(передний план)={rect_fg}", encoding="utf-8")


root.after(2500, capture)
root.after(seconds * 1000, root.destroy)
root.mainloop()