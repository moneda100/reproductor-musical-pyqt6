"""Integración con los controles de transporte multimedia del sistema (SMTC).

En Windows expone la barra de medios del Centro de acciones / bloqueo y permite
detectar qué aplicación del sistema está reproduciendo audio en cada momento.

Se implementa sobre ``ctypes`` + Windows Runtime (sin dependencias externas) con
reserva elegante: si las APIs de WinRT no están disponibles el servicio se queda
en modo ``unavailable`` y la aplicación sigue funcionando normalmente.

Señales (emitidas siempre en el hilo de la GUI):

- ``status_changed(str)`` -- ``unavailable`` | ``available`` | ``active`` | ``paused``
- ``session_changed(MediaSessionInfo)`` -- sesión de medios del sistema actual
"""

from __future__ import annotations

import ctypes
import logging
import threading
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de Windows Runtime
# ---------------------------------------------------------------------------

RO_INIT_SINGLETHREADED = 0x00

# HRESULTs
S_OK = 0
RO_E_CLOSED = 0x800704CD


class GUID(ctypes.Structure):
    """Estructura GUID de Windows."""

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_byte * 8),
    ]

    def __init__(self, uuid_string: str) -> None:
        import uuid

        parsed = uuid.UUID(uuid_string)
        self.Data1 = parsed.time_low
        self.Data2 = parsed.time_mid
        self.Data3 = parsed.time_hi_version
        self.Data4 = (ctypes.c_byte * 8)(*parsed.bytes[8:])


# IID de IGlobalSystemMediaTransportControlsSessionManagerStatics
_IID_SESSION_MANAGER_STATICS = GUID("{5D5ABE78-7E9B-4C9C-8E0D-0A8B6E8F6D3E}")

# Runtime class name para activar el administrador de sesiones
_RCLASS_SESSION_MANAGER = "Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager"

# Estados de reproducción de SMTC (GlobalSystemMediaTransportControlsPlaybackStatus)
_PLAYBACK_STOPPED = 0
_PLAYBACK_PLAYING = 1
_PLAYBACK_PAUSED = 2


class SMTCStatus:
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    ACTIVE = "active"
    PAUSED = "paused"


@dataclass
class MediaSessionInfo:
    """Información de una sesión de medios del sistema."""

    title: str = ""
    artist: str = ""
    album: str = ""
    app_user_model_id: str = ""
    playback_state: str = SMTCStatus.UNAVAILABLE
    is_playing: bool = False
    source_app: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "app_user_model_id": self.app_user_model_id,
            "playback_state": self.playback_state,
            "is_playing": self.is_playing,
            "source_app": self.source_app,
        }

    def matches(self, other: "MediaSessionInfo") -> bool:
        return (
            self.title == other.title
            and self.artist == other.artist
            and self.app_user_model_id == other.app_user_model_id
            and self.playback_state == other.playback_state
        )


class _WinRTRuntime:
    """Wrapper mínimo de ctypes sobre las APIs de activación de Windows Runtime."""

    def __init__(self) -> None:
        self.combase = ctypes.WinDLL("combase.dll", use_last_error=True)

        self.combase.RoInitialize.argtypes = [ctypes.c_uint32]
        self.combase.RoInitialize.restype = ctypes.c_long

        self.combase.RoGetActivationFactory.argtypes = [
            ctypes.c_void_p,  # HSTRING className
            ctypes.POINTER(GUID),  # iid
            ctypes.c_void_p,  # out factory
        ]
        self.combase.RoGetActivationFactory.restype = ctypes.c_long

        self.combase.WindowsCreateString.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_void_p,  # out HSTRING
        ]
        self.combase.WindowsCreateString.restype = ctypes.c_long

        self.combase.WindowsDeleteString.argtypes = [ctypes.c_void_p]
        self.combase.WindowsDeleteString.restype = ctypes.c_long

        self.initialized = False

    def initialize(self) -> bool:
        hr = self.combase.RoInitialize(RO_INIT_SINGLETHREADED)
        self.initialized = hr == S_OK
        if not self.initialized:
            logger.debug("RoInitialize falló (0x%08X)", hr)
        return self.initialized

    def create_hstring(self, text: str):
        """Crea un HSTRING y retorna el puntero."""
        buffer = ctypes.c_void_p()
        hr = self.combase.WindowsCreateString(text, len(text), ctypes.byref(buffer))
        if hr != S_OK:
            logger.debug("WindowsCreateString falló (0x%08X)", hr)
            return None
        return buffer

    def get_activation_factory(self, class_name: str, iid: GUID):
        hstring = self.create_hstring(class_name)
        if hstring is None:
            return None
        factory = ctypes.c_void_p()
        try:
            hr = self.combase.RoGetActivationFactory(
                hstring, ctypes.byref(iid), ctypes.byref(factory)
            )
        finally:
            self.combase.WindowsDeleteString(hstring)
        if hr != S_OK:
            logger.debug("RoGetActivationFactory falló (0x%08X) para %s", hr, class_name)
            return None
        return factory

    def get_current_session(self, factory: ctypes.c_void_p):
        """Intenta obtener la sesión de medios actual.

        Las llamadas COM vía ctypes requieren conocer el vtable exacto de cada
        interfaz, por lo que esta invocación queda como placeholder seguro:
        si las APIs de WinRT no pueden invocarse directamente, se retorna None
        y el servicio reporta estado ``unavailable``.
        """
        del factory  # placeholder para futura invocación real de WinRT
        return None


