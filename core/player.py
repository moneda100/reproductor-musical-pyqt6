"""Motor de reproducción sobre VLC.

Regla dura: **VLC solo se toca desde el hilo de la GUI**. Los callbacks de
evento de VLC llegan desde el hilo interno de libvlc, por lo que se reemiten
mediante ``pyqtSignal`` de un ``QObject`` que vive en el hilo de la GUI: así
el slot se ejecuta siempre en el hilo principal.
"""

from __future__ import annotations

import logging
import os
import sys
from enum import Enum
from typing import Any, Callable, Optional

import vlc
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class PlayerState(Enum):
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2
    ENDED = 3
    BUFFERING = 4
    ERROR = 5

    @property
    def is_playing(self) -> bool:
        return self is PlayerState.PLAYING


class PlayerSignals(QObject):
    """Señales del reproductor entregadas en el hilo de la GUI."""

    state_changed = pyqtSignal(object)  # PlayerState
    position_changed = pyqtSignal(int)  # milisegundos
    duration_changed = pyqtSignal(int)  # milisegundos
    track_ended = pyqtSignal()
    error_occurred = pyqtSignal(str)
    media_changed = pyqtSignal()


def _safe_state_name(value: Any) -> str:
    try:
        return vlc.State(value).name
    except Exception:  # noqa: BLE001
        return str(value)


