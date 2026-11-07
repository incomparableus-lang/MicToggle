# -*- coding: utf-8 -*-
"""Глобальные горячие клавиши для MicToggle.

Клавиатура и кнопки мыши ловятся низкоуровневыми хуками Windows
(WH_KEYBOARD_LL / WH_MOUSE_LL), поэтому работают, даже когда окно не в фокусе,
и могут «съесть» нажатие, чтобы оно не досталось другим программам.

Мышь поддерживается: средняя кнопка (колесо), боковые 1 и 2 (назад/вперёд).
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
WM_QUIT = 0x0012

VK_ESCAPE = 0x1B
VK_CONTROL, VK_MENU, VK_SHIFT = 0x11, 0x12, 0x10
VK_LWIN, VK_RWIN = 0x5B, 0x5C

MODIFIER_VKS = {VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN,
                0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}  # L/R shift, ctrl, alt

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

SetWindowsHookExW = user32.SetWindowsHookExW
SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD)
SetWindowsHookExW.restype = ctypes.c_void_p

UnhookWindowsHookEx = user32.UnhookWindowsHookEx
UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)

CallNextHookEx = user32.CallNextHookEx
CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
CallNextHookEx.restype = LRESULT

GetMessageW = user32.GetMessageW
GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT)
GetMessageW.restype = ctypes.c_int

GetAsyncKeyState = user32.GetAsyncKeyState
GetAsyncKeyState.argtypes = (ctypes.c_int,)
GetAsyncKeyState.restype = ctypes.c_short

PostThreadMessageW = user32.PostThreadMessageW
PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


MOUSE_NAMES = {
    "middle": "средняя (колесо)",
    "x1": "боковая 1 (назад)",
    "x2": "боковая 2 (вперёд)",
}

_KEY_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "CapsLock",
    0x1B: "Esc", 0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
    0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrtScr", 0x2D: "Insert", 0x2E: "Delete", 0x5B: "Win", 0x5C: "Win",
    0x5D: "Menu", 0x6A: "*", 0x6B: "+", 0x6C: "Separator", 0x6D: "-",
    0x6E: ".", 0x6F: "/", 0x90: "NumLock", 0x91: "ScrollLock", 0xBA: ";",
    0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
_KEY_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24)})
_KEY_NAMES.update({0x30 + i: str(i) for i in range(10)})
_KEY_NAMES.update({0x60 + i: f"Num{i}" for i in range(10)})


def vk_name(vk: int) -> str:
    """Читаемое имя клавиши для меню и подсказок."""
    if vk in _KEY_NAMES:
        return _KEY_NAMES[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"VK 0x{vk:02X}"


def current_mods() -> set[str]:
    """Какие модификаторы сейчас зажаты."""
    mods = set()
    if GetAsyncKeyState(VK_CONTROL) & 0x8000 or GetAsyncKeyState(0xA2) & 0x8000 \
            or GetAsyncKeyState(0xA3) & 0x8000:
        mods.add("ctrl")
    if GetAsyncKeyState(VK_MENU) & 0x8000 or GetAsyncKeyState(0xA4) & 0x8000 \
            or GetAsyncKeyState(0xA5) & 0x8000:
        mods.add("alt")
    if GetAsyncKeyState(VK_SHIFT) & 0x8000 or GetAsyncKeyState(0xA0) & 0x8000 \
            or GetAsyncKeyState(0xA1) & 0x8000:
        mods.add("shift")
    if GetAsyncKeyState(VK_LWIN) & 0x8000 or GetAsyncKeyState(VK_RWIN) & 0x8000:
        mods.add("win")
    return mods


MOD_ORDER = ("ctrl", "alt", "shift", "win")
MOD_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


@dataclass
class Config:
    """Настройки горячих клавиш и оверлея."""

    key_vk: int | None = 0x22          # PgDn
    key_mods: list[str] = field(default_factory=list)
    mouse: str | None = None
    swallow: bool = True               # не отдавать клавишу приложениям

    # оверлей состояния поверх игр
    overlay: bool = False
    overlay_corner: str = "top-right"
    overlay_only_muted: bool = False
    overlay_only_fullscreen: bool = True

    CORNERS = ("top-right", "bottom-right", "top-left", "bottom-left")

    @property
    def key_name(self) -> str:
        if self.key_vk is None:
            return "не назначена"
        parts = [MOD_LABELS[m] for m in MOD_ORDER if m in self.key_mods]
        parts.append(vk_name(self.key_vk))
        return "+".join(parts)

    @property
    def mouse_name(self) -> str:
        return MOUSE_NAMES.get(self.mouse or "", "не назначена")

    def to_dict(self) -> dict:
        return {"key_vk": self.key_vk, "key_mods": list(self.key_mods),
                "mouse": self.mouse, "swallow": self.swallow,
                "overlay": self.overlay, "overlay_corner": self.overlay_corner,
                "overlay_only_muted": self.overlay_only_muted,
                "overlay_only_fullscreen": self.overlay_only_fullscreen}

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        vk = data.get("key_vk", 0x22)
        mouse = data.get("mouse")
        corner = data.get("overlay_corner", "top-right")
        return cls(
            key_vk=int(vk) if vk is not None else None,
            key_mods=[m for m in data.get("key_mods", []) if m in MOD_ORDER],
            mouse=mouse if mouse in MOUSE_NAMES else None,
            swallow=bool(data.get("swallow", True)),
            overlay=bool(data.get("overlay", False)),
            overlay_corner=corner if corner in cls.CORNERS else "top-right",
            overlay_only_muted=bool(data.get("overlay_only_muted", False)),
            overlay_only_fullscreen=bool(data.get("overlay_only_fullscreen", True)),
        )


def _config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    folder = Path(base) / "MicToggle"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json"


def load_config() -> Config:
    try:
        # utf-8-sig: файл может быть сохранён блокнотом/PowerShell с BOM
        return Config.from_dict(json.loads(_config_path().read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return Config()


def save_config(cfg: Config) -> None:
    path = _config_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def config_exists() -> bool:
    return _config_path().exists()


def _xbutton_name(mouse_data: int) -> str:
    """Номер боковой кнопки.

    По документации он лежит в старшем слове mouseData, но на некоторых
    сборках Windows (и при инъекции событий) приходит в младшем.
    """
    high = (mouse_data >> 16) & 0xFFFF
    low = mouse_data & 0xFFFF
    button = high or low
    return "x1" if button == 1 else "x2"


class Hooks:
    """Поток с низкоуровневыми хуками клавиатуры и мыши."""

    def __init__(self, config_getter, on_trigger, on_captured, logger=None):
        """
        :param config_getter: функция без аргументов, возвращает Config
        :param on_trigger: вызывается при срабатывании горячей клавиши
        :param on_captured: вызывается с ("key", vk, mods) / ("mouse", name) / None
        :param logger: logging.Logger
        """
        self._cfg = config_getter
        self._on_trigger = on_trigger
        self._on_captured = on_captured
        self._log = logger
        self._capture_kind = None      # None | "key" | "mouse"
        self._tid = 0
        self._thread = None
        self._kb_hook = None
        self._ms_hook = None
        self._kb_proc = None
        self._ms_proc = None
        self._pressed = set()          # зажатые клавиши (антиповтор)
        self._swallowed = set()        # клавиши, чьи события мы съели
        self._swallowed_mouse = set()
        self._lock = threading.Lock()

    # --- управление извне

    @property
    def capture_kind(self) -> str | None:
        return self._capture_kind

    def begin_capture(self, kind: str) -> None:
        with self._lock:
            self._capture_kind = kind

    def cancel_capture(self) -> None:
        with self._lock:
            self._capture_kind = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="hook-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._tid:
            PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    # --- поток хуков

    def _run(self) -> None:
        self._tid = kernel32.GetCurrentThreadId()
        self._kb_proc = HOOKPROC(self._keyboard_cb)
        self._ms_proc = HOOKPROC(self._mouse_cb)
        if self._log:
            self._log.info("поток хуков: tid=%s", self._tid)
        self._kb_hook = SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, None, 0)
        self._ms_hook = SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, None, 0)
        if self._log:
            self._log.info("хуки: клавиатура %s, мышь %s",
                           bool(self._kb_hook), bool(self._ms_hook))
        msg = wintypes.MSG()
        while True:
            r = GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:
                if self._log:
                    self._log.info("цикл хуков завершился: GetMessage=%s", r)
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._kb_hook:
            UnhookWindowsHookEx(self._kb_hook)
        if self._ms_hook:
            UnhookWindowsHookEx(self._ms_hook)

    # --- колбэки

    def _next(self, hook, n_code, w_param, l_param):
        return CallNextHookEx(hook, n_code, w_param, l_param)

    def _keyboard_cb(self, n_code, w_param, l_param):
        try:
            if n_code != HC_ACTION:
                return self._next(self._kb_hook, n_code, w_param, l_param)

            kb = KBDLLHOOKSTRUCT.from_address(l_param)
            vk = int(kb.vkCode)
            message = int(w_param)

            if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if vk in MODIFIER_VKS:
                    return self._next(self._kb_hook, n_code, w_param, l_param)

                capture = self._capture_kind
                if capture is not None:
                    if vk == VK_ESCAPE:
                        self._finish_capture(None)
                    elif capture == "key":
                        self._finish_capture(("key", vk, sorted(current_mods())))
                    else:
                        return self._next(self._kb_hook, n_code, w_param, l_param)
                    return 1  # съедаем событие настройки

                cfg = self._cfg()
                if cfg.key_vk is not None and vk == cfg.key_vk \
                        and current_mods() == set(cfg.key_mods):
                    repeat = vk in self._pressed
                    self._pressed.add(vk)
                    if not repeat:
                        self._on_trigger()
                    if cfg.swallow:
                        self._swallowed.add(vk)
                        return 1
                    return self._next(self._kb_hook, n_code, w_param, l_param)

                if vk in self._swallowed:
                    return 1

            elif message in (WM_KEYUP, WM_SYSKEYUP):
                self._pressed.discard(vk)
                if vk in self._swallowed:
                    self._swallowed.discard(vk)
                    return 1

            return self._next(self._kb_hook, n_code, w_param, l_param)

        except Exception:
            if self._log:
                self._log.error("ошибка в хуке клавиатуры", exc_info=True)
            return self._next(self._kb_hook, n_code, w_param, l_param)

    def _mouse_cb(self, n_code, w_param, l_param):
        try:
            if n_code != HC_ACTION:
                return self._next(self._ms_hook, n_code, w_param, l_param)

            message = int(w_param)
            if message not in (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP):
                return self._next(self._ms_hook, n_code, w_param, l_param)

            data = MSLLHOOKSTRUCT.from_address(l_param)
            if message in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                button = "middle"
            else:
                button = _xbutton_name(int(data.mouseData))

            capture = self._capture_kind
            if capture == "mouse" and message in (WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                self._finish_capture(("mouse", button))
                self._swallowed_mouse.add(button)
                return 1

            cfg = self._cfg()
            if cfg.mouse == button:
                if message in (WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                    self._on_trigger()
                    self._swallowed_mouse.add(button)
                return 1  # кнопку всегда забираем себе

            if button in self._swallowed_mouse:
                if message in (WM_MBUTTONUP, WM_XBUTTONUP):
                    self._swallowed_mouse.discard(button)
                return 1

            return self._next(self._ms_hook, n_code, w_param, l_param)

        except Exception:
            if self._log:
                self._log.error("ошибка в хуке мыши", exc_info=True)
            return self._next(self._ms_hook, n_code, w_param, l_param)

    def _finish_capture(self, result) -> None:
        with self._lock:
            self._capture_kind = None
        self._on_captured(result)