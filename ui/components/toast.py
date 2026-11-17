"""Capa de feedback: avisos flotantes (toasts) no intrusivos.

Sustituye al único ``status_label``, que se pisaba a sí mismo y dejaba los
errores invisibles.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

TOAST_TYPES = {
    "info": ("#1E1E1E", "#E0E0E0", "ℹ"),
    "success": ("#12351F", "#7BE49B", "✔"),
    "warning": ("#3A2E12", "#F2C14E", "⚠"),
    "error": ("#3A1618", "#FF8A8A", "✖"),
    "progress": ("#1E1E1E", "#E0E0E0", "⏳"),
}


class Toast(QFrame):
    """Aviso individual con icono, texto y botón de cierre opcional."""

    closed = pyqtSignal()

    def __init__(
        self,
        message: str,
        toast_type: str = "info",
        duration_ms: int = 3500,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._duration_ms = duration_ms
        background, foreground, icon = TOAST_TYPES.get(toast_type, TOAST_TYPES["info"])

        self.setObjectName("Toast")
        self.setStyleSheet(
            f"""
            QFrame#Toast {{
                background-color: {background};
                border: 1px solid {foreground};
                border-radius: 10px;
            }}
            QLabel#ToastText {{ color: {foreground}; font-size: 12px; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {foreground}; font-size: 13px;")
        layout.addWidget(icon_label)

        self.text_label = QLabel(message)
        self.text_label.setObjectName("ToastText")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, stretch=1)

    def set_message(self, message: str) -> None:
        self.text_label.setText(message)

    def set_type(self, toast_type: str) -> None:
        background, foreground, icon = TOAST_TYPES.get(toast_type, TOAST_TYPES["info"])
        self.setStyleSheet(
            f"""
            QFrame#Toast {{
                background-color: {background};
                border: 1px solid {foreground};
                border-radius: 10px;
            }}
            QLabel#ToastText {{ color: {foreground}; font-size: 12px; }}
            """
        )
        self.text_label.setText(self.text_label.text())


class ToastOverlay(QWidget):
    """Contenedor que apila los toasts en la esquina inferior derecha."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self._toasts: list[Toast] = []
        self._animations: list[QPropertyAnimation] = []

    def show_toast(self, message: str, toast_type: str = "info", duration_ms: int = 3500) -> Toast:
        """Muestra un aviso y lo retira solo tras la duración indicada."""
        toast = Toast(message, toast_type, duration_ms, self)
        self._layout.addWidget(toast)
        self._toasts.append(toast)
        self._reposition()

        toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        if duration_ms > 0:
            QTimer.singleShot(duration_ms, lambda: self.dismiss(toast))
        return toast

    def dismiss(self, toast: Toast) -> None:
        try:
            if toast in self._toasts:
                self._toasts.remove(toast)
            toast.setParent(None)
            toast.deleteLater()
            self._reposition()
        except (RuntimeError, AttributeError):
            pass

    def clear(self) -> None:
        for toast in list(self._toasts):
            self.dismiss(toast)

    def _reposition(self) -> None:
        self.adjustSize()
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            QPoint(
                max(0, parent.width() - self.width() - 20),
                max(0, parent.height() - self.height() - 20),
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()


def show_toast(parent: QWidget, message: str, toast_type: str = "info") -> Toast:
    """Atajo: encuentra el overlay del padre y muestra un aviso."""
    overlay = parent.findChild(ToastOverlay)
    if overlay is None:
        overlay = ToastOverlay(parent)
    return overlay.show_toast(message, toast_type)