class MusicPlayer:
    """Motor de reproducción con VLC.

    Reproduce archivos locales (incluidos los descargados de YouTube) y
    streams HTTP. Todos los eventos se exponen como callbacks con nombre.
    """

    def __init__(self, vlc_module: Any | None = None) -> None:
        self._vlc = vlc_module or vlc
        try:
            self.instance = self._vlc.Instance("--quiet", "--no-video-title-show")
        except TypeError:
            self.instance = self._vlc.Instance("--quiet")
        if not self.instance:
            raise RuntimeError("No se pudo inicializar VLC. Comprueba que VLC está instalado.")
        self.player = self.instance.media_player_new()
        self.current_media = None
        self.current_track: Optional[str] = None
        self.state = PlayerState.STOPPED
        self.volume = 0.7
        self.callbacks: dict[str, list[Callable]] = {}
        self.signals = PlayerSignals()
        self._duration_ms = 0
        self._cached_position_ms = 0
        self._attended_events: list[Any] = []
        self._video_win_id: int = 0
        self._pending_seek_ms: Optional[int] = None
        self._seek_deadline: float = 0.0

        self._poll_timer = QTimer()
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._poll_player_state)

        try:
            self.player.audio_set_volume(int(self.volume * 100))
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo fijar el volumen inicial: %s", exc)

        self._attach_events()

    # ------------------------------------------------------------------
    # Eventos de VLC
    # ------------------------------------------------------------------
    def _attach_events(self) -> None:
        """Registra los observadores de eventos de VLC.

        La comprobación previa de ``vlc.EventType`` se hace en tiempo de
        ejecución para tolerar versiones antiguas de ``python-vlc``.
        """
        event_type = getattr(self._vlc, "EventType", None)
        if event_type is None:
            logger.warning("La versión de python-vlc no expone vlc.EventType")
            return

        try:
            manager = self.player.event_manager()
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo obtener el event manager de VLC: %s", exc)
            return

        handlers = {
            "MediaPlayerPlaying": self._on_playing,
            "MediaPlayerPaused": self._on_paused,
            "MediaPlayerStopped": self._on_stopped,
            "MediaPlayerEndReached": self._on_end_reached,
            "MediaPlayerLengthChanged": self._on_length_changed,
            "MediaPlayerTimeChanged": self._on_time_changed,
            "MediaPlayerEncounteredError": self._on_error,
            "MediaPlayerBuffering": self._on_buffering,
            "MediaPlayerMediaChanged": self._on_media_changed,
        }

        for name, handler in handlers.items():
            event = getattr(event_type, name, None)
            if event is None:
                logger.debug("Evento VLC no disponible: %s", name)
                continue
            try:
                if hasattr(manager, "event_attach"):
                    manager.event_attach(event, handler)
                    self._attended_events.append((manager, event, handler))
                elif hasattr(manager, "on"):
                    self._attended_events.append(manager.on(event, handler))
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo suscribir a %s: %s", name, exc)

    def _poll_player_state(self) -> None:
        """Monitoreo periódico para garantizar actualización en tiempo real y fin de pista."""
        if not self.player:
            return
        try:
            raw_state = self.player.get_state()
            vlc_state = self._map_state(raw_state)
            if vlc_state == PlayerState.ENDED:
                if self.state != PlayerState.ENDED:
                    self._on_end_reached()
                return

            if self.state == PlayerState.PLAYING:
                length_ms = self.player.get_length()
                if length_ms > 0 and length_ms != self._duration_ms:
                    self._duration_ms = int(length_ms)
                    self.signals.duration_changed.emit(self._duration_ms)
                    self._trigger_callback("duration_changed", self._duration_ms)

                time_ms = self.player.get_time()
                if time_ms is not None and time_ms >= 0:
                    if getattr(self, "_pending_seek_ms", None) is not None:
                        import time

                        now = time.time()
                        target = self._pending_seek_ms
                        if abs(time_ms - target) <= 2000 or now > getattr(self, "_seek_deadline", 0):
                            self._pending_seek_ms = None
                        else:
                            return
                    if time_ms != self._cached_position_ms:
                        self._cached_position_ms = int(time_ms)
                        self.signals.position_changed.emit(self._cached_position_ms)
                        self._trigger_callback("position_changed", self._cached_position_ms)

                if (
                    self._duration_ms > 0
                    and time_ms is not None
                    and time_ms >= (self._duration_ms - 300)
                    and time_ms > 0
                ):
                    if not self.player.is_playing() or vlc_state in (
                        PlayerState.ENDED,
                        PlayerState.STOPPED,
                    ):
                        self._on_end_reached()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error en sondeo de VLC: %s", exc)

    # -- handlers de VLC -------------------------------------------
    def _on_playing(self, _event=None) -> None:
        self._set_state(PlayerState.PLAYING)

    def _on_paused(self, _event=None) -> None:
        self._set_state(PlayerState.PAUSED)

    def _on_stopped(self, _event=None) -> None:
        self._set_state(PlayerState.STOPPED)

    def _on_end_reached(self, _event=None) -> None:
        self._set_state(PlayerState.ENDED)
        self.signals.track_ended.emit()
        self._trigger_callback("track_ended")

    def _on_length_changed(self, event=None) -> None:
        length = getattr(event, "new_length", 0) or 0
        self._duration_ms = int(length)
        self.signals.duration_changed.emit(self._duration_ms)
        self._trigger_callback("duration_changed", self._duration_ms)

    def _on_time_changed(self, event=None) -> None:
        time_ms = getattr(event, "new_time", 0) or 0
        if getattr(self, "_pending_seek_ms", None) is not None:
            import time

            now = time.time()
            target = self._pending_seek_ms
            # Descartar eventos atrasados de VLC que aún reportan el tiempo previo al seek
            if abs(time_ms - target) <= 2000 or now > getattr(self, "_seek_deadline", 0):
                self._pending_seek_ms = None
            else:
                return
        self._cached_position_ms = int(time_ms)
        self.signals.position_changed.emit(self._cached_position_ms)
        self._trigger_callback("position_changed", self._cached_position_ms)

    def _on_error(self, _event=None) -> None:
        self._set_state(PlayerState.ERROR)
        message = "Error de reproducción: VLC no pudo abrir el medio."
        self.signals.error_occurred.emit(message)
        self._trigger_callback("error", message)

    def _on_buffering(self, event=None) -> None:
        percent = getattr(event, "new_buffer", 0) or 0
        if percent < 99.9:
            self._set_state(PlayerState.BUFFERING)

    def _on_media_changed(self, _event=None) -> None:
        self.signals.media_changed.emit()
        self._trigger_callback("media_changed")

    # ------------------------------------------------------------------
    # API de reproducción
    # ------------------------------------------------------------------
    def set_video_widget(self, win_id: int) -> None:
        """Vincula el reproductor de vídeo a un frame de la interfaz."""
        if win_id:
            self._video_win_id = win_id
        target = win_id or getattr(self, "_video_win_id", 0)
        if not target:
            return
        try:
            if sys.platform.startswith("linux"):
                self.player.set_xwindow(target)
            elif sys.platform == "win32":
                self.player.set_hwnd(target)
            elif sys.platform == "darwin":
                self.player.set_nsobject(target)
            try:
                self.player.video_set_mouse_input(False)
                self.player.video_set_key_input(False)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo asignar video widget: %s", exc)

    def disable_video(self) -> None:
        """Desactiva la pista de vídeo para que VLC nunca abra una ventana externa en modo audio."""
        try:
            self.player.video_set_track(-1)
        except Exception:  # noqa: BLE001
            pass

    def enable_video(self) -> None:
        """Habilita la pista de vídeo para reproducir incrustado en el widget."""
        try:
            tracks = self.player.video_get_track_description() or []
            for track_id, _ in tracks:
                if track_id > 0:
                    self.player.video_set_track(track_id)
                    break
        except Exception:  # noqa: BLE001
            pass

    def load(self, source: str, *, video: bool = True) -> bool:
        """Carga un archivo local o una URL de stream."""
        if not source:
            return False
        try:
            if getattr(self, "_video_win_id", 0):
                self.set_video_widget(self._video_win_id)
            if source.startswith("http://") or source.startswith("https://"):
                logger.debug("VLC cargando stream: %s", source[:80])
                self.current_media = self.instance.media_new(source)
            else:
                path = os.path.abspath(source)
                logger.debug("VLC cargando archivo local: %s", path)
                self.current_media = self.instance.media_new_path(path)

            if not video:
                try:
                    self.current_media.add_option(":no-video")
                except Exception:
                    pass

            self.player.set_media(self.current_media)
            self.current_track = source
            self._duration_ms = 0
            self._cached_position_ms = 0
            # Un seek pendiente pertenece al medio anterior: si se conserva,
            # descarta los eventos de tiempo de la pista nueva y el progreso
            # se queda congelado en el minuto del seek anterior.
            self._pending_seek_ms = None
            self._seek_deadline = 0.0
            self._set_state(PlayerState.STOPPED)
            if not video:
                self.disable_video()
            else:
                self.enable_video()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al cargar %s: %s", source, exc)
            return False

    def play(self) -> bool:
        """Arranca la reproducción. Devuelve ``False`` si no hay medio cargado."""
        if not self.current_media:
            logger.debug("play() sin medio cargado")
            return False
        try:
            result = self.player.play()
        except Exception as exc:  # noqa: BLE001
            logger.warning("VLC falló al iniciar la reproducción: %s", exc)
            self._set_state(PlayerState.ERROR)
            return False
        if result == -1:
            logger.warning("VLC devolvió -1 al iniciar la reproducción")
            self._set_state(PlayerState.ERROR)
            return False
        self._set_state(PlayerState.PLAYING)
        return True

    def pause(self) -> None:
        """Pausa la reproducción solo si realmente está sonando."""
        if self.current_media is None:
            return
        current = self.get_state()
        if current in (PlayerState.STOPPED, PlayerState.ENDED, PlayerState.ERROR):
            logger.debug("pause() ignorado: el reproductor no está sonando")
            return
        try:
            setter = getattr(self.player, "set_pause", None)
            if callable(setter):
                setter(True)
            else:
                self.player.pause()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al pausar: %s", exc)
            return
        self._set_state(PlayerState.PAUSED)

    def resume(self) -> None:
        """Reanuda una reproducción pausada."""
        if self.current_media is None:
            return
        try:
            setter = getattr(self.player, "set_pause", None)
            if callable(setter):
                setter(False)
            else:
                self.player.play()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al reanudar: %s", exc)
            return
        self._set_state(PlayerState.PLAYING)

    def toggle_pause(self) -> None:
        if self.get_state() == PlayerState.PLAYING:
            self.pause()
        else:
            self.resume()

    def stop(self) -> None:
        try:
            self.player.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al detener: %s", exc)
        self._set_state(PlayerState.STOPPED)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        try:
            self.player.audio_set_volume(int(self.volume * 100))
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo ajustar el volumen: %s", exc)

    def get_position(self) -> float:
        """Posición actual en segundos (consulta VLC y usa caché si no está disponible)."""
        try:
            time_ms = self.player.get_time()
            if time_ms is not None and time_ms >= 0:
                self._cached_position_ms = int(time_ms)
                return self._cached_position_ms / 1000.0
        except Exception:  # noqa: BLE001
            pass
        return max(0.0, self._cached_position_ms / 1000.0)

    def get_position_ms(self) -> int:
        try:
            time_ms = self.player.get_time()
        except Exception:  # noqa: BLE001
            return 0
        return int(time_ms) if time_ms and time_ms > 0 else 0

    def get_duration(self) -> float:
        """Duración del medio actual en segundos (0 si se desconoce)."""
        try:
            length = self.player.get_length()
        except Exception:  # noqa: BLE001
            length = 0
        if length and length > 0:
            return length / 1000.0
        return self._duration_ms / 1000.0

    def set_position(self, seconds: float) -> None:
        if not self.current_media:
            return
        try:
            # Validar entrada: rechazar NaN, infinito y negativos
            if seconds != seconds or seconds == float("inf") or seconds == float("-inf"):
                return
            ms = max(0, int(seconds * 1000))
            self._cached_position_ms = ms
            self._pending_seek_ms = ms
            import time

            self._seek_deadline = time.time() + 2.5
            res = self.player.set_time(ms)
            duration = self.get_duration()
            if (res == -1 or res != 0) and duration > 0:
                ratio = max(0.0, min(1.0, seconds / duration))
                self.player.set_position(ratio)
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo fijar la posición: %s", exc)

    def get_state(self) -> PlayerState:
        """Estado real según VLC (no el estado cacheado)."""
        try:
            raw = self.player.get_state()
        except Exception:  # noqa: BLE001
            return self.state
        return self._map_state(raw)

    def _map_state(self, raw: Any) -> PlayerState:
        state_cls = getattr(self._vlc, "State", None)
        if state_cls is None:
            return self.state
        try:
            if raw == state_cls.Playing:
                return PlayerState.PLAYING
            if raw == state_cls.Paused:
                return PlayerState.PAUSED
            if raw == state_cls.Stopped:
                return PlayerState.STOPPED
            if raw == state_cls.Ended:
                return PlayerState.ENDED
            if raw == state_cls.Error:
                return PlayerState.ERROR
            if raw == state_cls.Buffering:
                return PlayerState.BUFFERING
        except Exception:  # noqa: BLE001
            pass
        return self.state

    def get_track_info(self) -> dict:
        """Información de la pista actual leída de VLC (codec, bitrate, muestras)."""
        info: dict[str, Any] = {}
        media = getattr(self.player, "media", None)
        if media is None:
            return info
        try:
            tracks = media.get_tracks_info() or []
        except Exception:  # noqa: BLE001
            return info
        for track in tracks:
            if track.get("type") != 2:  # 2 = audio
                continue
            info = {
                "codec": track.get("codec"),
                "sample_rate": track.get("audio_rate"),
                "channels": track.get("audio_channels"),
                "bitrate": track.get("bitrate"),
            }
            break
        try:
            stats = media.get_stats()
            if stats and getattr(stats, "bitrate", None):
                info.setdefault("bitrate", stats.bitrate)
        except Exception:  # noqa: BLE001
            pass
        return info

    def is_playing(self) -> bool:
        return self.get_state() == PlayerState.PLAYING

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def register_callback(self, event: str, callback: Callable) -> None:
        if event not in self.callbacks:
            self.callbacks[event] = []
        self.callbacks[event].append(callback)

    def unregister_callback(self, event: str, callback: Callable) -> None:
        handlers = self.callbacks.get(event)
        if handlers and callback in handlers:
            handlers.remove(callback)

    def _trigger_callback(self, event: str, *args: Any) -> None:
        for cb in list(self.callbacks.get(event, [])):
            try:
                cb(*args)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error en callback '%s': %s", event, exc)

    def _set_state(self, new_state: PlayerState) -> None:
        if new_state == self.state:
            return
        self.state = new_state
        if new_state == PlayerState.PLAYING:
            if hasattr(self, "_poll_timer") and not self._poll_timer.isActive():
                self._poll_timer.start()
        elif new_state in (
            PlayerState.PAUSED,
            PlayerState.STOPPED,
            PlayerState.ENDED,
            PlayerState.ERROR,
        ):
            if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
                self._poll_timer.stop()
        self.signals.state_changed.emit(new_state)
        self._trigger_callback("state_changed", new_state)
