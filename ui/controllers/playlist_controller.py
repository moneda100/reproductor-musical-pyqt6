"""Punto único de entrada de las mutaciones de la playlist.

Antes, ``MainWindow`` mutaba ``self.playlist`` directamente en varios sitios
(``_add_track_to_ui``, ``remove_selected_track``, ``clear_playlist``). Con la
sincronización entre dispositivos esa dispersión hacía que la capa de sync
perdiera eventos. Ahora **todas** las mutaciones pasan por aquí y se notifican
con señales.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.playlist import Playlist, Track
from ui.models.track_list_model import TrackListModel


class PlaylistController(QObject):
    """Envuelve a :class:`core.playlist.Playlist` y la sincroniza con el modelo."""

    tracks_changed = pyqtSignal()
    current_changed = pyqtSignal(int)
    track_added = pyqtSignal(object)

    def __init__(
        self,
        playlist: Optional[Playlist] = None,
        model: Optional[TrackListModel] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.playlist = playlist or Playlist("Mi Lista")
        self.model = model or TrackListModel(self)
        self.model.set_tracks(self.playlist.tracks)

    # -- consultas -----------------------------------------------------
    @property
    def count(self) -> int:
        return len(self.playlist.tracks)

    def current_track(self) -> Optional[Track]:
        return self.playlist.get_current_track()

    def track_at(self, index: int) -> Optional[Track]:
        if 0 <= index < len(self.playlist.tracks):
            return self.playlist.tracks[index]
        return None

    def tracks(self) -> list[Track]:
        return list(self.playlist.tracks)

    def index_of(self, track: Track) -> int:
        idx = self.playlist.find_index(track)
        if idx >= 0:
            return idx
        return self.playlist.find_index_by_key(track.track_key)

    # -- mutaciones ----------------------------------------------------
    def add_track(self, track: Track) -> None:
        self.playlist.add_track(track)
        self.model.append_track(track)
        self.tracks_changed.emit()
        self.track_added.emit(track)

    def add_tracks(self, tracks: Iterable[Track]) -> None:
        tracks = list(tracks)
        if not tracks:
            return
        self.playlist.add_tracks(tracks)
        self.model.set_tracks(self.playlist.tracks)
        self.tracks_changed.emit()
        for track in tracks:
            self.track_added.emit(track)

    def remove_index(self, index: int) -> bool:
        if not (0 <= index < len(self.playlist.tracks)):
            return False
        self.playlist.remove_track(index)
        self.model.remove_row(index)
        self.tracks_changed.emit()
        self.current_changed.emit(self.playlist.current_index)
        return True

    def move(self, source: int, destination: int) -> bool:
        if not self.playlist.move_track(source, destination):
            return False
        self.model.move_row(source, destination)
        self.tracks_changed.emit()
        return True

    def clear(self) -> None:
        self.playlist.clear()
        self.model.clear()
        self.tracks_changed.emit()
        self.current_changed.emit(0)

    def set_current(self, index: int) -> None:
        if not (0 <= index < len(self.playlist.tracks)):
            return
        self.playlist.current_index = index
        self.model.set_current_index(index)
        self.current_changed.emit(index)

    # -- persistencia ---------------------------------------------------
    def load_from(self, path: str) -> bool:
        try:
            playlist = Playlist.load_from_file(path)
        except (OSError, ValueError) as error:
            self.tracks_changed.emit()
            raise error
        self.playlist = playlist
        self.model.set_tracks(playlist.tracks)
        self.tracks_changed.emit()
        self.current_changed.emit(playlist.current_index)
        return True

    def save_to(self, path: str) -> None:
        self.playlist.save_to_file(path)
