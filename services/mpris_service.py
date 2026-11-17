"""Integración MPRIS (Linux) para los escritorios KDE/GNOME.

Requiere ``dbus-next``; si no está instalado, la app sigue funcionando
(necesariamente sin MPRIS).
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

BUS_NAME = "org.mpris.MediaPlayer2.musicplayerpro"
OBJECT_PATH = "/org/mpris/MediaPlayer2"


class MprisService:
    """Expone el reproductor en el bus de sesiones de Linux."""

    def __init__(self, trigger: Callable[[str], None]) -> None:
        self._trigger = trigger
        self._task = None
        self._bus = None
        self._interface = None

    def start(self) -> bool:
        try:
            import asyncio

            from dbus_next.aio import MessageBus
            from dbus_next.service import ServiceInterface, method
        except Exception as exc:  # noqa: BLE001
            logger.debug("dbus-next no está disponible: %s", exc)
            return False

        trigger = self._trigger

        class PlayerInterface(ServiceInterface):
            def __init__(self) -> None:
                super().__init__("org.mpris.MediaPlayer2.Player")

            @method()
            def Play(self) -> None:  # noqa: N802
                trigger("play_pause")

            @method()
            def Pause(self) -> None:  # noqa: N802
                trigger("play_pause")

            @method()
            def PlayPause(self) -> None:  # noqa: N802
                trigger("play_pause")

            @method()
            def Next(self) -> None:  # noqa: N802
                trigger("next")

            @method()
            def Previous(self) -> None:  # noqa: N802
                trigger("prev")

            @method()
            def Stop(self) -> None:  # noqa: N802
                trigger("stop")

        async def run() -> None:
            nonlocal self
            bus = await MessageBus().connect()
            self._bus = bus
            self._interface = PlayerInterface()
            bus.export(BUS_NAME, OBJECT_PATH, self._interface)
            await bus.request_name(BUS_NAME)
            await bus.wait_for_disconnect()

        try:
            self._task = asyncio.new_event_loop().create_task(run())
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo iniciar MPRIS: %s", exc)
            return False
        return True

    def stop(self) -> None:
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._bus = None
        self._task = None
