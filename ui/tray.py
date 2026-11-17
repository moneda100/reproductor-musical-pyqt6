"""Bandeja del sistema y minireproductor."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """Icono en la bandeja con menú de control y minireproductor."""

    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    previous_requested = pyqtSignal()
    show_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip("Music Player Pro")
        self._set_default_icon()
        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        show_action = QAction("Mostrar Music Player Pro", self)
        show_action.triggered.connect(self.show_requested.emit)
        self._menu.addAction(show_action)
        self._menu.addSeparator()

        self._play_action = QAction("Reproducir", self)
        self._play_action.triggered.connect(self.play_pause_requested.emit)
        self._menu.addAction(self._play_action)

        prev_action = QAction("Anterior", self)
        prev_action.triggered.connect(self.previous_requested.emit)
        self._menu.addAction(prev_action)

        next_action = QAction("Siguiente", self)
        next_action.triggered.connect(self.next_requested.emit)
        self._menu.addAction(next_action)

        self._menu.addSeparator()
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)

    def set_playing(self, playing: bool) -> None:
        self._play_action.setText("Pausar" if playing else "Reproducir")

    def set_track(self, title: str, artist: str = "") -> None:
        text = f"{artist} — {title}" if artist else title
        self.setToolTip(f"Music Player Pro\n{text}" if text else "Music Player Pro")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()

    def _set_default_icon(self) -> None:
        """Establece un icono por defecto para la bandeja del sistema.

        La ruta se resuelve respecto a este archivo (no al directorio de
        trabajo actual) para que funcione tanto al ejecutar desde el repositorio
        como desde el instalador. Si falta el recurso, se dibuja un ícono de
        respaldo visible (letra M sobre color de acento) en lugar de uno
        transparente que quedaría invisible en la bandeja.
        """
        from pathlib import Path

        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icons" / "app_icon.png"
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
            return

        # Ícono de respaldo visible: letra M sobre color de acento.
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor("#1DB954")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(2, 2, 30, 30, 8, 8)
            painter.setPen(QPen(QColor("#FFFFFF")))
            font = painter.font()
            font.setPointSize(20)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")
        finally:
            painter.end()
        self.setIcon(QIcon(pixmap))
