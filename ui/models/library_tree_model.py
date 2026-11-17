"""Modelo de árbol de la biblioteca.

Sustituye al ``QTreeWidget`` anterior, que construía el árbol con búsquedas
lineales de hijos (``_find_or_create_node``) → construcción **O(n²)**.

Aquí los nodos se guardan en estructuras Python con lookup por clave en
``O(1)`` y los ``QModelIndex`` se crean **de forma perezosa** (solo para las
filas visibles), de modo que con 20 000 pistas el cambio de vista queda muy
por debajo de los 200 ms exigidos.

Durante el escaneo las inserciones son incrementales
(``beginInsertRows``/``endInsertRows``), así que el coste total es lineal.
"""

from __future__ import annotations

import os
from enum import IntEnum
from typing import Iterable, Optional

from PyQt6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)


class LibraryViewMode(IntEnum):
    FOLDERS = 0
    ARTISTS = 1
    ALBUMS = 2

    @classmethod
    def from_text(cls, text: str) -> "LibraryViewMode":
        lowered = (text or "").lower()
        if "artista" in lowered:
            return cls.ARTISTS
        if "álbum" in lowered or "album" in lowered:
            return cls.ALBUMS
        return cls.FOLDERS


class NodeKind(IntEnum):
    FOLDER = 0
    ARTIST = 1
    ALBUM = 2
    TRACK = 3


class LibraryRoles(IntEnum):
    Path = Qt.ItemDataRole.UserRole + 1
    Kind = Qt.ItemDataRole.UserRole + 2
    Entry = Qt.ItemDataRole.UserRole + 3


class _Node:
    """Nodo del árbol de biblioteca."""

    __slots__ = (
        "kind",
        "label",
        "path",
        "entry",
        "children",
        "child_index",
        "parent",
        "row",
    )

    def __init__(
        self,
        kind: NodeKind,
        label: str,
        path: str | None = None,
        entry: dict | None = None,
    ) -> None:
        self.kind = kind
        self.label = label
        self.path = path
        self.entry = entry
        self.children: list[_Node] = []
        self.child_index: dict[str, int] = {}
        self.parent: Optional[_Node] = None
        self.row: int = 0

    def matches(self, needle: str) -> bool:
        """``True`` si el nodo (o sus metadatos) contienen el texto buscado."""
        if needle in self.label.casefold():
            return True
        entry = self.entry
        if not entry:
            return False
        return needle in _entry_search_text(entry)

    def get_or_create(
        self, key: str, kind: NodeKind, label: str, path: str | None = None
    ) -> "_Node":
        """Devuelve (o crea) el hijo identificado por ``key``. O(1)."""
        position = self.child_index.get(key)
        if position is not None:
            return self.children[position]
        node = _Node(kind, label, path)
        node.parent = self
        node.row = len(self.children)
        self.children.append(node)
        self.child_index[key] = node.row
        return node

    def add_child(self, key: str, node: "_Node") -> "_Node":
        node.parent = self
        node.row = len(self.children)
        self.children.append(node)
        self.child_index[key] = node.row
        return node


