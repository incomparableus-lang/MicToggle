# -*- coding: utf-8 -*-
"""MicToggle — микрофон в системном трее.

Значок в трее показывает состояние микрофона и цветом сообщает о нём:

    красный, перечёркнут  — микрофон выключен (mute)
    зелёный               — микрофон включён, звука нет
    яркий зелёный + волны — микрофон включён и слышит звук

Левый клик по значку выключает/включает микрофон, правый — меню
с автозапуском и выходом.

Запуск: pythonw mic_toggle.pyw  (или MicToggle.vbs из этой папки)
Разовая команда: pythonw mic_toggle.pyw --toggle
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
import traceback
import winreg
from ctypes import POINTER, cast
from logging.handlers import RotatingFileHandler
from pathlib import Path

import comtypes
import pystray
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation

import icons
import hotkeys
import overlay

APP_NAME = "MicToggle"
MUTEX_NAME = "Local\\MicToggleTray"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

FROZEN = bool(getattr(sys, "frozen", False))   # запущено из собранного exe
SCRIPT = Path(sys.executable).resolve() if FROZEN else Path(__file__).resolve()
APP_DIR = SCRIPT.parent if FROZEN else SCRIPT.parent


def read_version() -> str:
    try:
        return (APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "1.0.0"

POLL = 0.20          # как часто опрашивать микрофон, с
DEVICE_CHECK = 2.0   # как часто проверять, не сменилось ли устройство по умолчанию, с
PEAK_THRESHOLD = 0.015   # порог «в микрофон идёт звук» (шумовой пол около 0.002)
LIVE_ATTACK = 2          # столько замеров подряд выше порога = «звук идёт»
LIVE_HOLD = 0.6          # сколько держать «звук идёт» после последнего пика, с
OVERLAY_FLASH = 5.0      # сколько секунд показывать оверлей после переключения


# ---------------------------------------------------------------- лог

def _log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    folder = Path(base) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "mic-toggle.log"


def setup_logging() -> logging.Logger:
    log = logging.getLogger(APP_NAME)
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(_log_path(), maxBytes=256_000, backupCount=2,
                                      encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.propagate = False
    return log


log = setup_logging()


# ------------------------------------------------------------ микрофон

class MicEndpoint:
    """Микрофон по умолчанию: mute и уровень сигнала через Core Audio."""

    def __init__(self):
        self.id = ""
        self.name = "устройство записи"
        self._vol = None
        self._meter = None

    def connect(self) -> None:
        comtypes.CoInitialize()
        device = AudioUtilities.GetMicrophone()
        if not device:
            raise RuntimeError("устройство записи не найдено")
        self.id = device.GetId()
        self._vol = cast(device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                         POINTER(IAudioEndpointVolume))
        self._meter = cast(device.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                           POINTER(IAudioMeterInformation))
        self.name = self._friendly_name()

    def _friendly_name(self) -> str:
        try:
            for dev in AudioUtilities.GetAllDevices(1):
                if dev.id == self.id and dev.FriendlyName:
                    return dev.FriendlyName
        except Exception:
            log.debug("не удалось прочитать имя устройства", exc_info=True)
        return "устройство записи"

    def muted(self) -> bool:
        return bool(self._vol.GetMute())

    def set_muted(self, value: bool) -> None:
        self._vol.SetMute(1 if value else 0, None)

    def peak(self) -> float:
        return float(self._meter.GetPeakValue())

    def current_default_id(self) -> str:
        device = AudioUtilities.GetMicrophone()
        return device.GetId() if device else ""


def cli_toggle() -> int:
    """Разовая команда --toggle: переключить микрофон и выйти."""
    try:
        mic = MicEndpoint()
        mic.connect()
        new_state = not mic.muted()
        mic.set_muted(new_state)
        log.info("--toggle: микрофон %s", "выключен" if new_state else "включён")
        return 0
    except Exception:
        log.error("--toggle: ошибка\n%s", traceback.format_exc())
        return 1


# ------------------------------------------------------------ автозапуск

def _pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def autostart_command() -> str:
    if FROZEN:
        return f'"{sys.executable}"'
    return f'"{_pythonw()}" "{SCRIPT}"'


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
            log.info("автозапуск включён: %s", autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            log.info("автозапуск выключен")


# ------------------------------------------------------------ значок в трее

NOTIFY_SETTINGS = r"Control Panel\NotifyIconSettings"


def promote_tray_icon() -> bool:
    """Закрепить свой значок на панели задач.

    Windows 11 прячет новые значки в «шторку» ^. Записи живут в
    HKCU\\Control Panel\\NotifyIconSettings по ExecutablePath. Ставим
    IsPromoted=1 только если его там ещё нет — выбор пользователя,
    снятый вручную (0), не перебиваем.

    :return: True, если реестр пришлось править (значок надо перерегистрировать)
    """
    exe = str(Path(sys.executable).resolve()).lower()
    changed = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_SETTINGS) as root:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(root, name) as entry:
                        path = winreg.QueryValueEx(entry, "ExecutablePath")[0]
                        try:
                            winreg.QueryValueEx(entry, "IsPromoted")
                            continue          # значение уже есть — не трогаем
                        except FileNotFoundError:
                            pass
                except OSError:
                    continue
                if path.lower() != exe:
                    continue
                try:
                    with winreg.OpenKey(root, name, 0, winreg.KEY_SET_VALUE) as writable:
                        winreg.SetValueEx(writable, "IsPromoted", 0, winreg.REG_DWORD, 1)
                    changed = True
                except OSError:
                    log.debug("не удалось закрепить значок", exc_info=True)
    except OSError:
        pass
    return changed


# ------------------------------------------------------------ приложение

class App:
    def __init__(self):
        self.state = {"muted": None, "live": False, "error": False, "device": ""}
        self._mic = None
        self._pending_toggle = False
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self.cfg = hotkeys.load_config()
        self._capture_deadline = 0.0
        self._overlay_test_until = 0.0
        self._overlay_flash_until = 0.0
        self.hooks = hotkeys.Hooks(lambda: self.cfg, self._on_hotkey,
                                   self._on_captured, logger=log)
        self.overlay = overlay.Overlay(self._overlay_request, logger=log)
        self.icon = pystray.Icon(
            APP_NAME,
            icon=icons.tray_image("error"),
            title=self._tooltip("error"),
            menu=self._build_menu(),
        )

    # ---- подписи

    def _state_name(self) -> str:
        if self.state["error"]:
            return "error"
        if self.state["muted"] is None:
            return "error"
        if self.state["muted"]:
            return "off"
        return "live" if self.state["live"] else "on"

    def _tooltip(self, state: str) -> str:
        if self.hooks.capture_kind:
            return ("Жду нажатия клавиши… (Esc — отмена)"
                    if self.hooks.capture_kind == "key"
                    else "Жду нажатия кнопки мыши… (Esc — отмена)")
        key = self.cfg.key_name
        hot = f" · {key}" if self.cfg.key_vk is not None else ""
        text = {
            "off": "Микрофон выключен — клик, чтобы включить",
            "on": "Микрофон включён — клик, чтобы выключить",
            "live": "Микрофон включён, слышен звук — клик, чтобы выключить",
            "error": "Микрофон недоступен — клик, чтобы попробовать снова",
        }[state]
        return (text + hot)[:120]

    def _toggle_text(self) -> str:
        if self.state["muted"] is None:
            return "Включить / выключить микрофон"
        return "Включить микрофон" if self.state["muted"] else "Выключить микрофон"

    # ---- меню

    def _key_item_text(self) -> str:
        if self.hooks.capture_kind == "key":
            return "Нажмите клавишу…"
        return f"Клавиатура: {self.cfg.key_name}"

    def _mouse_item_text(self) -> str:
        if self.hooks.capture_kind == "mouse":
            return "Нажмите кнопку мыши…"
        return f"Мышь: {self.cfg.mouse_name}"

    def _build_menu(self):
        key_menu = pystray.Menu(
            pystray.MenuItem("Назначить…", self._begin_capture_key),
            pystray.MenuItem("Отключить", self._disable_key,
                             enabled=lambda item: self.cfg.key_vk is not None),
        )
        mouse_menu = pystray.Menu(
            pystray.MenuItem("Назначить…", self._begin_capture_mouse),
            pystray.MenuItem("Отключить", self._disable_mouse,
                             enabled=lambda item: self.cfg.mouse is not None),
        )
        corner_menu = pystray.Menu(*[
            pystray.MenuItem(
                overlay.CORNER_LABELS[c], self._corner_setter(c), radio=True,
                checked=lambda item, c=c: self.cfg.overlay_corner == c)
            for c in overlay.CORNERS
        ])
        overlay_menu = pystray.Menu(
            pystray.MenuItem("Показывать", self._toggle_overlay,
                             checked=lambda item: self.cfg.overlay),
            pystray.MenuItem("5 секунд после переключения", self._toggle_overlay_after_toggle,
                             checked=lambda item: self.cfg.overlay_after_toggle,
                             enabled=lambda item: self.cfg.overlay),
            pystray.MenuItem("Только когда микрофон выключен", self._toggle_overlay_muted,
                             checked=lambda item: self.cfg.overlay_only_muted,
                             enabled=lambda item: self.cfg.overlay),
            pystray.MenuItem("Только в полноэкранных приложениях",
                             self._toggle_overlay_fullscreen,
                             checked=lambda item: self.cfg.overlay_only_fullscreen,
                             enabled=lambda item: self.cfg.overlay),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Положение", corner_menu,
                             enabled=lambda item: self.cfg.overlay),
            pystray.MenuItem("Показать на 5 секунд", self._overlay_test),
        )
        return pystray.Menu(
            pystray.MenuItem(lambda item: self._toggle_text(), self._request_toggle,
                             default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self.state["device"] or "устройство записи",
                             None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self._key_item_text(), key_menu),
            pystray.MenuItem("Перехватывать клавишу (не отдавать приложениям)",
                             self._toggle_swallow,
                             checked=lambda item: self.cfg.swallow,
                             enabled=lambda item: self.cfg.key_vk is not None),
            pystray.MenuItem(lambda item: self._mouse_item_text(), mouse_menu),
            pystray.MenuItem(lambda item: "Оверлей в играх: "
                             + ("вкл" if self.cfg.overlay else "выкл"), overlay_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Запускать при входе в Windows", self._toggle_autostart,
                             checked=lambda item: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"{APP_NAME} {read_version()}",
                             None, enabled=False),
            pystray.MenuItem("Выход", self._quit),
        )

    def _request_toggle(self, icon=None, item=None):
        """Клик по значку/пункту меню: переключаем в фоновом потоке."""
        self._pending_toggle = True
        self._wake.set()

    # ---- горячие клавиши

    def _on_hotkey(self):
        """Сработала горячая клавиша (вызов из потока хуков)."""
        log.info("горячая клавиша: %s", self.cfg.key_name if self.cfg.key_vk else self.cfg.mouse_name)
        self._request_toggle()

    def _notify(self, message: str) -> None:
        try:
            self.icon.notify(message, APP_NAME)
        except Exception:
            log.debug("уведомление не показано", exc_info=True)

    def _refresh_ui(self) -> None:
        """Обновить подписи меню и подсказку (после смены настроек)."""
        try:
            self.icon.update_menu()
            self.icon.title = self._tooltip(self._state_name())[:120]
        except Exception:
            log.error("не удалось обновить меню\n%s", traceback.format_exc())

    def _begin_capture(self, kind: str) -> None:
        self.hooks.begin_capture(kind)
        self._capture_deadline = time.monotonic() + 10
        self.icon.title = self._tooltip(self._state_name())[:120]
        try:
            self.icon.update_menu()
        except Exception:
            log.debug("меню не обновилось", exc_info=True)
        self._notify("Нажмите клавишу…" if kind == "key"
                     else "Нажмите кнопку мыши…\nEsc — отмена")
        log.info("ожидание назначения: %s", kind)

    def _begin_capture_key(self, icon=None, item=None):
        self._begin_capture("key")

    def _begin_capture_mouse(self, icon=None, item=None):
        self._begin_capture("mouse")

    def _on_captured(self, result) -> None:
        """Результат назначения из потока хуков; None — отмена."""
        self._capture_deadline = 0.0
        if result is None:
            log.info("назначение отменено")
            self._refresh_ui()
            self._notify("Назначение отменено")
            return

        kind = result[0]
        if kind == "key":
            self.cfg.key_vk = int(result[1])
            self.cfg.key_mods = list(result[2])
            text = self.cfg.key_name
            log.info("назначена клавиша: %s", text)
        else:
            self.cfg.mouse = result[1]
            text = self.cfg.mouse_name
            log.info("назначена кнопка мыши: %s", text)

        self._save_config()
        self._refresh_ui()
        self._notify(f"Назначено: {text}")

    def _save_config(self) -> None:
        try:
            hotkeys.save_config(self.cfg)
        except OSError:
            log.error("не удалось сохранить настройки\n%s", traceback.format_exc())

    def _disable_key(self, icon=None, item=None):
        self.cfg.key_vk = None
        self.cfg.key_mods = []
        self._save_config()
        self._refresh_ui()
        log.info("клавиатурная горячая клавиша отключена")

    def _disable_mouse(self, icon=None, item=None):
        self.cfg.mouse = None
        self._save_config()
        self._refresh_ui()
        log.info("кнопка мыши отключена")

    def _toggle_swallow(self, icon=None, item=None):
        self.cfg.swallow = not self.cfg.swallow
        self._save_config()
        self._refresh_ui()
        log.info("перехват клавиши: %s", self.cfg.swallow)

    # ---- оверлей

    def _toggle_overlay(self, icon=None, item=None):
        self.cfg.overlay = not self.cfg.overlay
        self._save_config()
        self._refresh_ui()
        self.overlay.tick()
        log.info("оверлей: %s", "включён" if self.cfg.overlay else "выключен")

    def _toggle_overlay_after_toggle(self, icon=None, item=None):
        self.cfg.overlay_after_toggle = not self.cfg.overlay_after_toggle
        self._save_config()
        self._refresh_ui()
        self.overlay.tick()
        log.info("оверлей после переключения: %s", self.cfg.overlay_after_toggle)

    def _toggle_overlay_muted(self, icon=None, item=None):
        self.cfg.overlay_only_muted = not self.cfg.overlay_only_muted
        self._save_config()
        self._refresh_ui()
        self.overlay.tick()
        log.info("оверлей только при выключенном микрофоне: %s", self.cfg.overlay_only_muted)

    def _toggle_overlay_fullscreen(self, icon=None, item=None):
        self.cfg.overlay_only_fullscreen = not self.cfg.overlay_only_fullscreen
        self._save_config()
        self._refresh_ui()
        self.overlay.tick()
        log.info("оверлей только в полноэкранных приложениях: %s",
                 self.cfg.overlay_only_fullscreen)

    def _corner_setter(self, corner: str):
        def set_corner(icon=None, item=None):
            self.cfg.overlay_corner = corner
            self._save_config()
            self._refresh_ui()
            self.overlay.tick()
            log.info("положение оверлея: %s", overlay.CORNER_LABELS[corner])
        return set_corner

    def _overlay_test(self, icon=None, item=None):
        self._overlay_test_until = time.monotonic() + 5
        self.overlay.tick()
        log.info("оверлей: показ на 5 секунд")

    def _overlay_request(self):
        """Что и где показывать: (state, visible, corner, rect)."""
        state = self._state_name()
        corner = self.cfg.overlay_corner
        now = time.monotonic()

        if not self.cfg.overlay:
            return state, False, corner, None

        # проверка вида из меню
        if now < self._overlay_test_until:
            return state, True, corner, overlay.primary_rect()

        # вспышка после переключения микрофона — показываем везде
        if now < self._overlay_flash_until:
            rect = overlay.foreground_fullscreen() or overlay.primary_rect()
            return state, True, corner, rect

        if self.cfg.overlay_only_muted and state != "off":
            return state, False, corner, None

        if self.cfg.overlay_only_fullscreen:
            rect = overlay.foreground_fullscreen()
        else:
            rect = overlay.primary_rect()
        return state, rect is not None, corner, rect

    def _check_capture_timeout(self, now: float) -> None:
        if self._capture_deadline and now > self._capture_deadline \
                and self.hooks.capture_kind:
            self._capture_deadline = 0.0
            self.hooks.cancel_capture()
            log.info("время ожидания назначения вышло")
            self._refresh_ui()
            self._notify("Время вышло — назначение отменено")

    def _toggle_autostart(self, icon=None, item=None):
        try:
            set_autostart(not autostart_enabled())
        except OSError:
            log.error("не удалось изменить автозапуск\n%s", traceback.format_exc())

    def _quit(self, icon=None, item=None):
        log.info("выход")
        self._stopping.set()
        self._wake.set()
        try:
            self.hooks.stop()
        except Exception:
            log.debug("хуки не остановились", exc_info=True)
        try:
            self.overlay.stop()
        except Exception:
            log.debug("оверлей не остановился", exc_info=True)
        self.icon.stop()

    # ---- отрисовка состояния

    def _apply_state(self, state: str) -> None:
        try:
            self.icon.icon = icons.tray_image(state)
            if not self.hooks.capture_kind:
                self.icon.title = self._tooltip(state)[:120]
            # подпись пункта меню зависит от mute — перестраиваем меню
            if state in ("off", "on"):
                self.icon.update_menu()
        except Exception:
            log.error("не удалось обновить значок\n%s", traceback.format_exc())

    # ---- фоновый поток

    def _attach(self) -> None:
        """Подключиться к микрофону по умолчанию (или переподключиться)."""
        if self._mic is None:
            self._mic = MicEndpoint()
        self._mic.connect()
        self.state["device"] = self._mic.name

    def _monitor(self) -> None:
        comtypes.CoInitialize()
        live_until = 0.0
        above = 0
        last_state = None
        next_device_check = 0.0
        last_muted = None

        while not self._stopping.is_set():
            self._wake.wait(POLL)
            self._wake.clear()
            if self._stopping.is_set():
                break

            try:
                if self._pending_toggle:
                    self._pending_toggle = False
                    if self._mic is None:
                        self._attach()
                    target = not self._mic.muted()
                    self._mic.set_muted(target)
                    log.info("микрофон %s", "выключен" if target else "включён")

                if self._mic is None:
                    self._attach()

                now = time.monotonic()
                self._check_capture_timeout(now)
                self.overlay.tick()

                if now >= next_device_check:
                    next_device_check = now + DEVICE_CHECK
                    if self._mic.current_default_id() != self._mic.id:
                        log.info("устройство записи сменилось — переподключаюсь")
                        self._attach()

                muted = self._mic.muted()
                peak = self._mic.peak()
                if peak >= PEAK_THRESHOLD:
                    above += 1
                    if above >= LIVE_ATTACK:
                        live_until = now + LIVE_HOLD
                else:
                    above = 0

                self.state["muted"] = muted
                self.state["error"] = False
                self.state["live"] = (not muted) and (now < live_until)
                state = self._state_name()
            except Exception:
                log.error("ошибка доступа к микрофону\n%s", traceback.format_exc())
                self.state["error"] = True
                self._mic = None
                state = "error"
                next_device_check = 0.0
                time.sleep(DEVICE_CHECK)

            if state != last_state or self.state["muted"] != last_muted:
                if state != last_state:
                    log.info("состояние: %s", state)
                # переключили микрофон — показываем значок на 5 секунд
                if (self.state["muted"] != last_muted and last_muted is not None
                        and self.cfg.overlay and self.cfg.overlay_after_toggle):
                    self._overlay_flash_until = time.monotonic() + OVERLAY_FLASH
                    log.info("оверлей: вспышка %.0f с", OVERLAY_FLASH)
                last_state = state
                last_muted = self.state["muted"]
                self._apply_state(state)

    # ---- запуск

    def _setup(self, icon) -> None:
        icon.visible = True
        log.info("запуск: %s, версия %s, python %s, frozen=%s",
                 SCRIPT, read_version(), sys.version.split()[0], FROZEN)
        threading.Thread(target=self._promote_tray, name="tray-promote", daemon=True).start()
        try:
            self._attach()
            log.info("устройство записи: %s", self.state["device"])
        except Exception:
            log.error("не удалось подключиться при старте\n%s", traceback.format_exc())
            self._mic = None
        log.info("горячие клавиши: клавиатура %s, мышь %s, перехват %s",
                 self.cfg.key_name, self.cfg.mouse_name, self.cfg.swallow)
        if not hotkeys.config_exists():
            self._save_config()
        self.hooks.start()
        self.overlay.start()
        threading.Thread(target=self._monitor, name="mic-monitor", daemon=True).start()

    def run(self) -> None:
        self.icon.run(setup=self._setup)

    def _promote_tray(self) -> None:
        """Через пару секунд после первого показа закрепить значок в трее."""
        time.sleep(2.5)
        try:
            if promote_tray_icon():
                log.info("значок закреплён на панели задач")
                self.icon.visible = False
                time.sleep(0.4)
                self.icon.visible = True
        except Exception:
            log.error("не удалось закрепить значок\n%s", traceback.format_exc())


# ------------------------------------------------------------ точка входа

def _single_instance():
    """Не даём запуститься второму экземпляру; возвращаем хэндл мьютекса."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle


def _set_app_id() -> None:
    """Чтобы уведомления подписывались «MicToggle», а не «Python»."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MicToggle.Tray")
    except Exception:
        log.debug("AppUserModelID не задан", exc_info=True)


def main() -> int:
    if "--toggle" in sys.argv[1:]:
        return cli_toggle()

    _set_app_id()

    mutex = _single_instance()
    if mutex is None:
        log.info("экземпляр уже запущен — выхожу")
        return 0

    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())