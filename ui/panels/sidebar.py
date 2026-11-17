"""Barra lateral de navegación (Inicio / Biblioteca / Playlists / Favoritos / Historial)."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ui.widgets import load_icon


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon_name: str  # nombre del archivo SVG en resources/icons/svg/ (sin extensión)


NAV_ITEMS = (
    NavItem("home", "Inicio", "home"),
    NavItem("library", "Biblioteca", "library"),
    NavItem("playlists", "Playlists", "playlists"),
    NavItem("favorites", "Favoritos", "favorite_on"),
    NavItem("history", "Historial", "history"),
)

ICON_SIZE = 20  # px


class Sidebar(QWidget):
    """Barra lateral con la navegación principal."""

    navigated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("NavList")
        self.list_widget.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        layout.addWidget(self.list_widget)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)

        for item in NAV_ITEMS:
            entry = QListWidgetItem(item.label)
            entry.setIcon(load_icon(item.icon_name, ICON_SIZE))
            entry.setData(Qt.ItemDataRole.UserRole, item.key)
            entry.setData(Qt.ItemDataRole.AccessibleTextRole, item.label)
            entry.setToolTip(item.label)
            self.list_widget.addItem(entry)

        self.list_widget.setCurrentRow(0)

    def _on_current_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key:
            self.navigated.emit(key)

    def select(self, key: str) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.list_widget.setCurrentRow(row)
                return

    def current_key(self) -> str:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else "home"
