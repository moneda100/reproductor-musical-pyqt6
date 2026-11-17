"""Panel de cola: vista de la cola con reordenación por arrastre."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.models.track_list_model import TrackListModel
from ui.widgets import TrackListDelegate


class QueuePanel(QWidget):
    """Cola de reproducción (la propia lista de reproducción)."""

    play_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)
    move_requested = pyqtSignal(int, int)
    clear_requested = pyqtSignal()
    save_as_playlist_requested = pyqtSignal()
    clear_played_requested = pyqtSignal()
    shuffle_queue_requested = pyqtSignal()

    def __init__(self, model: TrackListModel, provider=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.header_label = QLabel("Cola")
        self.header_label.setObjectName("TitleLabel")
        header.addWidget(self.header_label)
        header.addStretch()

        # Botón de menú para acciones adicionales (☰)
        self.menu_btn = QPushButton("☰")
        self.menu_btn.setObjectName("GhostBtn")
        self.menu_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.menu_btn.setToolTip("Más opciones de cola")
        self.menu_btn.setAccessibleName("Opciones de cola")
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.clicked.connect(self._show_queue_menu)
        header.addWidget(self.menu_btn)

        self.remove_btn = QPushButton("Quitar")
        self.remove_btn.setObjectName("SecondaryBtn")
        self.remove_btn.clicked.connect(self._emit_remove)
        header.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Vaciar")
        self.clear_btn.setObjectName("SecondaryBtn")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.list_view = QListView(self)
        self.list_view.setObjectName("QueueList")
        self.list_view.setModel(self.model)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_view.doubleClicked.connect(self.play_requested.emit)
        self.list_view.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_view, stretch=1)

        self._delegate = TrackListDelegate(provider, self.list_view)
        self.list_view.setItemDelegate(self._delegate)

        model.modelReset.connect(self._update_header)
        model.rowsInserted.connect(lambda *_: self._update_header())
        model.rowsRemoved.connect(lambda *_: self._update_header())
        model.current_changed.connect(self._on_current_changed)

        # Menú contextual en la lista
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)

    def _on_current_changed(self, row: int) -> None:
        if 0 <= row < self.model.rowCount():
            idx = self.model.index(row, 0)
            self.list_view.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

    def _show_queue_menu(self) -> None:
        """Muestra el menú de opciones de cola."""
        menu = QMenu(self)

        save_action = menu.addAction("💾  Guardar cola como playlist…")
        save_action.triggered.connect(self.save_as_playlist_requested.emit)

        menu.addSeparator()

        clear_played_action = menu.addAction("🧹  Limpiar reproducidas")
        clear_played_action.triggered.connect(self.clear_played_requested.emit)

        shuffle_action = menu.addAction("🔀  Mezclar cola")
        shuffle_action.triggered.connect(self.shuffle_queue_requested.emit)

        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _show_context_menu(self, pos) -> None:
        """Menú contextual en elementos de la cola."""
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)

        play_action = menu.addAction("▶  Reproducir")
        play_action.triggered.connect(lambda: self.play_requested.emit(index.row()))

        menu.addSeparator()

        remove_action = menu.addAction("🗑️  Quitar de la cola")
        remove_action.triggered.connect(lambda: self.remove_requested.emit(index.row()))

        menu.addSeparator()

        move_up_action = menu.addAction("⬆️  Subir")
        move_up_action.triggered.connect(lambda: self._move_row(index.row(), -1))

        move_down_action = menu.addAction("⬇️  Bajar")
        move_down_action.triggered.connect(lambda: self._move_row(index.row(), 1))

        menu.exec(self.list_view.viewport().mapToGlobal(pos))

    def _move_row(self, row: int, delta: int) -> None:
        new_row = row + delta
        if 0 <= new_row < self.model.rowCount():
            self.move_requested.emit(row, new_row)

    def _update_header(self) -> None:
        self.header_label.setText(f"Cola ({self.model.rowCount()})")

    def _emit_remove(self) -> None:
        index = self.list_view.currentIndex()
        if index.isValid():
            self.remove_requested.emit(index.row())

    def _on_rows_moved(self, _parent, start: int, end: int, destination, row: int) -> None:
        if destination.isValid() and row != start:
            self.move_requested.emit(start, row)
