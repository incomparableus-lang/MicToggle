# -*- coding: utf-8 -*-
"""Быстрая проверка без графики: значки, меню, mute через Core Audio, автозапуск.

Запуск: .venv\\Scripts\\python tests\\smoke.py
"""

import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import icons  # noqa: E402

spec = importlib.util.spec_from_file_location("mic_toggle", ROOT / "mic_toggle.pyw")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

# 1. значки всех состояний собираются в многоразмерный ICO
expected = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128)]
for state in ("off", "on", "live", "error"):
    img = Image.open(io.BytesIO(icons.tray_image(state)._ico_bytes()))
    assert sorted(img.info["sizes"]) == expected, state
print("icons ok")

# 2. микрофон: чтение, запись, возврат исходного состояния
ep = mt.MicEndpoint()
ep.connect()
print("device:", ep.name)
print("id:", ep.id)
original = ep.muted()
print("muted now:", original, "peak:", round(ep.peak(), 4))
ep.set_muted(not original)
print("after toggle:", ep.muted())
assert ep.muted() != original
ep.set_muted(original)
assert ep.muted() == original
print("mic ok")

# 3. приложение и меню собираются, подписи вычисляются
app = mt.App()
for item in app.icon.menu:
    print("menu:", repr(item.text), "| enabled:", item.enabled,
          "| checked:", item.checked, "| default:", item.default)

app.state["muted"] = True
assert app._state_name() == "off"
app.state["muted"] = False
assert app._state_name() == "on"
app.state["live"] = True
assert app._state_name() == "live"
app.state["error"] = True
assert app._state_name() == "error"
print("states ok")

# 4. настройки горячих клавиш: значения по умолчанию и сериализация
default_cfg = mt.hotkeys.Config()
assert default_cfg.key_vk == 0x22 and default_cfg.key_name == "PageDown"
assert default_cfg.mouse is None and default_cfg.mouse_name == "не назначена"
assert default_cfg.swallow is True
cfg = mt.hotkeys.Config.from_dict({"key_vk": 0x78, "key_mods": ["ctrl", "alt"],
                                   "mouse": "x1", "swallow": False})
assert cfg.key_name == "Ctrl+Alt+F9", cfg.key_name
assert cfg.mouse_name == "боковая 1 (назад)"
assert mt.hotkeys.Config.from_dict(cfg.to_dict()) == cfg
print("hotkey config ok")

# 5. автозапуск: запись, чтение, удаление
before = mt.autostart_enabled()
mt.set_autostart(True)
assert mt.autostart_enabled()
mt.set_autostart(False)
assert not mt.autostart_enabled()
if before:
    mt.set_autostart(True)
print("autostart ok, command:", mt.autostart_command())

print("ALL OK")