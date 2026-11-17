"""Panel de letras con la línea activa resaltada y estados de carga/vacío."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.lyrics import LyricLine, active_line_index


class LyricsPanel(QWidget):
    """Muestra la letra y resalta la línea que suena en cada momento.

    Estados:
      - Cargando: spinner/mensaje "Buscando letras…"
      - Sin letras: mensaje informativo
      - Con letras: letra sincronizada con línea activa resaltada
    """

    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.header_label = QLabel("Letras")
        self.header_label.setObjectName("TitleLabel")
        header.addWidget(self.header_label)
        header.addStretch()

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setObjectName("SecondaryBtn")
        self.close_btn.clicked.connect(self.closed.emit)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.text_browser = QTextBrowser(self)
        self.text_browser.setObjectName("LyricsView")
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                font-size: 16px;
                line-height: 1.6;
                color: #E0E0E0;
            }
        """)
        layout.addWidget(self.text_browser, stretch=1)

        self._lines: list[LyricLine] = []
        self._active_index = -1
        self._loading = False

    # -- estados ---------------------------------------------------------
    def set_loading(self, loading: bool = True) -> None:
        """Muestra u oculta el indicador de carga."""
        self._loading = loading
        if loading:
            self.text_browser.setPlainText("Buscando letras…")
            self.text_browser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.text_browser.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def set_no_lyrics(self) -> None:
        """Muestra un mensaje informativo cuando no hay letras disponibles."""
        self._lines = []
        self._active_index = -1
        self.text_browser.clear()
        self.text_browser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                font-size: 16px;
                color: #888888;
            }
        """)
        self.text_browser.setPlainText(
            "No se encontraron letras para esta canción.\n"
            "Prueba con otra pista o verifica tu conexión a Internet."
        )

    def clear(self) -> None:
        self._lines = []
        self._active_index = -1
        self._loading = False
        self.text_browser.clear()
        self.text_browser.setAlignment(Qt.AlignmentFlag.AlignLeft)

    # -- carga de letra --------------------------------------------------
    def set_lyrics(self, lines: list[LyricLine], plain: str = "") -> None:
        """Carga la letra en el visor con estilo Spotify."""
        self._loading = False
        self._lines = list(lines or [])
        self._active_index = -1
        self.text_browser.clear()
        self.text_browser.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                font-size: 16px;
                line-height: 1.6;
                color: #E0E0E0;
            }
        """)
        if not self._lines and plain:
            self.text_browser.setPlainText(plain)
            return
        for line in self._lines:
            self.text_browser.append(line.text)
        self.text_browser.moveCursor(QTextCursor.MoveOperation.Start)

    # -- resaltado de línea activa ---------------------------------------
    def set_position(self, position_ms: int) -> None:
        """Resalta la línea que corresponde a la posición actual."""
        if not self._lines:
            return
        index = active_line_index(self._lines, position_ms)
        if index == self._active_index:
            return
        self._active_index = index

        cursor = self.text_browser.textCursor()
        cursor.clearSelection()

        normal = QTextCharFormat()
        normal.setForeground(QColor(120, 120, 120))
        normal.setFontPointSize(14)

        highlight = QTextCharFormat()
        highlight.setForeground(QColor(255, 255, 255))
        highlight.setFontWeight(700)
        highlight.setFontPointSize(18)

        active_position = None
        block = self.text_browser.document().firstBlock()
        for line_number in range(len(self._lines)):
            if not block.isValid():
                break
            if line_number == index:
                active_position = block.position()
            cursor.setPosition(block.position())
            cursor.setPosition(
                block.position() + block.length() - 1,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.setCharFormat(highlight if line_number == index else normal)
            block = block.next()

        cursor.clearSelection()
        if active_position is not None:
            cursor.setPosition(active_position)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.ensureCursorVisible()
