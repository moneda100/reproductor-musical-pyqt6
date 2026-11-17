"""Ventana independiente del gestor de descargas.

El gestor **no** vive dentro de la ventana principal: es una ventana propia,
no modal, para que la interfaz de reproducción/búsqueda quede limpia y las
descargas puedan seguir en segundo plano sin mezclarse con el resto de la UI.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.panels.downloads_panel import DownloadsPanel


class DownloadManagerDialog(QDialog):
    """Contenedor profesional alrededor de :class:`DownloadsPanel`."""

    def __init__(
        self,
        parent: QWidget | None = None,
        destination: str = "",
        audio_format: str = "mp3",
        mode: str = "playlist",
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("DownloadManager")
        self.setWindowTitle("Music Player Pro — Gestor de descargas")
        self.setModal(False)
        self.resize(980, 640)
        self.setMinimumSize(820, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QWidget(self)
        header.setObjectName("ManagerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Gestor de descargas")
        title.setObjectName("ManagerTitle")
        subtitle = QLabel(
            "Elige la lista completa o canciones sueltas, la carpeta y el formato. "
            "El progreso se actualiza canción a canción."
        )
        subtitle.setObjectName("HintLabel")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header_layout.addLayout(titles, stretch=1)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setObjectName("GhostBtn")
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header)

        self.panel = DownloadsPanel(
            destination=destination,
            audio_format=audio_format,
            mode=mode,
            parent=self,
        )
        layout.addWidget(self.panel, stretch=1)

    def show_and_raise(self) -> None:
        """Muestra la ventana y la trae al frente sin bloquear la principal."""
        self.show()
        self.raise_()
        self.activateWindow()
