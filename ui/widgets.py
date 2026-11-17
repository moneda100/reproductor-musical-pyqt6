"""Widgets reutilizables de la interfaz."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

MARQUEE_INTERVAL_MS = 40
MARQUEE_GAP = 40

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons" / "svg"


def _icon_path(icon_name: str) -> Path:
    """Resuelve la ruta de un icono SVG en resources/icons/svg/."""
    return ICON_DIR / f"{icon_name}.svg"


def load_icon(icon_name: str, size: int = 24) -> QIcon:
    """Carga un icono SVG como QIcon con el tamaño indicado."""
    path = _icon_path(icon_name)
    if path.exists():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            return QIcon(pixmap)
    # Fallback: icono vacío para no romper la UI si falta el archivo.
    return QIcon()


class ClickableSlider(QSlider):
    """Slider que permite saltar de posición haciendo clic o arrastrando con precisión."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.pixelPosToRangeValue(event.position())
            self.setSliderDown(True)
            self.setValue(val)
            self._update_hover_tooltip(val)
            self.sliderPressed.emit()
            self.sliderMoved.emit(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        val = self.pixelPosToRangeValue(event.position())
        self._update_hover_tooltip(val)
        if self.isSliderDown() and (event.buttons() & Qt.MouseButton.LeftButton):
            self.setValue(val)
            self.sliderMoved.emit(val)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _update_hover_tooltip(self, val: int) -> None:
        if self.maximum() > self.minimum():
            secs = max(0, int(val))
            if secs >= 3600:
                h = secs // 3600
                m = (secs % 3600) // 60
                s = secs % 60
                tip = f"{h}:{m:02d}:{s:02d}"
            else:
                tip = f"{secs // 60}:{secs % 60:02d}"
            self.setToolTip(tip)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            val = self.pixelPosToRangeValue(event.position())
            self.setValue(val)
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle_rect = self.style().subControlRect(
            self.style().ComplexControl.CC_Slider,
            opt,
            self.style().SubControl.SC_SliderHandle,
            self,
        )
        if self.orientation() == Qt.Orientation.Horizontal:
            handle_len = (
                handle_rect.width() if handle_rect.isValid() and handle_rect.width() > 0 else 16
            )
            slider_len = self.width()
            pos_val = int(pos.x())
        else:
            handle_len = (
                handle_rect.height() if handle_rect.isValid() and handle_rect.height() > 0 else 16
            )
            slider_len = self.height()
            pos_val = int(pos.y())

        val = QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            pos_val - handle_len // 2,
            slider_len - handle_len,
            opt.upsideDown,
        )
        return max(self.minimum(), min(self.maximum(), val))


