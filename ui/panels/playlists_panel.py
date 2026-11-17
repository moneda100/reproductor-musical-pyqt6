"""Panel de gestión de playlists múltiples."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PlaylistsPanel(QWidget):
    """Lista de playlists guardadas con acciones de gestión."""

    playlist_opened = pyqtSignal(str)  # playlist_id
    create_requested = pyqtSignal()
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    duplicate_requested = pyqtSignal(str)
    import_requested = pyqtSignal()
    export_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.header_label = QLabel("Playlists")
        self.header_label.setObjectName("TitleLabel")
        header.addWidget(self.header_label)
        header.addStretch()

        self.new_btn = QPushButton("➕ Nueva")
        self.new_btn.clicked.connect(self.create_requested.emit)
        header.addWidget(self.new_btn)

        self.import_btn = QPushButton("📥 Importar")
        self.import_btn.setObjectName("SecondaryBtn")
        self.import_btn.clicked.connect(self.import_requested.emit)
        header.addWidget(self.import_btn)

        self.export_btn = QPushButton("📤 Exportar")
        self.export_btn.setObjectName("SecondaryBtn")
        self.export_btn.clicked.connect(self._emit_export)
        header.addWidget(self.export_btn)
        layout.addLayout(header)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("PlaylistList")
        self.list_widget.itemDoubleClicked.connect(self._on_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget, stretch=1)

    def set_playlists(self, playlists: list[dict]) -> None:
        self.list_widget.clear()
        for playlist in playlists:
            item = QListWidgetItem(playlist.get("name", "Sin nombre"))
            item.setData(Qt.ItemDataRole.UserRole, playlist.get("id", ""))
            item.setToolTip(playlist.get("name", ""))
            self.list_widget.addItem(item)
        self.header_label.setText(f"Playlists ({len(playlists)})")

    def current_id(self) -> str:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        if playlist_id:
            self.playlist_opened.emit(playlist_id)

    def _emit_export(self) -> None:
        playlist_id = self.current_id()
        if playlist_id:
            self.export_requested.emit(playlist_id)

    def _show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        open_action = menu.addAction("▶ Abrir")
        open_action.triggered.connect(lambda: self.playlist_opened.emit(playlist_id))
        menu.addSeparator()
        rename_action = menu.addAction("✏️ Renombrar")
        rename_action.triggered.connect(lambda: self.rename_requested.emit(playlist_id))
        duplicate_action = menu.addAction("⧉ Duplicar")
        duplicate_action.triggered.connect(lambda: self.duplicate_requested.emit(playlist_id))
        export_action = menu.addAction("📤 Exportar")
        export_action.triggered.connect(lambda: self.export_requested.emit(playlist_id))
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Eliminar")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(playlist_id))
        menu.exec(self.list_widget.viewport().mapToGlobal(pos))