class LibraryTreeModel(QAbstractItemModel):
    """Árbol de la biblioteca con modos Carpeta / Artista / Álbum."""

    count_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = _Node(NodeKind.FOLDER, "")
        self._mode = LibraryViewMode.FOLDERS
        self._count = 0
        self._building = False
        self._last_rel_dir: str | None = None
        self._last_parent: Optional[_Node] = None

    # -- API de Qt ---------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return len(parent.internalPointer().children)
        return len(self._root.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 1

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer() if parent.isValid() else self._root
        if row >= len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:  # noqa: A003
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent = node.parent
        if parent is None or parent is self._root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return node.label
        if role == LibraryRoles.Path:
            return node.path
        if role == LibraryRoles.Kind:
            return int(node.kind)
        if role == Qt.ItemDataRole.ToolTipRole:
            return node.path or node.label
        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "Biblioteca"
        return None

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        if parent.isValid():
            return bool(parent.internalPointer().children)
        return bool(self._root.children)

    # -- construcción ------------------------------------------------
    @property
    def mode(self) -> LibraryViewMode:
        return self._mode

    def set_mode(self, mode: LibraryViewMode) -> None:
        self._mode = mode

    def set_entries(self, entries: Iterable[dict], mode: LibraryViewMode | None = None) -> None:
        """Reconstruye el árbol completo a partir de las entradas.

        La construcción se hace en Python puro dentro de un único
        ``beginResetModel``: notificar cada inserción por separado costaría
        decenas de miles de señales de Qt con 20 000 pistas.
        """
        if mode is not None:
            self._mode = mode
        self.beginResetModel()
        self._root = _Node(NodeKind.FOLDER, "")
        self._count = 0
        self._building = True
        self._last_rel_dir = None
        self._last_parent = None
        insert = {
            LibraryViewMode.FOLDERS: self._insert_folder,
            LibraryViewMode.ARTISTS: self._insert_artist,
            LibraryViewMode.ALBUMS: self._insert_album,
        }[self._mode]
        try:
            for entry in entries:
                insert(entry)
        finally:
            self._building = False
        self.endResetModel()
        self.count_changed.emit(self._count)

    def add_entries(self, entries: Iterable[dict]) -> None:
        """Añade entradas de forma incremental (usado durante el escaneo)."""
        for entry in entries:
            self._insert(entry)
        self.count_changed.emit(self._count)

    def clear(self) -> None:
        self.set_entries([])

    # -- inserción ----------------------------------------------------
    def _insert(self, entry: dict) -> None:
        if self._mode == LibraryViewMode.FOLDERS:
            self._insert_folder(entry)
        elif self._mode == LibraryViewMode.ARTISTS:
            self._insert_artist(entry)
        else:
            self._insert_album(entry)

    def _insert_folder(self, entry: dict) -> None:
        rel_dir = entry.get("rel_dir", ".")
        # Caché de la última carpeta visitada: los ficheros llegan agrupados
        # por carpeta, así que se evita repetir el troceado y las búsquedas.
        if rel_dir == self._last_rel_dir:
            parent = self._last_parent
        else:
            parent = self._folder_node(rel_dir)
            self._last_rel_dir = rel_dir
            self._last_parent = parent

        path = entry.get("path")
        node = _Node(NodeKind.TRACK, f"🎵 {entry.get('filename', '')}", path, entry)
        if self._building:
            parent.add_child(path, node)
        else:
            self._insert_child(parent, path, node)
        self._count += 1

    def _folder_node(self, rel_dir: str) -> _Node:
        """Devuelve (creando si hace falta) el nodo de una carpeta relativa."""
        sep = os.sep
        parts = [p for p in rel_dir.replace("/", sep).split(sep) if p and p != "."]
        parent = self._root
        key = ""
        for part in parts:
            key = part if not key else f"{key}{sep}{part}"
            existing = parent.child_index.get(key)
            if existing is None:
                node = _Node(NodeKind.FOLDER, f"📁 {part}", key)
                if self._building:
                    parent = parent.add_child(key, node)
                else:
                    parent = self._insert_child(parent, key, node)
            else:
                parent = parent.children[existing]
        return parent

    def _insert_artist(self, entry: dict) -> None:
        artist = entry.get("artist") or "Desconocido"
        album = entry.get("album") or "Desconocido"
        artist_node = self._root.get_or_create(artist, NodeKind.ARTIST, f"🎤 {artist}", None)
        album_node = artist_node.get_or_create(
            f"{artist}|{album}", NodeKind.ALBUM, f"💿 {album}", None
        )
        path = entry.get("path")
        node = _Node(NodeKind.TRACK, f"🎵 {entry.get('title', '')}", path, entry)
        self._insert_child(album_node, path, node)
        self._count += 1

    def _insert_album(self, entry: dict) -> None:
        album = entry.get("album") or "Desconocido"
        album_node = self._root.get_or_create(album, NodeKind.ALBUM, f"💿 {album}", None)
        path = entry.get("path")
        node = _Node(NodeKind.TRACK, f"🎵 {entry.get('title', '')}", path, entry)
        self._insert_child(album_node, path, node)
        self._count += 1

    def _insert_child(self, parent: _Node, key: str, node: _Node) -> _Node:
        """Inserta un hijo notificando a Qt (inserción incremental real)."""
        if self._building:
            return parent.add_child(key, node)
        parent_index = self._index_of(parent)
        row = len(parent.children)
        self.beginInsertRows(parent_index, row, row)
        parent.add_child(key, node)
        self.endInsertRows()
        return node

    def _index_of(self, node: _Node) -> QModelIndex:
        if node is self._root:
            return QModelIndex()
        return self.createIndex(node.row, 0, node)


def _entry_search_text(entry: dict) -> str:
    """Texto indexable de una entrada de biblioteca (para el filtro)."""
    parts = [
        entry.get("title", ""),
        entry.get("artist", ""),
        entry.get("album", ""),
        entry.get("filename", ""),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


class LibraryFilterProxy(QSortFilterProxyModel):
    """Filtro de texto y ordenación sobre el árbol de la biblioteca."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_text = ""
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(True)

    def set_filter_text(self, text: str) -> None:
        self._filter_text = (text or "").strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        if not self._filter_text:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False
        node = index.internalPointer()
        if node.kind == NodeKind.TRACK:
            return node.matches(self._filter_text)
        # Un grupo se mantiene si alguno de sus descendientes coincide.
        return any(self._subtree_matches(child) for child in node.children)

    def _subtree_matches(self, node: _Node) -> bool:
        if node.kind == NodeKind.TRACK and node.matches(self._filter_text):
            return True
        return any(self._subtree_matches(child) for child in node.children)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        left_node = model.index(left.row(), 0, left.parent()).internalPointer()
        right_node = model.index(right.row(), 0, right.parent()).internalPointer()
        # Los grupos (carpetas/artistas/álbumes) siempre antes que las pistas.
        if left_node.kind != right_node.kind:
            return left_node.kind < right_node.kind
        return left_node.label.casefold() < right_node.label.casefold()
