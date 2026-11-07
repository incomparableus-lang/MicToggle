# -*- coding: utf-8 -*-
"""Отрисовка значков для MicToggle.

Значок — цветной кружок с белым микрофоном:

* ``off``   — красный, микрофон перечёркнут (микрофон выключен);
* ``on``    — зелёный, микрофон включён, но тишина;
* ``live``  — яркий зелёный, по бокам «волны»: в микрофон идёт звук;
* ``error`` — серый, устройство записи недоступно.

Каждый размер ICO рисуется отдельно (16, 20, 24, ... 128 px), поэтому
значок остаётся резким при любом масштабе и DPI.
"""

import io
import struct

from PIL import Image, ImageDraw

COLORS = {
    "off": (214, 58, 58),
    "on": (46, 160, 92),
    "live": (32, 214, 110),
    "error": (128, 128, 128),
}

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128]

SS = 8  # суперсэмплинг — сглаживание штрихов


def draw(state: str, size: int = 128) -> Image.Image:
    """Рисует значок нужного состояния и размера на прозрачном фоне."""
    color = COLORS.get(state, COLORS["error"])
    small = size <= 24
    W = size * SS
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    white = (255, 255, 255)

    def box(t):
        return tuple(v * W for v in t)

    # цветной кружок-подложка
    inset = W * 0.015
    d.ellipse((inset, inset, W - inset, W - inset), fill=color)

    # на 16-24 px ножку и основание не рисуем — они превращаются в кашу
    cap = box((0.400, 0.14, 0.600, 0.52) if small else (0.415, 0.16, 0.585, 0.50))
    d.rounded_rectangle(cap, radius=(cap[2] - cap[0]) / 2, fill=white)
    # дуга-держатель
    stroke = max(int((0.075 if small else 0.048) * W), SS * 2)
    arc_box = (0.28, 0.28, 0.72, 0.64) if small else (0.325, 0.295, 0.675, 0.615)
    d.arc(box(arc_box), 0, 180, fill=white, width=stroke)
    if not small:
        # ножка и основание
        d.line((W / 2, 0.615 * W, W / 2, 0.745 * W), fill=white, width=stroke)
        d.line((0.415 * W, 0.745 * W, 0.585 * W, 0.745 * W), fill=white, width=stroke)

    if state == "live" and not small:
        # «волны» звука: две дуги по бокам кружка
        w = max(int(0.040 * W), SS * 2)
        d.arc(box((0.055, 0.305, 0.285, 0.695)), 110, 250, fill=white, width=w)
        d.arc(box((0.715, 0.305, 0.945, 0.695)), 290, 430, fill=white, width=w)

    if state == "off":
        # перечёркиваем микрофон: классический «mute»
        w = max(int(0.050 * W), int(SS * 1.6))
        d.line((0.15 * W, 0.15 * W, 0.85 * W, 0.85 * W), fill=white, width=w)

    return img.resize((size, size), Image.LANCZOS)


class TrayImage:
    """Картинка для pystray, которая сохраняется в многоразмерный ICO.

    pystray сам сохраняет PIL-картинку как ICO с одним размером; эта обёртка
    отдаёт контейнер со всеми размерами, чтобы Windows выбрала точную.
    """

    def __init__(self, state: str):
        self._images = {s: draw(state, s) for s in ICO_SIZES}

    def _ico_bytes(self) -> bytes:
        entries = []
        for size in ICO_SIZES:
            buf = io.BytesIO()
            self._images[size].save(buf, format="PNG")
            entries.append((size, buf.getvalue()))

        out = io.BytesIO()
        out.write(struct.pack("<HHH", 0, 1, len(entries)))
        offset = 6 + 16 * len(entries)
        for size, data in entries:
            out.write(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                                  len(data), offset))
            offset += len(data)
        for _, data in entries:
            out.write(data)
        return out.getvalue()

    def save(self, fp, format=None, **kwargs):
        if (format or "").upper() == "ICO":
            fp.write(self._ico_bytes())
        else:
            self._images[max(ICO_SIZES)].save(fp, format=format, **kwargs)


_cache: dict[str, TrayImage] = {}


def tray_image(state: str) -> TrayImage:
    if state not in _cache:
        _cache[state] = TrayImage(state)
    return _cache[state]