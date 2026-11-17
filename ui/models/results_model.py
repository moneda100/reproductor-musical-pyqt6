"""``QAbstractListModel`` para los resultados de búsqueda (YouTube / biblioteca)."""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal


class ResultRoles(IntEnum):
    Title = Qt.ItemDataRole.UserRole + 1
    Artist = Qt.ItemDataRole.UserRole + 2
    Duration = Qt.ItemDataRole.UserRole + 3
    Url = Qt.ItemDataRole.UserRole + 4
    Thumbnail = Qt.ItemDataRole.UserRole + 5
    Identifier = Qt.ItemDataRole.UserRole + 6
    Playlist = Qt.ItemDataRole.UserRole + 7
    Source = Qt.ItemDataRole.UserRole + 8


class ResultsModel(QAbstractListModel):
    """Lista de resultados heterogéneos (YouTube o biblioteca local)."""

    count_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._results: list[dict] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._results)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._results)):
            return None
        item = self._results[index.row()]
        if role == ResultRoles.Title:
            return item.get("title", "")
        if role == ResultRoles.Artist:
            return item.get("artist", "")
        if role == ResultRoles.Duration:
            return item.get("duration", 0) or 0
        if role == ResultRoles.Url:
            return item.get("url", "")
        if role == ResultRoles.Thumbnail:
            return item.get("thumbnail") or item.get("cover_url") or ""
        if role == ResultRoles.Identifier:
            return item.get("id", "")
        if role == ResultRoles.Playlist:
            return item.get("playlist", "")
        if role == ResultRoles.Source:
            return item.get("source", "youtube")
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("title", "")
        if role == Qt.ItemDataRole.ToolTipRole:
            artist = item.get("artist", "")
            return f"{item.get('title', '')}\n{artist}" if artist else item.get("title", "")
        return None

    def roleNames(self) -> dict:  # noqa: N802
        return {
            ResultRoles.Title: b"title",
            ResultRoles.Artist: b"artist",
            ResultRoles.Duration: b"duration",
            ResultRoles.Url: b"url",
            ResultRoles.Thumbnail: b"thumbnail",
            ResultRoles.Identifier: b"identifier",
            ResultRoles.Playlist: b"playlist",
            ResultRoles.Source: b"source",
        }

    def set_results(self, results: Iterable[dict]) -> None:
        self.beginResetModel()
        self._results = list(results)
        self.endResetModel()
        self.count_changed.emit(len(self._results))

    def append_results(self, results: Iterable[dict]) -> int:
        """Añade resultados al final sin perder la selección existente.

        Devuelve cuántos elementos se añadieron. Se usa para «Cargar más»:
        el modelo crece y la vista conserva el scroll y los elementos previos.
        """
        new_results = list(results)
        if not new_results:
            return 0
        start = len(self._results)
        self.beginInsertRows(QModelIndex(), start, start + len(new_results) - 1)
        self._results.extend(new_results)
        self.endInsertRows()
        self.count_changed.emit(len(self._results))
        return len(new_results)

    def clear(self) -> None:
        self.set_results([])

    def result_at(self, row: int) -> Optional[dict]:
        if 0 <= row < len(self._results):
            return self._results[row]
        return None

    def results(self) -> list[dict]:
        return list(self._results)
