"""Controlador de reproducción: puente entre la playlist y VLC.

**VLC solo se toca desde el hilo de la GUI**: este controlador no crea
hilos, solo Translate las intenciones del usuario a llamadas sobre el
reproductor, y traduce los eventos de VLC a señales Qt.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.player import MusicPlayer, PlayerState
from core.playlist import Track
from ui.controllers.playlist_controller import PlaylistController

logger = logging.getLogger(__name__)


class PlaybackController(QObject):
    """Estado de reproducción y navegación por la cola."""

    state_changed = pyqtSignal(object)  # PlayerState
    track_changed = pyqtSignal(object)  # Track
    position_changed = pyqtSignal(int)  # milisegundos
    duration_changed = pyqtSignal(int)  # milisegundos
    error_occurred = pyqtSignal(str)
    playlist_finished = pyqtSignal()
    stream_required = pyqtSignal(object)  # Track de YouTube sin archivo local
    seek_started = pyqtSignal(int)  # segundos objetivo del seek

    SEEK_THRESHOLD_MS = 2000  # 2 s: umbral para dar por terminado el seek

    def __init__(
        self,
        playlist_controller: PlaylistController,
        player: Optional[MusicPlayer] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.playlist = playlist_controller
        self.player = player or MusicPlayer()
        self._duration_ms = 0
        self._seeking = False
        self._seek_target_ms: Optional[int] = None
        self._seek_deadline: float = 0.0

        # Único canal de eventos: las señales Qt del reproductor se emiten en
        # el hilo de la GUI, así que los slots también se ejecutan allí.
        self.player.signals.state_changed.connect(self._on_state_changed)
        self.player.signals.position_changed.connect(self._on_position_changed)
        self.player.signals.duration_changed.connect(self._on_duration_changed)
        self.player.signals.track_ended.connect(self._on_track_ended)
        self.player.signals.error_occurred.connect(self.error_occurred.emit)

    # -- callbacks de VLC ---------------------------------------------
    def _on_state_changed(self, state: PlayerState) -> None:
        self.state_changed.emit(state)

    def _on_position_changed(self, position_ms: int) -> None:
        position_ms = int(position_ms)
        # Durante un seek manual, el valor de VLC puede ir por detrás del
        # objetivo. Mantenemos el objetivo en pantalla hasta que VLC se
        # acerque lo suficiente, o pase el timeout de seguridad (1.5s).
        if self._seeking and self._seek_target_ms is not None:
            import time

            close_enough = abs(position_ms - self._seek_target_ms) <= self.SEEK_THRESHOLD_MS
            # Si _seek_deadline no está establecido (0), tratarlo como infinito (no timeout)
            deadline = self._seek_deadline if self._seek_deadline > 0 else float('inf')
            timed_out = time.time() > deadline
            if close_enough or timed_out:
                self._seeking = False
                self._seek_target_ms = None
                self.position_changed.emit(position_ms)
            else:
                self.position_changed.emit(self._seek_target_ms)
            return
        self.position_changed.emit(position_ms)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = int(duration_ms)
        self.duration_changed.emit(self._duration_ms)

    def _on_track_ended(self) -> None:
        """Fin de pista detectado: avanza a la siguiente canción inmediatamente."""
        self._reset_seek_state()
        self.next(auto=True)

    def _on_error(self, message: str) -> None:
        self.error_occurred.emit(message)

    # -- reproducción ---------------------------------------------------
    def _needs_stream(self, track: Track) -> bool:
        """YouTube sin archivo local disponible: hay que resolver el stream."""
        if not track.is_youtube:
            return False
        path = track.file_path or ""
        if path.startswith("http"):
            return False
        return not (path and os.path.exists(path))

    def _reset_seek_state(self) -> None:
        """Olvida un seek pendiente al cambiar de pista."""
        self._seeking = False
        self._seek_target_ms = None

    def _load_track(self, track: Track, video: bool = False, auto_advance: bool = False) -> bool:
        """Carga una pista; si es de YouTube sin archivo, pide el stream."""
        self._reset_seek_state()
        if self._needs_stream(track):
            self.stream_required.emit(track)
            return False
        if not self.player.load(track.file_path, video=video):
            self.error_occurred.emit(f"No se pudo cargar «{track.title}»")
            if auto_advance:
                self.next(auto=True)
            return False
        self.track_changed.emit(track)
        return self.player.play()

    def play_index(self, index: int, video: bool = False) -> bool:
        """Carga y reproduce la pista del índice indicado."""
        track = self.playlist.track_at(index)
        if track is None:
            return False
        self.playlist.set_current(index)
        return self._load_track(track, video=video)

    def play_track(self, track: Track, video: bool = False) -> bool:
        index = self.playlist.index_of(track)
        if index < 0:
            return False
        return self.play_index(index, video=video)

    def play_stream(
        self,
        track: Track,
        stream_url: str,
        position: Optional[float] = None,
        autoplay: bool = True,
        is_video: bool = False,
    ) -> bool:
        """Reproduce una pista cuando su stream ya se ha resuelto.

        ``position`` permite reanudar en el mismo punto al cambiar entre audio
        y vídeo, y ``autoplay=False`` conserva el estado de pausa.
        """
        self._reset_seek_state()
        if not stream_url:
            self.error_occurred.emit(f"No se pudo obtener el stream de «{track.title}»")
            # Intentar la siguiente pista automáticamente
            self.next(auto=True)
            return False
        index = self.playlist.index_of(track)
        if index >= 0:
            self.playlist.set_current(index)
        if not self.player.load(stream_url, video=is_video):
            self.error_occurred.emit(f"No se pudo cargar «{track.title}»")
            # Intentar la siguiente pista automáticamente
            self.next(auto=True)
            return False
        if position is not None:
            self.player.set_position(max(0.0, float(position)))
        self.track_changed.emit(track)
        if not autoplay:
            return True
        return self.player.play()

    def toggle_play(self) -> None:
        state = self.player.get_state()
        if state == PlayerState.PLAYING:
            self.player.pause()
        elif state == PlayerState.PAUSED:
            self.player.resume()
        else:
            current = self.playlist.current_track()
            if current is not None:
                self.play_index(self.playlist.index_of(current))
            elif self.playlist.count:
                self.play_index(0)

    def next(self, auto: bool = False) -> Optional[Track]:
        """Avanza a la siguiente pista. ``auto=True`` cuando llega por evento."""
        track = self.playlist.playlist.next()
        if track is None:
            if auto:
                self.playlist_finished.emit()
            return None
        self.playlist.set_current(self.playlist.playlist.current_index)
        self._load_track(track, auto_advance=auto)
        return track

    def previous(self) -> Optional[Track]:
        track = self.playlist.playlist.previous()
        if track is None:
            return None
        self.playlist.set_current(self.playlist.playlist.current_index)
        self._load_track(track)
        return track

    def seek(self, seconds: float) -> None:
        import time

        seconds = max(0.0, float(seconds))
        self._seeking = True
        self._seek_target_ms = int(seconds * 1000)
        self._seek_deadline = time.time() + 1.5
        self.player.set_position(seconds)
        # Notificar inmediatamente al UI para que muestre el objetivo del seek.
        self.position_changed.emit(self._seek_target_ms)
        self.seek_started.emit(int(seconds))

    def set_volume(self, value: int) -> None:
        self.player.set_volume(max(0.0, min(1.0, value / 100.0)))

    def stop(self) -> None:
        self._reset_seek_state()
        self.player.stop()

    # -- estado ---------------------------------------------------------
    @property
    def state(self) -> PlayerState:
        return self.player.get_state()

    def is_playing(self) -> bool:
        return self.state == PlayerState.PLAYING

    def current_media_info(self) -> dict:
        return self.player.get_track_info()