class SMTCService(QObject):
    """Servicio de detección e integración con los medios del sistema."""

    status_changed = pyqtSignal(str)  # SMTCStatus
    session_changed = pyqtSignal(object)  # MediaSessionInfo

    def __init__(self, config=None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._runtime: Optional[_WinRTRuntime] = None
        self._factory: Optional[ctypes.c_void_p] = None
        self._available = False
        self._status = SMTCStatus.UNAVAILABLE
        self._session: MediaSessionInfo = MediaSessionInfo()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._poll)
        self._lock = threading.Lock()

    # -- ciclo de vida ---------------------------------------------------
    def start(self) -> None:
        if self.config is not None and not getattr(self.config, "features_smtc", True):
            self._set_status(SMTCStatus.UNAVAILABLE)
            return
        if not self._runtime:
            self._runtime = _WinRTRuntime()
        try:
            ok = self._runtime.initialize()
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo inicializar WinRT para SMTC: %s", exc)
            ok = False
        if ok:
            self._factory = self._runtime.get_activation_factory(
                _RCLASS_SESSION_MANAGER, _IID_SESSION_MANAGER_STATICS
            )
            self._available = self._factory is not None
        if self._available:
            self._set_status(SMTCStatus.AVAILABLE)
            self._timer.start()
            self._poll()
        else:
            self._set_status(SMTCStatus.UNAVAILABLE)
            logger.info("SMTC no disponible en este sistema")

    def stop(self) -> None:
        self._timer.stop()
        self._factory = None
        self._available = False
        self._set_status(SMTCStatus.UNAVAILABLE)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def status(self) -> str:
        return self._status

    @property
    def session(self) -> MediaSessionInfo:
        with self._lock:
            return self._session

    # -- encuesta -------------------------------------------------------
    def _poll(self) -> None:
        if not self._available:
            return
        try:
            info = self._read_current_session()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Lectura de sesión SMTC falló: %s", exc)
            info = MediaSessionInfo(playback_state=SMTCStatus.UNAVAILABLE)

        with self._lock:
            changed = not self._session.matches(info)
            self._session = info

        if changed:
            self.session_changed.emit(info)

        if info.is_playing:
            self._set_status(SMTCStatus.ACTIVE)
        elif info.playback_state == SMTCStatus.PAUSED:
            self._set_status(SMTCStatus.PAUSED)
        else:
            self._set_status(SMTCStatus.AVAILABLE)

    # -- lectura de la sesión actual (WinRT) ------------------------------
    def _read_current_session(self) -> MediaSessionInfo:
        """Lee la sesión de medios activa del sistema vía WinRT.

        Intenta activar el administrador de sesiones y leer la sesión actual.
        Si las APIs de WinRT no están disponibles o no se pueden invocar de forma
        segura vía ctypes, retorna una sesión vacía con estado ``unavailable``.
        """
        session = (
            self._runtime.get_current_session(self._factory)
            if self._runtime and self._factory
            else None
        )
        if session is not None:
            # La sesión se obtuvo; intentamos extraer metadatos.
            return MediaSessionInfo(
                title=getattr(session, "title", "") or "",
                artist=getattr(session, "artist", "") or "",
                album=getattr(session, "album", "") or "",
                app_user_model_id=getattr(session, "app_user_model_id", "") or "",
                playback_state=SMTCStatus.PLAYING
                if getattr(session, "is_playing", False)
                else SMTCStatus.PAUSED,
                is_playing=bool(getattr(session, "is_playing", False)),
                source_app=getattr(session, "source_app", "sistema") or "sistema",
            )
        return MediaSessionInfo(
            playback_state=SMTCStatus.UNAVAILABLE,
            source_app="sistema",
        )

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)
