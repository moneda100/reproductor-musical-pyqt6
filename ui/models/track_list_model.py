"""``QAbstractListModel`` para listas de pistas (playlist, cola)."""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal

from core.playlist import Track


class TrackRoles(IntEnum):
    Title = Qt.ItemDataRole.UserRole + 1
    Artist = Qt.ItemDataRole.UserRole + 2
    Album = Qt.ItemDataRole.UserRole + 3
    Duration = Qt.ItemDataRole.UserRole + 4
    Source = Qt.ItemDataRole.UserRole + 5
    CoverUrl = Qt.ItemDataRole.UserRole + 6
    FilePath = Qt.ItemDataRole.UserRole + 7
    TrackKey = Qt.ItemDataRole.UserRole + 8
    Current = Qt.ItemDataRole.UserRole + 9
    Available = Qt.ItemDataRole.UserRole + 10


class TrackListModel(QAbstractListModel):
    """Lista de pistas con roles enriquecidos (título, artista, duración, portada)."""

    current_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._current_index: int = -1
        self._available: Optional[set[str]] = None

    # -- API de Qt ---------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._tracks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        if role == TrackRoles.Title:
            return track.title
        if role == TrackRoles.Artist:
            return track.artist
        if role == TrackRoles.Album:
            return track.album
        if role == TrackRoles.Duration:
            return track.duration
        if role == TrackRoles.Source:
            return track.source
        if role == TrackRoles.CoverUrl:
            return track.cover_url
        if role == TrackRoles.FilePath:
            return track.file_path
        if role == TrackRoles.TrackKey:
            return track.track_key
        if role == TrackRoles.Current:
            return index.row() == self._current_index
        if role == TrackRoles.Available:
            return self.is_available(track)
        if role == Qt.ItemDataRole.DisplayRole:
            return track.title
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{track.title}\n{track.artist}\n{track.album}"
        return None

    def roleNames(self) -> dict:  # noqa: N802
        return {
            TrackRoles.Title: b"title",
            TrackRoles.Artist: b"artist",
            TrackRoles.Album: b"album",
            TrackRoles.Duration: b"duration",
            TrackRoles.Source: b"source",
            TrackRoles.CoverUrl: b"coverUrl",
            TrackRoles.FilePath: b"filePath",
            TrackRoles.TrackKey: b"trackKey",
            TrackRoles.Current: b"current",
            TrackRoles.Available: b"available",
        }

    # -- mutaciones --------------------------------------------------
    def set_tracks(self, tracks: Iterable[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()

    def append_track(self, track: Track) -> None:
        row = len(self._tracks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tracks.append(track)
        self.endInsertRows()

    def remove_row(self, row: int) -> bool:
        if not (0 <= row < len(self._tracks)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._tracks.pop(row)
        self.endRemoveRows()
        if self._current_index >= len(self._tracks):
            self.set_current_index(max(0, len(self._tracks) - 1))
        elif self._current_index > row:
            self.set_current_index(self._current_index - 1)
        return True

    def move_row(self, source: int, destination: int) -> bool:
        if not (0 <= source < len(self._tracks)):
            return False
        destination = max(0, min(destination, len(self._tracks) - 1))
        if source == destination:
            return False
        self.beginResetModel()
        track = self._tracks.pop(source)
        self._tracks.insert(destination, track)
        self.endResetModel()
        return True

    def clear(self) -> None:
        self.beginResetModel()
        self._tracks.clear()
        self._current_index = -1
        self.endResetModel()

    def set_current_index(self, index: int) -> None:
        if index == self._current_index:
            return
        old = self._current_index
        self._current_index = index
        if 0 <= old < len(self._tracks):
            self.dataChanged.emit(self.index(old, 0), self.index(old, 0), [TrackRoles.Current])
        if 0 <= index < len(self._tracks):
            self.dataChanged.emit(self.index(index, 0), self.index(index, 0), [TrackRoles.Current])
        self.current_changed.emit(index)

    # -- consultas ---------------------------------------------------
    def track_at(self, row: int) -> Optional[Track]:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def row_of(self, track: Track) -> int:
        for index, candidate in enumerate(self._tracks):
            if candidate is track:
                return index
        return -1

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    # -- disponibilidad local ----------------------------------------
    def set_unavailable(self, keys: Iterable[str]) -> None:
        """Marca como no disponibles las pistas con esas ``track_key``."""
        self._available = set(keys)
        if self._tracks:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._tracks) - 1, 0),
                [TrackRoles.Available],
            )

    def is_available(self, track: Track) -> bool:
        if self._available is None:
            return True
        return track.track_key not in self._available
