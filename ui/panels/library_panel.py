"""Panel de la biblioteca: árbol con modelo de datos, filtro y modos de vista."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ui.models.library_tree_model import LibraryFilterProxy, LibraryTreeModel


class LibraryPanel(QWidget):
    """Explorador de la biblioteca musical."""

    add_folder_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    play_requested = pyqtSignal(str)
    edit_tags_requested = pyqtSignal(str)
    view_mode_changed = pyqtSignal(int)
    filter_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.model = LibraryTreeModel(self)
        self.proxy = LibraryFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self._entries: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        self.add_folder_btn = QPushButton("📁 Añadir carpeta")
        self.add_folder_btn.clicked.connect(self.add_folder_requested.emit)

        self.clear_btn = QPushButton("🧹 Limpiar")
        self.clear_btn.setObjectName("SecondaryBtn")
        self.clear_btn.clicked.connect(self.clear_requested.emit)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filtrar biblioteca…")
        self.filter_input.setAccessibleName("Filtrar la biblioteca")
        self.filter_input.textChanged.connect(self._on_filter_changed)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["📂 Carpetas", "🎤 Artistas", "💿 Álbumes"])
        self.view_mode_combo.currentIndexChanged.connect(self.view_mode_changed.emit)

        tools.addWidget(self.add_folder_btn)
        tools.addWidget(self.clear_btn)
        tools.addWidget(self.filter_input, stretch=1)
        tools.addWidget(QLabel("Vista:"))
        tools.addWidget(self.view_mode_combo)
        layout.addLayout(tools)

        self.tree_view = QTreeView(self)
        self.tree_view.setObjectName("LibraryTree")
        self.tree_view.setModel(self.proxy)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setIndentation(15)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)
        self.tree_view.doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.tree_view, stretch=1)

        self.model.count_changed.connect(self._on_count_changed)
        self._status = QLabel("")
        self._status.setObjectName("StatusLabel")
        layout.addWidget(self._status)

    # -- datos --------------------------------------------------------
    def set_entries(self, entries: list[dict]) -> None:
        """Reconstruye el árbol completo."""
        self._entries = list(entries)
        self.model.set_entries(self._entries, self.view_mode_combo.currentIndex())

    def append_entries(self, entries: list[dict]) -> None:
        """Añade entradas de forma incremental (escaneo en curso)."""
        self._entries.extend(entries)
        self.model.add_entries(entries)

    def rebuild(self) -> None:
        """Reconstruye el árbol conservando las entradas (cambio de vista)."""
        self.model.set_entries(self._entries, self.view_mode_combo.currentIndex())

    def clear(self) -> None:
        self._entries = []
        self.model.clear()
        self._status.setText("Biblioteca vacía.")

    def view_mode(self) -> int:
        return self.view_mode_combo.currentIndex()

    def _on_count_changed(self, count: int) -> None:
        self._status.setText(f"{count} pistas en la biblioteca")

    def _on_filter_changed(self, text: str) -> None:
        self.proxy.set_filter_text(text)
        self.filter_changed.emit(text)

    # -- interacción ---------------------------------------------------
    def _selected_path(self) -> str | None:
        index = self.tree_view.currentIndex()
        if not index.isValid():
            return None
        from ui.models.library_tree_model import LibraryRoles, NodeKind

        if index.data(LibraryRoles.Kind) != int(NodeKind.TRACK):
            return None
        return index.data(LibraryRoles.Path)

    def _on_double_clicked(self, index) -> None:
        from ui.models.library_tree_model import LibraryRoles, NodeKind

        if index.data(LibraryRoles.Kind) != int(NodeKind.TRACK):
            return
        path = index.data(LibraryRoles.Path)
        if path:
            self.play_requested.emit(path)

    def _show_context_menu(self, pos) -> None:
        index = self.tree_view.indexAt(pos)
        menu = QMenu(self)
        if index.isValid():
            from ui.models.library_tree_model import LibraryRoles, NodeKind

            if index.data(LibraryRoles.Kind) == int(NodeKind.TRACK):
                path = index.data(LibraryRoles.Path)
                play = menu.addAction("▶ Añadir y reproducir")
                play.triggered.connect(lambda: self.play_requested.emit(path))
                edit = menu.addAction("🏷️ Editar etiquetas")
                edit.triggered.connect(lambda: self.edit_tags_requested.emit(path))
                menu.addSeparator()
        add = menu.addAction("📁 Añadir carpeta…")
        add.triggered.connect(self.add_folder_requested.emit)
        menu.exec(self.tree_view.viewport().mapToGlobal(pos))
