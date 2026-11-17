"""Diálogo de detección y purga de duplicados."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DuplicatesDialog(QWidget):
    """Muestra los grupos de duplicados y permite purgar los sobrantes."""

    purge_requested = pyqtSignal(list)  # rutas a eliminar

    def __init__(self, groups: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.groups = list(groups)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self.header_label = QLabel(
            f"Duplicados encontrados: {sum(group.count - 1 for group in self.groups)}"
        )
        self.header_label.setObjectName("TitleLabel")
        layout.addWidget(self.header_label)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Grupo", "Pista", "Duración", "Ruta"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 220)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.tree, stretch=1)

        for group in self.groups:
            parent_item = QTreeWidgetItem([f"Grupo ({group.count} pistas)", "", "", ""])
            self.tree.addTopLevelItem(parent_item)
            for track in group.tracks:
                child = QTreeWidgetItem(
                    [
                        "",
                        f"{track.artist} — {track.title}",
                        f"{int(track.duration or 0) // 60}:{int(track.duration or 0) % 60:02d}",
                        track.file_path,
                    ]
                )
                child.setData(0, Qt.ItemDataRole.UserRole, track.file_path)
                parent_item.addChild(child)
            parent_item.setExpanded(True)

        buttons = QHBoxLayout()
        buttons.addStretch()
        keep_btn = QPushButton("Conservar el primero")
        keep_btn.setObjectName("SecondaryBtn")
        keep_btn.clicked.connect(self._purge_extra)
        buttons.addWidget(keep_btn)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _purge_extra(self) -> None:
        """Propone eliminar todas las copias menos la primera de cada grupo."""
        victims: list[str] = []
        for group in self.groups:
            for track in group.tracks[1:]:
                if track.file_path:
                    victims.append(track.file_path)
        self.purge_requested.emit(victims)
        self.close()