class IconButton(QPushButton):
    """Botón de icono SVG con nombre accesible y tooltip (accesibilidad).

    Carga un archivo SVG de ``resources/icons/svg/`` y lo muestra como
    ``QIcon`` en el botón. El aspecto (colores, fondo, bordes) lo define el
    tema activo a través de la QSS de la ventana. Esta clase solo fija
    geometría, cursor, foco y accesibilidad.

    Usa ``set_icon(icon_name)`` para cambiar el icono dinámicamente
    (por ejemplo, play/pausa o favorito activado/desactivado).
    """

    def __init__(
        self,
        icon_name: str,
        accessible_name: str,
        tooltip: str = "",
        size: int = 48,
        icon_size: int | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size or max(16, int(size * 0.5))
        self.setAccessibleName(accessible_name)
        self.setToolTip(tooltip or accessible_name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_icon(icon_name)
        # Sin texto: solo se muestra el icono SVG centrado.
        self.setText("")

    def set_icon(self, icon_name: str) -> None:
        """Cambia el icono del botón por el SVG indicado."""
        self._icon_name = icon_name
        self.setIcon(load_icon(icon_name, self._icon_size))
        self.setIconSize(QSize(self._icon_size, self._icon_size))


class CoverArtLabel(QLabel):
    """Muestra una portada con carga asíncrona y sin fugas de hilos.

    Corrección del bug original: ``t.disconnect()`` desconectaba **todas** las
    señales del hilo (incluida ``finished``), por lo que el hilo nunca se
    retiraba de ``active_threads``. Ahora se usa un token de generación: cada
    carga nueva invalida la anterior y el worker se cancela siempre.
    """

    def __init__(self, size: int = 200, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Música")
        self._generation = 0
        self._worker = None
        self.set_placeholder()

    def set_cover(self, image_source: str, provider=None) -> None:
        """Muestra la portada indicada (URL o ruta local)."""
        self._cancel_pending()
        if not image_source:
            self.set_placeholder()
            return

        if image_source.startswith("http"):
            if provider is None:
                from ui.image_provider import get_default_image_provider

                provider = get_default_image_provider()
            self._generation += 1
            generation = self._generation

            def on_ready(pixmap):
                if generation == self._generation:
                    self._apply_pixmap(pixmap)

            def on_error(_message):
                if generation == self._generation:
                    self.set_placeholder()

            self._worker = provider.request(image_source, on_ready, on_error)
        elif os.path.exists(image_source):
            pixmap = QPixmapLoader.load(image_source)
            self._apply_pixmap(pixmap)
        else:
            self.set_placeholder()

    def _cancel_pending(self) -> None:
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None

    def _apply_pixmap(self, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            self.set_placeholder()
            return
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def set_placeholder(self) -> None:
        self.clear()
        self.setStyleSheet(
            """
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1A1A1A, stop:1 #333);
            border-radius: 12px;
            font-size: 14px;
            font-weight: bold;
            color: #555;
            border: 1px solid #444;
            """
        )
        self.setText("Música")


class QPixmapLoader:
    """Carga de pixmaps desde disco (helper para evitar imports repetidos)."""

    @staticmethod
    def load(path: str):
        from PyQt6.QtGui import QPixmap

        return QPixmap(path)


class MarqueeLabel(QLabel):
    """Etiqueta con desplazamiento horizontal **bajo demanda**.

    Antes el ``QTimer`` de 30 ms estaba siempre activo (≈66 wakeups/s en
    reposo). Ahora solo corre cuando el texto no cabe y el control es visible.
    Respeta la preferencia del sistema ``prefers-reduced-motion``.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._offset = 0
        self._scroll_enabled = False
        self._text_width = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_scroll)
        self.setContentsMargins(5, 0, 5, 0)
        self.setWordWrap(False)
        # Asegurar que la fuente tenga un tamaño de punto válido
        font = self.font()
        if font.pointSize() <= 0:
            font.setPointSize(12)
            self.setFont(font)
        # Detectar preferencia de movimiento reducido del sistema
        self._reduced_motion = self._check_reduced_motion()
        # Escuchar cambios en la preferencia del sistema
        try:
            from PyQt6.QtGui import QGuiApplication
            QGuiApplication.styleHints().changed.connect(self._on_style_hints_changed)
        except Exception:
            pass

    def _check_reduced_motion(self) -> bool:
        """Verifica si el usuario prefiere movimiento reducido."""
        try:
            from PyQt6.QtGui import QGuiApplication
            hints = QGuiApplication.styleHints()
            # Qt 6.5+: prefersReducedMotion
            return getattr(hints, "prefersReducedMotion", lambda: False)()
        except Exception:
            return False

    def _on_style_hints_changed(self) -> None:
        """Reactiva al cambio de preferencias del sistema."""
        self._reduced_motion = self._check_reduced_motion()
        self._check_scroll()

    def setText(self, text):  # noqa: N802
        self._text = text or ""
        self._offset = 0
        super().setText(self._text)
        self._check_scroll()

    def text(self) -> str:
        return self._text

    # -- gestión del temporizador ----------------------------------
    def _check_scroll(self) -> None:
        metrics = self.fontMetrics()
        self._text_width = metrics.horizontalAdvance(self._text)
        needs_scroll = self._text_width > self.width() and self.width() > 0
        # Respetar prefers-reduced-motion: no animar si el usuario lo prefiere
        if self._reduced_motion:
            needs_scroll = False
        self._scroll_enabled = needs_scroll
        if not needs_scroll:
            self._offset = 0
            self._timer.stop()
        elif self.isVisible():
            self._timer.start(MARQUEE_INTERVAL_MS)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_scroll()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.WinIdChange, QEvent.Type.FontChange):
            self._check_scroll()

    def _update_scroll(self) -> None:
        if self.wordWrap():
            self.setWordWrap(False)
        if not self._scroll_enabled or not self.isVisible():
            self._timer.stop()
            return
        self._offset += 1
        if self._offset > self._text_width + MARQUEE_GAP:
            self._offset = -MARQUEE_GAP
        self.update()

    def paintEvent(self, event):
        if not self._scroll_enabled:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        metrics = self.fontMetrics()
        content_rect = self.contentsRect()
        y = (content_rect.height() - metrics.height()) / 2 + metrics.ascent()
        painter.drawText(content_rect.left() - self._offset, int(y), self._text)
        painter.drawText(
            content_rect.left() - self._offset + self._text_width + MARQUEE_GAP, int(y), self._text
        )
        painter.end()


class TrackListDelegate(QStyledItemDelegate):
    """Dibuja las pistas con portada, título, artista y duración."""

    def __init__(self, provider=None, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider
        # Caché de miniaturas ya escaladas: evita reescalar en cada repintado
        # al hacer scroll por listas largas.
        self._scaled_cache: dict[tuple[str, int, int], object] = {}

    @property
    def provider(self):
        return self._provider

    def set_provider(self, provider) -> None:
        self._provider = provider

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 56)

    def paint(self, painter: QPainter, option, index) -> None:
        from ui.models.track_list_model import TrackRoles

        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, QColor(40, 40, 40))
        elif hovered:
            painter.fillRect(rect, QColor(30, 30, 30))

        title = index.data(TrackRoles.Title) or ""
        artist = index.data(TrackRoles.Artist) or ""
        duration = index.data(TrackRoles.Duration) or 0
        cover_url = index.data(TrackRoles.CoverUrl) or ""
        is_current = bool(index.data(TrackRoles.Current))
        is_available = bool(index.data(TrackRoles.Available))

        cover_rect = QRect(rect.left() + 6, rect.top() + 6, 44, 44)
        pixmap = None
        if self._provider is not None and cover_url:
            pixmap = self._provider.cached_pixmap(cover_url)
        if pixmap is not None and not pixmap.isNull():
            cache_key = (cover_url, cover_rect.width(), cover_rect.height())
            scaled = self._scaled_cache.get(cache_key)
            if scaled is None:
                scaled = pixmap.scaled(
                    cover_rect.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if len(self._scaled_cache) >= 512:
                    self._scaled_cache.clear()
                self._scaled_cache[cache_key] = scaled
            painter.drawPixmap(cover_rect.topLeft(), scaled)
        else:
            painter.fillRect(cover_rect, QColor(50, 50, 50))

        text_rect = QRect(cover_rect.right() + 10, rect.top() + 6, rect.width() - 90, 44)

        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        if is_available:
            painter.setPen(QColor(255, 255, 255) if is_current else QColor(220, 220, 220))
        else:
            painter.setPen(QColor(120, 120, 120))
        painter.drawText(
            QRect(text_rect.left(), text_rect.top(), text_rect.width(), 20),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            _elide(painter, title, text_rect.width()),
        )

        small_font = QFont(option.font)
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        painter.setPen(QColor(170, 170, 170) if is_available else QColor(100, 100, 100))
        subtitle = artist
        if not is_available:
            subtitle = "No disponible en este dispositivo"
        painter.drawText(
            QRect(text_rect.left(), text_rect.top() + 20, text_rect.width(), 18),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            _elide(painter, subtitle, text_rect.width()),
        )

        if duration:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                QRect(rect.right() - 60, rect.top(), 54, rect.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                format_duration(duration),
            )

        if is_current:
            painter.setPen(QPen(QColor(29, 185, 84), 3))
            painter.drawLine(rect.topLeft(), rect.bottomLeft())

        painter.restore()


def _elide(painter: QPainter, text: str, width: int) -> str:
    metrics = painter.fontMetrics()
    return metrics.elidedText(text or "", Qt.TextElideMode.ElideRight, max(10, width))


def format_duration(seconds: float) -> str:
    """``125.0`` -> ``"2:05"``."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "--:--"
    if total < 0:
        return "--:--"
    return f"{total // 60}:{total % 60:02d}"


class VideoWidget(QWidget):
    """Marcador donde VLC incrusta el vídeo (Direct3D11 / X11 / Cocoa).

    Se usa tanto en la vista «Ahora reproduciendo» como en el mini
    reproductor. VLC solo puede apuntar a una superficie a la vez; la ventana
    principal decide cuál está activa.
    """

    double_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoSurface")
        # ``WA_NativeWindow`` basta para que VLC pinte sobre el HWND. En Qt6
        # ``WA_PaintOnScreen`` provoca el aviso «QWidget::paintEngine: Should no
        # longer be called», así que no se usa.
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #000000; border-radius: 8px;")

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        """Doble clic = pantalla completa, como en YouTube o VLC."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def clear(self) -> None:
        """Oculta la superficie y evita que VLC pinte sobre él al cerrar."""
        self.hide()


class _MiniDragBar(QWidget):
    """Barra superior del mini reproductor: arrastra la ventana."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MiniHeader")
        self.setFixedHeight(30)
        self._drag_offset = None

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class MiniPlayerWindow(QWidget):
    """Mini reproductor flotante con portada/vídeo y controles completos.

    Es una ventana separada de la principal pero comparte el mismo
    ``MusicPlayer``: la reproducción no se duplica. La superficie de vídeo se
    muestra bajo demanda y la ventana se adapta a ese modo.
    """

    close_requested = pyqtSignal()
    show_requested = pyqtSignal()
    play_toggled = pyqtSignal()
    next_requested = pyqtSignal()
    previous_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    video_toggled = pyqtSignal(bool)
    stay_on_top_changed = pyqtSignal(bool)
    undock_requested = pyqtSignal()
    dock_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, stay_on_top: bool = True) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle("Music Player Pro — mini")
        self.setObjectName("MiniPlayer")
        self.resize(380, 196)
        self.setMinimumWidth(350)
        self._user_seeking = False
        self._stay_on_top = stay_on_top
        self._is_docked = parent is not None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- barra superior arrastrable ---------------------------------
        self.header = _MiniDragBar(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 0, 6, 0)
        header_layout.setSpacing(6)
        brand = QLabel("♫  Music Player Pro")
        brand.setObjectName("MiniBrand")
        header_layout.addWidget(brand)
        header_layout.addStretch()

        self.expand_btn = QPushButton("⤢")
        self.expand_btn.setObjectName("MiniIconBtn")
        self.expand_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.expand_btn.setToolTip("Mostrar la ventana principal")
        self.expand_btn.setAccessibleName("Mostrar la ventana principal")
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.clicked.connect(self.show_requested.emit)
        header_layout.addWidget(self.expand_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("MiniCloseBtn")
        self.close_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.close_btn.setToolTip("Cerrar el mini reproductor")
        self.close_btn.setAccessibleName("Cerrar el mini reproductor")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.close_btn)

        # -- botón "siempre visible" (stay on top) ------------------------
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setObjectName("MiniIconBtn")
        self.pin_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.pin_btn.setToolTip("Mantener siempre visible (siempre encima)")
        self.pin_btn.setAccessibleName("Mantener siempre visible")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.clicked.connect(self._toggle_stay_on_top)
        header_layout.addWidget(self.pin_btn)

        # -- botón desacoplar/acoplar ------------------------------------
        self.dock_btn = QPushButton("⛶")
        self.dock_btn.setObjectName("MiniIconBtn")
        self.dock_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.dock_btn.setToolTip("Desacoplar del reproductor principal")
        self.dock_btn.setAccessibleName("Desacoplar/acoplar")
        self.dock_btn.setCheckable(True)
        self.dock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dock_btn.clicked.connect(self._toggle_dock)
        header_layout.addWidget(self.dock_btn)

        # Inicializar estado del botón y flags de ventana
        self.pin_btn.setChecked(self._stay_on_top)
        self.dock_btn.setChecked(self._is_docked)
        self.dock_btn.setToolTip(
            "Desacoplar del reproductor principal"
            if self._is_docked
            else "Acoplar al reproductor principal"
        )
        self._update_window_flags()
        outer.addWidget(self.header)

        # -- cuerpo ------------------------------------------------------
        body = QWidget(self)
        body.setObjectName("MiniBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 8, 12, 12)
        body_layout.setSpacing(8)

        self.cover_view = QWidget(body)
        cover_layout = QHBoxLayout(self.cover_view)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(12)

        self.cover_label = CoverArtLabel(88, self.cover_view)
        self.cover_label.setFixedSize(88, 88)
        cover_layout.addWidget(self.cover_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title_label = MarqueeLabel(self.cover_view)
        self.title_label.setObjectName("MiniTitle")
        self.artist_label = QLabel("—")
        self.artist_label.setObjectName("MutedLabel")
        self.album_label = QLabel("")
        self.album_label.setObjectName("HintLabel")
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.artist_label)
        info_layout.addWidget(self.album_label)
        info_layout.addStretch()
        cover_layout.addLayout(info_layout, stretch=1)
        body_layout.addWidget(self.cover_view)

        self.video_widget = VideoWidget(body)
        self.video_widget.setMinimumHeight(180)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_widget.hide()
        body_layout.addWidget(self.video_widget, stretch=1)

        # -- progreso ----------------------------------------------------
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        self.progress_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setAccessibleName("Posición de reproducción")
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("HintLabel")
        progress_layout.addWidget(self.progress_slider, stretch=1)
        progress_layout.addWidget(self.time_label)
        body_layout.addLayout(progress_layout)

        # -- controles ---------------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.previous_btn = QPushButton("⏮")
        self.previous_btn.setObjectName("MiniControlBtn")
        self.previous_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.previous_btn.setAccessibleName("Pista anterior")
        self.previous_btn.setToolTip("Pista anterior")
        self.previous_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.previous_btn.clicked.connect(self.previous_requested.emit)

        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("MiniPlayBtn")
        self.play_btn.setFixedSize(48, 48)
        self.play_btn.setAccessibleName("Reproducir o pausar")
        self.play_btn.setToolTip("Reproducir o pausar")
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.play_toggled.emit)

        self.next_btn = QPushButton("⏭")
        self.next_btn.setObjectName("MiniControlBtn")
        self.next_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.next_btn.setAccessibleName("Pista siguiente")
        self.next_btn.setToolTip("Pista siguiente")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(self.next_requested.emit)

        self.video_btn = QPushButton("📺")
        self.video_btn.setObjectName("MiniControlBtn")
        self.video_btn.setFixedSize(44, 44)  # WCAG 2.5.5 target size
        self.video_btn.setCheckable(True)
        self.video_btn.setAccessibleName("Mostrar vídeo en el mini reproductor")
        self.video_btn.setToolTip("Mostrar u ocultar la vista de vídeo")
        self.video_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_btn.clicked.connect(self._on_video_clicked)
        self.video_btn.hide()
        # Estilo base para el botón de vídeo
        self.video_btn.setStyleSheet("""
            QPushButton#MiniControlBtn:checked {
                background-color: rgba(29, 185, 84, 0.3);
                border: 1px solid #1DB954;
                border-radius: 6px;
            }
        """)

        controls.addWidget(self.previous_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.video_btn)
        controls.addStretch()

        volume_icon = QLabel("🔊")
        volume_icon.setObjectName("HintLabel")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(88)
        self.volume_slider.setAccessibleName("Volumen del mini reproductor")
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        controls.addWidget(volume_icon)
        controls.addWidget(self.volume_slider)
        body_layout.addLayout(controls)

        outer.addWidget(body, stretch=1)

    # -- información ---------------------------------------------------
    def set_track_info(self, title: str, artist: str = "", album: str = "") -> None:
        self.title_label.setText(title or "—")
        self.title_label.setToolTip(title or "")
        self.artist_label.setText(artist or "—")
        self.album_label.setText(album or "")

    def set_cover(self, image_source: str, provider=None) -> None:
        self.cover_label.set_cover(image_source, provider)

    def set_playing(self, playing: bool) -> None:
        self.play_btn.setText("⏸" if playing else "▶")
        self.play_btn.setAccessibleName("Pausar" if playing else "Reproducir")
        self.play_btn.setToolTip("Pausar" if playing else "Reproducir")

    def set_volume(self, value: int) -> None:
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(max(0, min(100, int(value))))
        self.volume_slider.blockSignals(False)

    def set_position(self, seconds: float, duration: float = 0.0) -> None:
        duration_value = max(0.0, float(duration or 0.0))
        if duration_value > 0:
            maximum = max(0, int(duration_value))
            if self.progress_slider.maximum() != maximum:
                self.progress_slider.setRange(0, maximum)
        seconds_value = max(0.0, float(seconds or 0.0))
        if self._user_seeking:
            target = (
                self._seek_target
                if getattr(self, "_seek_target", None) is not None
                else self.progress_slider.value()
            )
            if (
                getattr(self, "_seek_target", None) is not None
                and abs(seconds_value - self._seek_target) <= 2.0
            ):
                self._user_seeking = False
                self._seek_target = None
                if getattr(self, "_seek_timer", None) and self._seek_timer.isActive():
                    self._seek_timer.stop()
            else:
                self._update_time_label(float(target), duration_value)
                if self.progress_slider.maximum() > 0:
                    self.progress_slider.setValue(
                        min(self.progress_slider.maximum(), max(0, int(target)))
                    )
                return

        if self.progress_slider.maximum() > 0:
            self.progress_slider.setValue(min(self.progress_slider.maximum(), int(seconds_value)))
        self._update_time_label(seconds_value, duration_value)

    # -- vídeo ----------------------------------------------------------
    def _apply_video_mode(self, enabled: bool) -> None:
        self.cover_view.setVisible(not enabled)
        self.video_widget.setVisible(enabled)
        if enabled:
            self.resize(max(420, self.width()), 392)
            self.video_widget.setFixedHeight(180)
        else:
            self.resize(self.width(), 196)

    def _update_window_flags(self) -> None:
        """Actualiza los flags de ventana según el estado 'stay on top'."""
        was_visible = self.isVisible()
        flags = self.windowFlags()
        if self._stay_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if was_visible:
            self.show()  # Necesario para aplicar el cambio de flags solo si ya estaba visible

    def _toggle_stay_on_top(self) -> None:
        """Alterna el modo 'siempre encima'."""
        self._stay_on_top = self.pin_btn.isChecked()
        self._update_window_flags()
        self.stay_on_top_changed.emit(self._stay_on_top)
        self.pin_btn.setToolTip(
            "Desactivar 'siempre encima'" if self._stay_on_top else "Activar 'siempre encima'"
        )
        self.pin_btn.setToolTip(
            "Desactivar 'siempre encima'" if self._stay_on_top else "Activar 'siempre encima'"
        )

    def _toggle_dock(self) -> None:
        """Alterna entre modo acoplado y desacoplado."""
        # El botón ya ha cambiado su estado (checked/unchecked) por el click
        self._is_docked = self.dock_btn.isChecked()
        if self._is_docked:
            self.dock_btn.setToolTip("Desacoplar del reproductor principal")
            self.dock_requested.emit()
        else:
            self.dock_btn.setToolTip("Acoplar al reproductor principal")
            self.undock_requested.emit()

    def set_video_available(self, available: bool) -> None:
        self.video_btn.setVisible(bool(available))
        if available:
            # Hacer el botón más visible cuando hay vídeo disponible
            self.video_btn.setStyleSheet("""
                QPushButton#MiniControlBtn {
                    background-color: rgba(29, 185, 84, 0.2);
                    border: 1px solid #1DB954;
                    border-radius: 6px;
                }
                QPushButton#MiniControlBtn:hover {
                    background-color: rgba(29, 185, 84, 0.4);
                    border: 1px solid #1DB954;
                }
            """)
        else:
            self.video_btn.setStyleSheet("")
        if not available and self.video_btn.isChecked():
            self.set_video_enabled(False)

    def video_enabled(self) -> bool:
        return self.video_btn.isChecked()

    def set_video_enabled(self, enabled: bool) -> None:
        """Cambia el modo vídeo sin reemitir ``video_toggled``."""
        self.video_btn.blockSignals(True)
        self.video_btn.setChecked(bool(enabled))
        self.video_btn.blockSignals(False)
        self._apply_video_mode(bool(enabled))

    def _on_video_clicked(self, checked: bool) -> None:
        self._apply_video_mode(bool(checked))
        self.video_toggled.emit(bool(checked))

    def _apply_video_mode(self, enabled: bool) -> None:
        self.cover_view.setVisible(not enabled)
        self.video_widget.setVisible(enabled)
        if enabled:
            self.resize(max(420, self.width()), 392)
        else:
            self.resize(self.width(), 196)

    # -- progreso -------------------------------------------------------
    def _on_slider_pressed(self) -> None:
        self._user_seeking = True
        self._seek_target = None
        if getattr(self, "_seek_timer", None) and self._seek_timer.isActive():
            self._seek_timer.stop()

    def _on_slider_moved(self, value: int) -> None:
        duration = float(self.progress_slider.maximum())
        self._update_time_label(float(value), duration)

    def _on_slider_released(self) -> None:
        self._seek_target = int(self.progress_slider.value())
        duration = float(self.progress_slider.maximum())
        self._update_time_label(float(self._seek_target), duration)
        if getattr(self, "_seek_timer", None) is None:
            from PyQt6.QtCore import QTimer

            self._seek_timer = QTimer(self)
            self._seek_timer.setSingleShot(True)
            self._seek_timer.timeout.connect(self._reset_seeking)
        else:
            self._seek_timer.stop()
        self._seek_timer.start(1500)
        self.seek_requested.emit(self._seek_target)

    def _reset_seeking(self) -> None:
        self._user_seeking = False
        self._seek_target = None

    def _update_time_label(self, seconds: float, duration: float) -> None:
        self.time_label.setText(f"{format_duration(seconds)} / {format_duration(duration)}")
