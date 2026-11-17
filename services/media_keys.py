"""Teclas multimedia del sistema.

- Windows: ``RegisterHotKey`` vía ``ctypes`` (sin dependencias externas).
- macOS: no hay soporte nativo trivial; se usa el registro de accesibilidad
  cuando está disponible y se ignora en caso contrario.
- Linux: **MPRIS** sobre D-Bus (``dbus-next``) si está disponible.

En todas las plataformas la app sigue funcionando con los atajos de teclado
internos si el soporte del SO no está disponible.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
import sys
from typing import Callable

from PyQt6.QtCore import QCoreApplication

logger = logging.getLogger(__name__)

# Identificadores de hotkey únicos por servicio (evita conflictos si hay varias
# ventanas abiertas en el mismo proceso).
_HOTKEY_IDS = itertools.count(0xB000)

# Identificadores de hotkey de Windows (MOD_NOREPEAT = 0x4000)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2


class MediaKeyService:
    """Registro de teclas multimedia del sistema operativo."""

    def __init__(self, parent=None) -> None:
        self._parent = parent
        self._registered: list[int] = []
        self._native_event_filter = None
        self._callbacks: dict[str, Callable] = {}
        self._available = False

    # -- callbacks -------------------------------------------------------
    def register(self, action: str, callback: Callable) -> None:
        """Asocia una acción ('play_pause', 'next', 'prev', 'stop') a un callback."""
        self._callbacks[action] = callback

    def trigger(self, action: str) -> None:
        callback = self._callbacks.get(action)
        if callback is not None:
            try:
                callback()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error en la acción multimedia '%s': %s", action, exc)

    # -- ciclo de vida -----------------------------------------------------
    def start(self) -> bool:
        """Registra las teclas. Devuelve ``True`` si el SO las admite."""
        if sys.platform == "win32":
            self._available = self._start_windows()
        elif sys.platform.startswith("linux"):
            self._available = self._start_mpris()
        else:
            self._available = False
        if not self._available:
            logger.info("Teclas multimedia del sistema no disponibles en esta plataforma")
        return self._available

    def stop(self) -> None:
        if sys.platform == "win32":
            self._stop_windows()
        elif sys.platform.startswith("linux"):
            self._stop_mpris()
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    # -- Windows ------------------------------------------------------------
    def _start_windows(self) -> bool:
        try:
            import ctypes.wintypes

            from PyQt6.QtCore import QAbstractNativeEventFilter
        except Exception:  # pragma: no cover
            return False

        user32 = ctypes.windll.user32
        hotkeys = [
            (MOD_CONTROL, VK_MEDIA_PLAY_PAUSE, "play_pause"),
            (MOD_CONTROL, VK_MEDIA_NEXT_TRACK, "next"),
            (MOD_CONTROL, VK_MEDIA_PREV_TRACK, "prev"),
            (MOD_CONTROL, VK_MEDIA_STOP, "stop"),
        ]
        service = self

        class Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):  # noqa: N802
                if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                    if msg.message == WM_HOTKEY:
                        for hotkey_id, action in service._hotkey_actions.items():
                            if hotkey_id == msg.wParam:
                                service.trigger(action)
                                return True, 0
                return False, 0

        self._hotkey_actions: dict[int, str] = {}
        next_id = next(_HOTKEY_IDS)
        ok = True
        for modifiers, key, action in hotkeys:
            if user32.RegisterHotKey(None, next_id, modifiers | MOD_NOREPEAT, key):
                self._hotkey_actions[next_id] = action
                self._registered.append(next_id)
                next_id = next(_HOTKEY_IDS)
            else:
                ok = False
        if not self._registered:
            return False
        self._native_event_filter = Filter()
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._native_event_filter)
        logger.info("Teclas multimedia registradas en Windows: %d", len(self._registered))
        return ok

    def _stop_windows(self) -> None:
        app = QCoreApplication.instance()
        if app is not None and self._native_event_filter is not None:
            # Sin esto, el filtro queda colgando en la aplicación y Qt aborta
            # al recibir el siguiente evento nativo.
            app.removeNativeEventFilter(self._native_event_filter)
        self._native_event_filter = None
        try:
            user32 = ctypes.windll.user32
            for hotkey_id in self._registered:
                user32.UnregisterHotKey(None, hotkey_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudieron desregistrar las hotkeys: %s", exc)
        self._registered.clear()

    # -- Linux (MPRIS) -------------------------------------------------------
    def _start_mpris(self) -> bool:
        try:
            from services.mpris_service import MprisService
        except Exception as exc:  # noqa: BLE001
            logger.debug("MPRIS no disponible: %s", exc)
            return False
        self._mpris = MprisService(self.trigger)
        return self._mpris.start()

    def _stop_mpris(self) -> None:
        mpris = getattr(self, "_mpris", None)
        if mpris is not None:
            mpris.stop()
