# -*- coding: utf-8 -*-
"""Оверлей состояния микрофона поверх игр.

Отдельное окно со стилями WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST |
WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW:

* не забирает фокус и не мешает кликам (клики проходят сквозь него);
* не попадает в Alt+Tab и на панель задач;
* видно поверх игр в режиме «окно без рамки» (borderless windowed) и поверх
  обычных окон — но не поверх эксклюзивного полноэкранного режима, куда
  пробиваются только оверлеи с инъекцией DLL.

Рисуется через UpdateLayeredWindow: PIL-картинка с настоящей альфой.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import icons

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# ---------------------------------------------------------------- Win32

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
ULW_ALPHA = 0x00000002
AC_SRC_ALPHA = 0x1
DIB_RGB_COLORS = 0
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14
GA_ROOT = 2

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                         wintypes.DWORD)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentProcessId.restype = wintypes.DWORD


user32.RegisterClassExW.argtypes = (ctypes.POINTER(WNDCLASSEXW),)
user32.RegisterClassExW.restype = wintypes.WORD
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT)
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MONITORINFO))
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)


# ---------------------------------------------------------------- внешний вид

LABELS = {
    "off": "МИКРОФОН ВЫКЛ",
    "on": "МИКРОФОН ВКЛ",
    "live": "СЛЫШЕН ЗВУК",
    "error": "НЕТ МИКРОФОНА",
}

CORNERS = ("top-right", "bottom-right", "top-left", "bottom-left")

CORNER_LABELS = {
    "top-right": "правый верхний",
    "bottom-right": "правый нижний",
    "top-left": "левый верхний",
    "bottom-left": "левый нижний",
}

MARGIN = 24
HEIGHT = 58
ICON = 42
SS = 2  # рисуем в 2 раза крупнее и уменьшаем — сглаживание


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(state: str) -> Image.Image:
    """Пилюля «иконка + подпись» нужного состояния."""
    color = icons.COLORS.get(state, icons.COLORS["error"])
    label = LABELS.get(state, LABELS["error"])

    font = _font(19 * SS)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_w = int(tmp.textlength(label, font=font))
    width = 10 * SS + ICON * SS + 9 * SS + text_w + 14 * SS
    height = HEIGHT * SS

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # тёмная подложка с цветной рамкой
    radius = height // 2
    d.rounded_rectangle((1, 1, width - 2, height - 2), radius=radius,
                        fill=(10, 12, 16, 200), outline=color + (255,), width=2 * SS)

    # иконка микрофона
    badge = icons.draw(state, ICON * SS)
    img.alpha_composite(badge, (10 * SS, (height - ICON * SS) // 2))

    # подпись
    d.text((10 * SS + ICON * SS + 9 * SS, height // 2), label, font=font,
           fill=(255, 255, 255, 255), anchor="lm")

    return img.resize((max(1, width // SS), max(1, height // SS)), Image.LANCZOS)


# ---------------------------------------------------------------- окно

class Overlay(threading.Thread):
    """Невидимое для мыши окно-пилюля в углу экрана."""

    def __init__(self, provider, logger=None):
        """
        :param provider: функция без аргументов -> (state, visible, corner, rect)
            rect — экран (x, y, w, h), в чьём углу рисовать.
        """
        super().__init__(name="overlay", daemon=True)
        self._provider = provider
        self._log = logger
        self._hwnd = None
        self._tid = 0
        self._proc = WNDPROC(self._wndproc)
        self._shown = False
        self._last = None          # (state, corner, rect)
        self._dib = None
        self._mem_dc = None
        self._bits = None
        self._size = (0, 0)
        self._stop = threading.Event()

    # --- поток

    def run(self) -> None:
        self._tid = kernel32.GetCurrentThreadId()
        if not self._create_window():
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)

    def _create_window(self) -> bool:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "MicToggleOverlay"
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS — нормально
                if self._log:
                    self._log.error("оверлей: RegisterClassExW, ошибка %s", err)
                return False
        self._hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            "MicToggleOverlay", "MicToggle", WS_POPUP,
            0, 0, 10, 10, None, None, hinst, None)
        if not self._hwnd:
            if self._log:
                self._log.error("оверлей: CreateWindowExW, ошибка %s", ctypes.get_last_error())
            return False
        return True

    def _wndproc(self, hwnd, msg, w_param, l_param):
        return user32.DefWindowProcW(hwnd, msg, w_param, l_param)

    # --- обновление (зовётся из потока монитора)

    def tick(self) -> None:
        if not self._hwnd:
            return
        try:
            state, visible, corner, rect = self._provider()
        except Exception:
            if self._log:
                self._log.error("оверлей: provider упал", exc_info=True)
            return

        if not visible:
            if self._shown:
                user32.ShowWindow(self._hwnd, SW_HIDE)
                self._shown = False
                self._last = None
            return

        key = (state, corner, rect)
        if key == self._last and self._shown:
            return
        self._last = key

        img = _image_cache(state)
        self._paint(img)

        x, y = _corner_xy(rect, img.size, corner)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, x, y, img.size[0], img.size[1],
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self._shown = True

    def _paint(self, img: Image.Image) -> None:
        w, h = img.size
        if self._size != (w, h) or self._dib is None:
            self._release_surface()
            self._mem_dc = gdi32.CreateCompatibleDC(None)
            bi = BITMAPINFO()
            bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bi.bmiHeader.biWidth = w
            bi.bmiHeader.biHeight = -h      # сверху вниз
            bi.bmiHeader.biPlanes = 1
            bi.bmiHeader.biBitCount = 32
            bi.bmiHeader.biCompression = DIB_RGB_COLORS
            bits = ctypes.c_void_p()
            self._dib = gdi32.CreateDIBSection(self._mem_dc, ctypes.byref(bi), DIB_RGB_COLORS,
                                              ctypes.byref(bits), None, 0)
            gdi32.SelectObject(self._mem_dc, self._dib)
            self._bits = bits
            self._size = (w, h)

        # UpdateLayeredWindow ждёт премультиплированные BGRA:
        # split() отдаёт R, G, B, A, а в память надо положить B, G, R, A
        premul = img.convert("RGBa")
        r, g, b, a = premul.split()
        bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
        ctypes.memmove(self._bits.value, bgra, len(bgra))

        blend = BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
        size = SIZE(w, h)
        src = wintypes.POINT(0, 0)
        user32.UpdateLayeredWindow(self._hwnd, None, None, ctypes.byref(size),
                                   self._mem_dc, ctypes.byref(src), 0,
                                   ctypes.byref(blend), ULW_ALPHA)

    def _release_surface(self) -> None:
        if self._dib:
            gdi32.DeleteObject(self._dib)
            self._dib = None
        if self._mem_dc:
            gdi32.DeleteDC(self._mem_dc)
            self._mem_dc = None
        self._size = (0, 0)

    def stop(self) -> None:
        self._stop.set()
        if self._tid:
            user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT


_cache: dict[str, Image.Image] = {}


def _image_cache(state: str) -> Image.Image:
    if state not in _cache:
        _cache[state] = render(state)
    return _cache[state]


def _corner_xy(rect, size, corner: str):
    x, y, w, h = rect
    if corner not in CORNERS:
        corner = "top-right"
    px = x + w - size[0] - MARGIN if "right" in corner else x + MARGIN
    py = y + MARGIN if "top" in corner else y + h - size[1] - MARGIN
    return int(px), int(py)


# ---------------------------------------------------------------- экран

def primary_rect():
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    return (0, 0, width, height)


def fullscreen_rect_for(hwnd):
    """Экран (x, y, w, h), если окно занимает монитор целиком, иначе None."""
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == kernel32.GetCurrentProcessId():
        return None

    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, name, 256)
    if name.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                      "Windows.UI.Core.CoreWindow"):
        return None
    if not user32.IsWindowVisible(hwnd):
        return None

    cloaked = wintypes.DWORD()
    try:
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                     ctypes.sizeof(cloaked))
        if cloaked.value:
            return None
    except OSError:
        pass

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None

    m = info.rcMonitor
    tolerance = 2
    if (abs(rect.left - m.left) <= tolerance and abs(rect.top - m.top) <= tolerance
            and abs(rect.right - m.right) <= tolerance and abs(rect.bottom - m.bottom) <= tolerance):
        return (m.left, m.top, m.right - m.left, m.bottom - m.top)
    return None


def foreground_fullscreen():
    """Экран, если на переднем плане полноэкранное приложение, иначе None.

    Своё собственное окно и оболочку не считаем игрой.
    """
    return fullscreen_rect_for(user32.GetForegroundWindow())