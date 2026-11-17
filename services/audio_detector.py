"""Detector de sesiones de audio del sistema (alternativa a SMTC).

Cuando SMTC / WinRT no está disponible en el equipo, este servicio usa la API
de Core Audio de Windows (``mmdevapi.dll`` vía ``ctypes``, sin dependencias
externas) para detectar si hay aplicaciones reproduciendo audio y cuáles son.

Se implementa con reserva elegante: si las APIs de Core Audio no se pueden
cargar o invocar, el servicio se queda en modo ``unavailable`` y la aplicación
sigue funcionando normalmente.

Señales (emitidas siempre en el hilo de la GUI):

- ``status_changed(str)`` -- ``unavailable`` | ``available`` | ``active``
- ``session_changed(AudioSessionInfo)`` -- sesión de audio detectada
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de la API de Core Audio de Windows (mmdevapi.dll)
# ---------------------------------------------------------------------------


class GUID(ctypes.Structure):
    """Estructura GUID de Windows (idéntica a la de services/smtc_service.py)."""

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


# CLSID del enumerador de dispositivos de multimedia
CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
# IID de IMMDeviceEnumerator
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
# IID de IAudioSessionManager2
IID_IAudioSessionManager2 = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")

# Contexto de activación COM
CLSCTX_ALL = 0x17

# DataFlow para GetDefaultAudioEndpoint: eRender = 0 (salida de audio)
EDataRender = 0
# Rol del dispositivo: eConsole = 0 (reproducción normal de usuario)
ERoleConsole = 0

# Estados de sesión de audio (AudioSessionState)
AUDIO_SESSION_STATE_INACTIVE = 0
AUDIO_SESSION_STATE_ACTIVE = 1
AUDIO_SESSION_STATE_EXPIRED = 2

# Índices de vtable (después de los 3 métodos de IUnknown:
# QueryInterface, AddRef, Release). Cada entrada es un puntero de 8 bytes.
_VTABLE = {
    # IMMDeviceEnumerator (después de IUnknown)
    "GetDefaultAudioEndpoint": 5,
    # IMMDevice (después de IUnknown)
    "Activate": 3,
    # IAudioSessionManager2 (hereda de IAudioSessionManager, que añade 6
    # métodos a IUnknown; GetSessionEnumerator está en el índice 9)
    "GetSessionEnumerator": 9,
    # IAudioSessionEnumerator (después de IUnknown)
    "GetCount": 3,
    "GetSession": 4,
    # IAudioSessionControl2 (hereda de IAudioSessionControl, que añade 2 a
    # IUnknown; GetState está en 3, GetDisplayName en 4; GetProcessId en 10)
    "GetState": 3,
    "GetDisplayName": 4,
    "GetProcessId": 10,
}


def _vtable_index(method_name: str) -> int:
    return _VTABLE[method_name]


class _ComPtr:
    """Wrapper mínimo sobre un puntero de interfaz COM para llamadas vtable."""

    def __init__(self, ptr: int) -> None:
        self._ptr = ptr

    @property
    def ptr(self) -> int:
        return self._ptr

    def call(self, method_name: str, restype, argtypes, *args) -> object:
        """Llama a un método de la vtable por su nombre."""
        index = _vtable_index(method_name)
        vtable = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
        func_ptr = vtable[0][index]
        func = ctypes.cast(
            func_ptr,
            ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes),
        )
        return func(self._ptr, *args)


class _WinRTAudio:
    """Wrapper de ctypes sobre mmdevapi.dll y ole32.dll."""

    def __init__(self) -> None:
        self.ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        self.mmdevapi = ctypes.WinDLL("mmdevapi.dll", use_last_error=True)

        self.ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        self.ole32.CoInitialize.restype = ctypes.HRESULT
        self.ole32.CoCreateInstance.argtypes = [
            GUID,  # rclsid
            ctypes.c_void_p,  # pUnkOuter
            ctypes.c_ulong,  # dwClsContext
            GUID,  # riid
            ctypes.POINTER(ctypes.c_void_p),  # ppv
        ]
        self.ole32.CoCreateInstance.restype = ctypes.HRESULT
        self.ole32.CoUninitialize.argtypes = []
        self.ole32.CoUninitialize.restype = None

        self.initialized = False

    def initialize(self) -> bool:
        try:
            hr = self.ole32.CoInitialize(None)
            self.initialized = hr >= 0  # S_OK = 0, S_FALSE = 1
            if not self.initialized:
                logger.debug("CoInitialize devolvió 0x%08X", hr)
            return self.initialized
        except Exception as exc:  # noqa
            logger.debug("CoInitialize falló: %s", exc)
            return False

    def create_instance(self, clsid: GUID, iid: GUID) -> Optional[int]:
        """Crea una instancia COM y retorna el puntero de la interfaz."""
        ptr = ctypes.c_void_p()
        try:
            hr = self.ole32.CoCreateInstance(clsid, None, CLSCTX_ALL, iid, ctypes.byref(ptr))
            if hr < 0:
                logger.debug("CoCreateInstance falló (0x%08X) para %s", hr, str(clsid))
                return None
            return ptr.value
        except Exception as exc:  # noqa
            logger.debug("CoCreateInstance excepción: %s", exc)
            return None

    def uninitialize(self) -> None:
        if self.initialized:
            try:
                self.ole32.CoUninitialize()
            except Exception:  # noqa
                pass
            self.initialized = False


class AudioSessionInfo:
    """Información de una sesión de audio detectada."""

    def __init__(
        self,
        process_id: int = 0,
        process_name: str = "",
        display_name: str = "",
        state: int = AUDIO_SESSION_STATE_INACTIVE,
        is_playing: bool = False,
    ) -> None:
        self.process_id = process_id
        self.process_name = process_name
        self.display_name = display_name
        self.state = state
        self.is_playing = bool(is_playing)

    @property
    def status(self) -> str:
        if self.is_playing:
            return "active"
        return "inactive"

    def as_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "process_name": self.process_name,
            "display_name": self.display_name,
            "state": self.state,
            "is_playing": self.is_playing,
        }

    def matches(self, other: "AudioSessionInfo") -> bool:
        return (
            self.process_id == other.process_id
            and self.process_name == other.process_name
            and self.state == other.state
        )


class AudioDetector(QObject):
    """Detecta aplicaciones que están reproduciendo audio en el sistema.

    Usa la API de Core Audio de Windows (mmdevapi) como alternativa a SMTC
    cuando WinRT no está disponible.
    """

    status_changed = pyqtSignal(str)  # "unavailable" | "available" | "active"
    session_changed = pyqtSignal(object)  # AudioSessionInfo

    def __init__(self, config=None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._com: Optional[_WinRTAudio] = None
        self._enumerator_ptr: Optional[int] = None
        self._available = False
        self._status = "unavailable"
        self._session = AudioSessionInfo()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._poll)
        self._lock = threading.Lock()

    # -- ciclo de vida ---------------------------------------------------
    def start(self) -> None:
        if self.config is not None and not getattr(self.config, "features_audio_detection", True):
            self._set_status("unavailable")
            return

        try:
            self._com = _WinRTAudio()
            ok = self._com.initialize()
        except Exception as exc:  # noqa
            logger.warning("No se pudo inicializar Core Audio: %s", exc)
            ok = False

        if ok:
            ptr = self._com.create_instance(CLSID_MMDeviceEnumerator, IID_IMMDeviceEnumerator)
            if ptr:
                self._enumerator_ptr = ptr
                self._available = True

        if self._available:
            self._set_status("available")
            self._timer.start()
            self._poll()
        else:
            self._set_status("unavailable")
            logger.info("Detector de audio no disponible en este sistema")

    def stop(self) -> None:
        self._timer.stop()
        if self._enumerator_ptr is not None:
            try:
                _ComPtr(self._enumerator_ptr).call("Release", ctypes.HRESULT, [])
            except Exception:  # noqa
                pass
            self._enumerator_ptr = None
        if self._com is not None:
            self._com.uninitialize()
            self._com = None
        self._available = False
        self._set_status("unavailable")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def status(self) -> str:
        return self._status

    @property
    def session(self) -> AudioSessionInfo:
        with self._lock:
            return self._session

    # -- encuesta -------------------------------------------------------
    def _poll(self) -> None:
        if not self._available or self._com is None:
            return
        try:
            info = self._read_active_session()
        except Exception as exc:  # noqa
            logger.debug("Lectura de sesión de audio falló: %s", exc)
            info = AudioSessionInfo(state=AUDIO_SESSION_STATE_INACTIVE)

        with self._lock:
            changed = not self._session.matches(info)
            self._session = info

        if changed:
            self.session_changed.emit(info)

        if info.is_playing:
            self._set_status("active")
        else:
            self._set_status("available")

    # -- lectura de la sesión activa ------------------------------------
    def _read_active_session(self) -> AudioSessionInfo:
        """Lee la sesión de audio activa del dispositivo de salida predeterminado."""
        if self._com is None or self._enumerator_ptr is None:
            return AudioSessionInfo()

        enumerator = _ComPtr(self._enumerator_ptr)

        # Obtener el dispositivo de audio de salida predeterminado (eRender, eConsole)
        device_ptr = ctypes.c_void_p()
        try:
            hr = enumerator.call(
                "GetDefaultAudioEndpoint",
                ctypes.HRESULT,
                [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
                EDataRender,
                ERoleConsole,
                ctypes.byref(device_ptr),
            )
        except Exception as exc:  # noqa
            logger.debug("GetDefaultAudioEndpoint falló: %s", exc)
            return AudioSessionInfo()

        if hr < 0 or not device_ptr.value:
            return AudioSessionInfo()

        device = _ComPtr(device_ptr.value)

        # Activar IAudioSessionManager2 sobre el dispositivo
        mgr_ptr = ctypes.c_void_p()
        try:
            hr = device.call(
                "Activate",
                ctypes.HRESULT,
                [
                    GUID,  # riid
                    ctypes.c_ulong,  # dwClsContext
                    ctypes.c_void_p,  # pActivationParams (None)
                    ctypes.POINTER(ctypes.c_void_p),  # ppv
                ],
                IID_IAudioSessionManager2,
                CLSCTX_ALL,
                None,
                ctypes.byref(mgr_ptr),
            )
        except Exception as exc:  # noqa
            logger.debug("Activate(IAudioSessionManager2) falló: %s", exc)
            device.release()
            return AudioSessionInfo()

        device.release()

        if hr < 0 or not mgr_ptr.value:
            return AudioSessionInfo()

        manager = _ComPtr(mgr_ptr.value)

        # Obtener el enumerador de sesiones
        enum_ptr = ctypes.c_void_p()
        try:
            hr = manager.call(
                "GetSessionEnumerator",
                ctypes.HRESULT,
                [ctypes.POINTER(ctypes.c_void_p)],
                ctypes.byref(enum_ptr),
            )
        except Exception as exc:  # noqa
            logger.debug("GetSessionEnumerator falló: %s", exc)
            manager.release()
            return AudioSessionInfo()

        manager.release()

        if hr < 0 or not enum_ptr.value:
            return AudioSessionInfo()

        session_enum = _ComPtr(enum_ptr.value)

        # Obtener el número de sesiones
        count = ctypes.c_uint()
        try:
            hr = session_enum.call(
                "GetCount",
                ctypes.HRESULT,
                [ctypes.POINTER(ctypes.c_uint)],
                ctypes.byref(count),
            )
        except Exception as exc:  # noqa
            logger.debug("GetCount falló: %s", exc)
            session_enum.release()
            return AudioSessionInfo()

        if hr < 0 or count.value == 0:
            session_enum.release()
            return AudioSessionInfo()

        # Recorrer las sesiones buscando una que esté reproduciendo
        result = AudioSessionInfo(state=AUDIO_SESSION_STATE_INACTIVE)
        for i in range(count.value):
            session_ptr = ctypes.c_void_p()
            try:
                hr = session_enum.call(
                    "GetSession",
                    ctypes.HRESULT,
                    [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)],
                    i,
                    ctypes.byref(session_ptr),
                )
            except Exception as exc:  # noqa
                logger.debug("GetSession(%d) falló: %s", i, exc)
                continue

            if hr < 0 or not session_ptr.value:
                continue

            session = _ComPtr(session_ptr.value)

            # Leer el estado de la sesión
            state = ctypes.c_uint()
            try:
                hr2 = session.call(
                    "GetState",
                    ctypes.HRESULT,
                    [ctypes.POINTER(ctypes.c_uint)],
                    ctypes.byref(state),
                )
            except Exception as exc:  # noqa
                logger.debug("GetState falló: %s", exc)
                session.release()
                continue

            is_playing = hr2 >= 0 and state.value == AUDIO_SESSION_STATE_ACTIVE

            # Leer el nombre para mostrar
            display_name_ptr = ctypes.c_void_p()
            try:
                session.call(
                    "GetDisplayName",
                    ctypes.HRESULT,
                    [ctypes.POINTER(ctypes.c_void_p)],
                    ctypes.byref(display_name_ptr),
                )
            except Exception:  # noqa
                display_name_ptr = None

            display_name = ""
            if display_name_ptr:
                try:
                    # CoTaskMemString: el puntero apunta a un wchar_t*
                    display_name = ctypes.wstring_at(display_name_ptr)
                    ctypes.windll.ole32.CoTaskMemFree(display_name_ptr)
                except Exception:  # noqa
                    display_name = ""

            # Leer el ID de proceso
            pid = ctypes.c_uint32()
            try:
                session.call(
                    "GetProcessId",
                    ctypes.HRESULT,
                    [ctypes.POINTER(ctypes.c_uint32)],
                    ctypes.byref(pid),
                )
            except Exception:  # noqa
                pid = 0

            session.release()

            # Obtener nombre del proceso desde el PID
            process_name = self._process_name_from_pid(pid.value) if pid.value else ""

            # Si esta sesión está activa, nos quedamos con ella
            if is_playing:
                result = AudioSessionInfo(
                    process_id=pid.value,
                    process_name=process_name,
                    display_name=display_name or process_name or f"PID {pid.value}",
                    state=state.value,
                    is_playing=True,
                )
                break
            elif state.value == AUDIO_SESSION_STATE_ACTIVE:
                # Sesión activa pero no necesariamente reproduciendo audio
                result = AudioSessionInfo(
                    process_id=pid.value,
                    process_name=process_name,
                    display_name=display_name or process_name or f"PID {pid.value}",
                    state=state.value,
                    is_playing=False,
                )

        session_enum.release()
        return result

    @staticmethod
    def _process_name_from_pid(pid: int) -> str:
        """Obtiene el nombre del proceso a partir de su PID usando kernel32."""
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return ""
            try:
                size = ctypes.c_uint32(512)
                buf = ctypes.create_unicode_buffer(size.value)
                # QueryFullProcessImageNameW
                kernel32.QueryFullProcessImageNameW.argtypes = [
                    ctypes.c_void_p,  # hProcess
                    ctypes.c_uint32,  # dwFlags
                    ctypes.c_wchar_p,  # lpExeName
                    ctypes.POINTER(ctypes.c_uint32),  # lpdwSize
                ]
                kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
                ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                if ok:
                    return os.path.basename(buf.value)
            finally:
                kernel32.CloseHandle(h)
        except Exception:  # noqa
            pass
        return ""

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)
