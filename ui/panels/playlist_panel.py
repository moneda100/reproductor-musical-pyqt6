"""Panel de la lista de reproducción (con modelo de datos y reordenación)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.models.track_list_model import TrackListModel, TrackRoles
from ui.widgets import TrackListDelegate


class PlaylistPanel(QWidget):
    """Lista principal de reproducción."""

    play_requested = pyqtSignal(int)
    play_next_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)
    clear_requested = pyqtSignal()
    favorite_requested = pyqtSignal(int)
    move_requested = pyqtSignal(int, int)
    edit_tags_requested = pyqtSignal(int)
    open_folder_requested = pyqtSignal(int)

    def __init__(
        self,
        model: TrackListModel,
        provider=None,
        parent: QWidget | None = None,
        title: str = "Mi lista",
    ) -> None:
        super().__init__(parent)
        self.model = model
        self._panel_title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.header_label = QLabel("Mi lista (0)")
        self.header_label.setObjectName("TitleLabel")
        header.addWidget(self.header_label)
        header.addStretch()

        self.favorite_btn = QPushButton("⭐ Favorita")
        self.favorite_btn.setObjectName("SecondaryBtn")
        self.favorite_btn.clicked.connect(self._emit_favorite)
        header.addWidget(self.favorite_btn)

        self.edit_btn = QPushButton("🏷️ Etiquetas")
        self.edit_btn.setObjectName("SecondaryBtn")
        self.edit_btn.clicked.connect(self._emit_edit)
        header.addWidget(self.edit_btn)

        self.remove_btn = QPushButton("🗑️ Quitar")
        self.remove_btn.setObjectName("SecondaryBtn")
        self.remove_btn.clicked.connect(self._emit_remove)
        header.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("🧹 Limpiar")
        self.clear_btn.setObjectName("SecondaryBtn")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        header.addWidget(self.clear_btn)

        layout.addLayout(header)

        self.list_view = QListView(self)
        self.list_view.setObjectName("PlaylistList")
        self.list_view.setModel(self.model)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_view.doubleClicked.connect(self.play_requested.emit)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        self.list_view.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_view, stretch=1)

        self._delegate = TrackListDelegate(provider, self.list_view)
        self.list_view.setItemDelegate(self._delegate)

        model.modelReset.connect(self._update_header)
        model.rowsInserted.connect(lambda *_: self._update_header())
        model.rowsRemoved.connect(lambda *_: self._update_header())
        model.current_changed.connect(self._on_current_changed)

    # -- utilidades ---------------------------------------------------
    def _on_current_changed(self, row: int) -> None:
        if 0 <= row < self.model.rowCount():
            idx = self.model.index(row, 0)
            self.list_view.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

    def _update_header(self) -> None:
        self.header_label.setText(f"{self._panel_title} ({self.model.rowCount()})")

    def current_row(self) -> int:
        index = self.list_view.currentIndex()
        return index.row() if index.isValid() else -1

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.list_view.selectedIndexes()})

    # -- acciones -----------------------------------------------------
    def _emit_favorite(self) -> None:
        row = self.current_row()
        if row >= 0:
            self.favorite_requested.emit(row)

    def _emit_edit(self) -> None:
        row = self.current_row()
        if row >= 0:
            self.edit_tags_requested.emit(row)

    def _emit_remove(self) -> None:
        rows = self.selected_rows()
        if not rows:
            row = self.current_row()
            rows = [row] if row >= 0 else []
        for row in reversed(rows):
            self.remove_requested.emit(row)

    def _on_rows_moved(self, _parent, start: int, end: int, destination, row: int) -> None:
        if destination.isValid() and row != start:
            self.move_requested.emit(start, row)

    def _show_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QApplication, QMenu

        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        title = str(index.data(TrackRoles.Title) or "")
        artist = str(index.data(TrackRoles.Artist) or "")
        file_path = str(index.data(TrackRoles.FilePath) or "")

        menu = QMenu(self)
        play = menu.addAction("▶ Reproducir")
        play.triggered.connect(lambda: self.play_requested.emit(row))
        play_next = menu.addAction("⏭ Reproducir a continuación")
        play_next.triggered.connect(lambda: self.play_next_requested.emit(row))
        menu.addSeparator()

        favorite = menu.addAction("⭐ Alternar favorita")
        favorite.triggered.connect(lambda: self.favorite_requested.emit(row))
        edit = menu.addAction("🏷️ Editar etiquetas")
        edit.triggered.connect(lambda: self.edit_tags_requested.emit(row))
        open_folder = menu.addAction("📂 Abrir carpeta")
        open_folder.setEnabled(bool(file_path))
        open_folder.triggered.connect(lambda: self.open_folder_requested.emit(row))
        menu.addSeparator()

        copy_title = menu.addAction("📋 Copiar título")
        copy_title.setEnabled(bool(title))
        copy_title.triggered.connect(lambda: QApplication.clipboard().setText(title))
        copy_artist = menu.addAction("📋 Copiar artista")
        copy_artist.setEnabled(bool(artist))
        copy_artist.triggered.connect(lambda: QApplication.clipboard().setText(artist))
        if file_path:
            copy_path = menu.addAction("🔗 Copiar ruta")
            copy_path.triggered.connect(lambda: QApplication.clipboard().setText(file_path))
        menu.addSeparator()

        remove = menu.addAction("🗑️ Quitar de la lista")
        remove.triggered.connect(lambda: self.remove_requested.emit(row))
        clear = menu.addAction("🧹 Limpiar lista")
        clear.setEnabled(self.model.rowCount() > 0)
        clear.triggered.connect(self.clear_requested.emit)
        menu.exec(self.list_view.viewport().mapToGlobal(pos))
