"""Panel «Ahora reproduciendo»: portada, información y acciones.

La reproducción (play/pausa, anterior/siguiente, aleatorio, repetir,
progreso, volumen y silencio) vive en un único lugar: ``ControlsPanel``,
siempre visible en la parte inferior de la ventana. Este panel no duplica
esos controles; solo muestra la portada, los metadatos, el vídeo opcional
y las acciones propias de la pista (favorito, letras, carpeta y mini).

┌─────────────────────────────────────────────────────────────────┐
│  [Carátula grande]    AHORA REPRODUCIENDO                        │
│                       Título de la pista                          │
│                       Artista                                     │
│                       Álbum · formato/bitrate                     │
│                                                                   │
│  [ FAVORITO ] [ LETRAS ] [ CARPETA ] [ MINI ]                     │
└─────────────────────────────────────────────────────────────────┘

Cuando hay vídeo disponible, el área central se sustituye por el vídeo
sin dejar huecos vacíos. Todos los botones tienen texto, tooltip y nombre
accesible.
"""

from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import CoverArtLabel, MarqueeLabel, VideoWidget


class VideoSizeMode(Enum):
    """Modos de visualización del vídeo incrustado."""

    STANDARD = "standard"
    CINEMA = "cinema"
    FULLSCREEN = "fullscreen"
    RESIZABLE = "resizable"

    def label(self) -> str:
        return {
            VideoSizeMode.STANDARD: "Estándar",
            VideoSizeMode.CINEMA: "Cine",
            VideoSizeMode.FULLSCREEN: "Pantalla completa",
            VideoSizeMode.RESIZABLE: "Responsivo",
        }[self]


VIDEO_SIZE_STANDARD = QSize(640, 360)
VIDEO_SIZE_CINEMA = QSize(1280, 720)
VIDEO_MIN_SIZE = QSize(320, 180)
VIDEO_ASPECT_RATIO = 16 / 9
_SIZE_MAX = 16777215


class ResizableVideoFrame(QFrame):
    """Contenedor del vídeo que se adapta al espacio disponible."""

    size_changed = pyqtSignal(QSize)
    mode_changed = pyqtSignal(VideoSizeMode)
    double_clicked = pyqtSignal()

    _GRAB = 8

    def __init__(self, video_widget: VideoWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoFrame")
        self.video_widget = video_widget
        self.video_widget.setParent(self)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.video_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.mode = VideoSizeMode.STANDARD
        self._fixed_size = QSize(VIDEO_SIZE_STANDARD)
        self._available = QSize(VIDEO_SIZE_STANDARD)
        self._resizing = False
        self._edge = ""
        self._press_pos = QPoint()
        self._press_size = QSize()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(VIDEO_MIN_SIZE)
        self.apply_mode()

    def apply_mode(self) -> None:
        if self.mode in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
            self.setMinimumSize(VIDEO_MIN_SIZE)
            self.setMaximumSize(_SIZE_MAX, _SIZE_MAX)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.setMinimumSize(VIDEO_MIN_SIZE)
            self.setMaximumSize(_SIZE_MAX, _SIZE_MAX)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        avail = self._available
        if not avail.isValid() or avail.width() <= 0 or avail.height() <= 0:
            parent = self.parentWidget()
            if parent is not None:
                avail = parent.size()
        self.fit_to(avail)
        self.updateGeometry()

    def set_mode(self, mode: VideoSizeMode) -> None:
        if self.mode == mode:
            return
        self.mode = mode
        if mode == VideoSizeMode.STANDARD:
            self._fixed_size = QSize(VIDEO_SIZE_STANDARD)
        elif mode == VideoSizeMode.CINEMA:
            self._fixed_size = QSize(VIDEO_SIZE_CINEMA)
        self.apply_mode()
        self.mode_changed.emit(mode)

    def set_size(self, width: int, height: int) -> None:
        width = max(VIDEO_MIN_SIZE.width(), int(width or 0))
        height = max(VIDEO_MIN_SIZE.height(), int(height or 0))
        if width > 0 and height > 0:
            ratio = width / height
            if abs(ratio - VIDEO_ASPECT_RATIO) > 0.01:
                height = int(round(width / VIDEO_ASPECT_RATIO))
                if height < VIDEO_MIN_SIZE.height():
                    height = VIDEO_MIN_SIZE.height()
                    width = int(round(height * VIDEO_ASPECT_RATIO))
        self._fixed_size = QSize(width, height)
        if self.mode not in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
            self.apply_mode()
        self.updateGeometry()

    def current_mode(self) -> VideoSizeMode:
        return self.mode

    def target_size(self) -> QSize:
        if self.mode in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
            return QSize(self.size())
        return QSize(self._fixed_size)

    def fit_to(self, available: QSize) -> None:
        if not available.isValid() or available.width() <= 0 or available.height() <= 0:
            return
        self._available = QSize(available)
        width, height = self._fit_size(available)
        if self.mode in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
            if self.size() != QSize(width, height):
                self.resize(width, height)
                self.video_widget.resize(width, height)
                if self.mode == VideoSizeMode.RESIZABLE:
                    self.size_changed.emit(QSize(width, height))
        else:
            if self.size() != QSize(width, height):
                self.setFixedSize(width, height)
                self.video_widget.resize(width, height)

    def _fit_size(self, available: QSize) -> tuple[int, int]:
        avail_w = max(VIDEO_MIN_SIZE.width(), int(available.width()))
        avail_h = max(VIDEO_MIN_SIZE.height(), int(available.height()))
        if self.mode in (VideoSizeMode.STANDARD, VideoSizeMode.CINEMA):
            box = self._fixed_size
        else:
            box = QSize(avail_w, avail_h)
        max_w = min(avail_w, box.width())
        max_h = min(avail_h, box.height())
        width = max_w
        height = int(round(width / VIDEO_ASPECT_RATIO))
        if height > max_h:
            height = max_h
            width = int(round(height * VIDEO_ASPECT_RATIO))
        width = max(VIDEO_MIN_SIZE.width(), width)
        height = max(VIDEO_MIN_SIZE.height(), height)
        return width, height

    def _edge_at(self, pos: QPoint) -> str:
        rect = self.rect()
        x, y = pos.x(), pos.y()
        w, h = rect.width(), rect.height()
        edge = ""
        if x < self._GRAB:
            edge += "l"
        elif x > w - self._GRAB:
            edge += "r"
        if y < self._GRAB:
            edge += "t"
        elif y > h - self._GRAB:
            edge += "b"
        return edge

    @staticmethod
    def _cursor_for_edge(edge: str):
        if edge in ("tl", "br"):
            return QCursor(Qt.CursorShape.SizeFDiagCursor)
        if edge in ("tr", "bl"):
            return QCursor(Qt.CursorShape.SizeBDiagCursor)
        if edge in ("l", "r"):
            return QCursor(Qt.CursorShape.SizeHorCursor)
        if edge in ("t", "b"):
            return QCursor(Qt.CursorShape.SizeVerCursor)
        return QCursor(Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.mode != VideoSizeMode.RESIZABLE:
            super().mouseMoveEvent(event)
            return
        edge = self._edge_at(event.position().toPoint())
        if self._resizing:
            self._resize_to(event.position().toPoint())
        else:
            self.setCursor(self._cursor_for_edge(edge))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        if self.mode == VideoSizeMode.RESIZABLE and event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resizing = True
                self._edge = edge
                self._press_pos = event.globalPosition().toPoint()
                self._press_size = self.size()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._resizing and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            self._edge = ""
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _resize_to(self, pos: QPoint) -> None:
        diff = pos - self._press_pos
        min_w = self.minimumSize().width()
        min_h = self.minimumSize().height()
        new_w, new_h = self._press_size.width(), self._press_size.height()
        if "l" in self._edge:
            new_w = max(min_w, self._press_size.width() - diff.x())
        elif "r" in self._edge:
            new_w = max(min_w, self._press_size.width() + diff.x())
        if "t" in self._edge:
            new_h = max(min_h, self._press_size.height() - diff.y())
        elif "b" in self._edge:
            new_h = max(min_h, self._press_size.height() + diff.y())
        self.setFixedSize(new_w, new_h)
        self.size_changed.emit(self.size())


class VideoStage(QWidget):
    """Área que ocupa el espacio libre y ajusta el vídeo a 16:9."""

    def __init__(self, video_frame: ResizableVideoFrame, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.video_frame = video_frame
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(video_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(VIDEO_MIN_SIZE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event) -> None:  # noqa: N802  # type: ignore[override]
        super().resizeEvent(event)
        self._available = self.size()
        self.video_frame.fit_to(self._available)

    def mousePressEvent(self, event) -> None:  # noqa: N802  # type: ignore[override]
        self.setFocus()
        super().mousePressEvent(event)


class NowPlayingPanel(QWidget):
    """Panel único y unificado: diseño funcional, nada truncado, cada botón
    con propósito claro."""

    video_toggled = pyqtSignal(bool)
    mini_toggled = pyqtSignal(bool)
    open_folder_requested = pyqtSignal()
    favorite_requested = pyqtSignal()
    show_lyrics_requested = pyqtSignal()
    video_size_mode_changed = pyqtSignal(object, QSize)
    video_fullscreen_requested = pyqtSignal(bool)

    # Atajos de teclado del panel (la reproducción real vive en ControlsPanel).
    play_toggle_requested = pyqtSignal()
    seek_relative_requested = pyqtSignal(int)
    volume_relative_requested = pyqtSignal(int)
    mute_requested = pyqtSignal()
    fullscreen_toggle_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._video_available = False
        self._chrome_visible = True

        # ================================================================
        # Layout principal: portada + información, o vídeo a pantalla completa
        # ================================================================
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        self.content_stack = QStackedWidget(self)
        self.content_stack.setObjectName("NowPlayingStack")

        # ------- Página 1: portada a la izquierda, información a la derecha -------
        self.player_page = QWidget(self)
        self.player_page.setObjectName("NowPlayingPlayerPage")
        player_layout = QHBoxLayout(self.player_page)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(28)

        # Portada (responsive: min/max width para adaptarse a la ventana)
        self.left_panel = QWidget(self.player_page)
        self.left_panel.setObjectName("LeftPanel")
        self.left_panel.setMinimumWidth(220)
        self.left_panel.setMaximumWidth(360)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.cover_label = CoverArtLabel(260, self.left_panel)
        self.cover_label.setFixedSize(260, 260)
        left_layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.cover_caption = QLabel("AHORA REPRODUCIENDO", self.left_panel)
        self.cover_caption.setObjectName("EyebrowLabel")
        self.cover_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.cover_caption)
        left_layout.addStretch()
        player_layout.addWidget(self.left_panel, stretch=0)

        # Información de la pista (ocupa todo el ancho restante)
        self.info_panel = QWidget(self.player_page)
        self.info_panel.setObjectName("NowPlayingInfo")
        info_layout = QVBoxLayout(self.info_panel)
        info_layout.setContentsMargins(4, 16, 4, 16)
        info_layout.setSpacing(8)
        info_layout.addStretch(1)

        self.title_label = MarqueeLabel(self.info_panel)
        self.title_label.setObjectName("HeroTitle")
        self.title_label.setText("Bienvenido")
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        info_layout.addWidget(self.title_label)

        self.artist_label = MarqueeLabel(self.info_panel)
        self.artist_label.setObjectName("HeroArtist")
        self.artist_label.setText("Selecciona una pista")
        self.artist_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        info_layout.addWidget(self.artist_label)

        self.album_label = QLabel(" ", self.info_panel)
        self.album_label.setObjectName("MutedLabel")
        self.album_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        info_layout.addWidget(self.album_label)

        self.media_info_label = QLabel(" ", self.info_panel)
        self.media_info_label.setObjectName("StatusLabel")
        self.media_info_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        info_layout.addWidget(self.media_info_label)

        info_layout.addSpacing(12)
        self.shortcuts_hint = QLabel(
            "Espacio: reproducir o pausar · ←/→: ±5 s · ↑/↓: volumen · "
            "M: silenciar · F: pantalla completa",
            self.info_panel,
        )
        self.shortcuts_hint.setObjectName("HintLabel")
        self.shortcuts_hint.setWordWrap(True)
        self.shortcuts_hint.setMaximumWidth(620)
        info_layout.addWidget(self.shortcuts_hint)
        info_layout.addStretch(1)
        player_layout.addWidget(self.info_panel, stretch=1)

        # ------- Página 2: vídeo incrustado (ocupa toda el área) -------
        self.video_widget = VideoWidget(self)
        self.video_widget.hide()
        self.video_frame = ResizableVideoFrame(self.video_widget, self)
        self.video_stage = VideoStage(self.video_frame, self)
        self.video_frame.size_changed.connect(self._on_video_frame_size_changed)
        self.video_frame.mode_changed.connect(self._on_video_mode_changed)
        self.video_frame.double_clicked.connect(self.fullscreen_toggle_requested.emit)
        self.video_widget.double_clicked.connect(self.fullscreen_toggle_requested.emit)

        self.content_stack.addWidget(self.player_page)
        self.content_stack.addWidget(self.video_stage)
        self.content_stack.setCurrentWidget(self.player_page)
        root.addWidget(self.content_stack, stretch=1)

        # ------- Opciones de vídeo compactas (solo con vídeo) -------
        self.video_options_bar = QWidget(self)
        self.video_options_bar.setObjectName("VideoOptionsBar")
        vob = QVBoxLayout(self.video_options_bar)
        vob.setContentsMargins(12, 10, 12, 10)
        vob.setSpacing(8)

        # Fila 1: Toggle vídeo + selector de modo (dropdown)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(8)

        mode_row.addWidget(QLabel("Vídeo"))
        self.video_toggle_btn = QPushButton("Ver video")
        self.video_toggle_btn.setCheckable(True)
        self.video_toggle_btn.setObjectName("VideoToggleBtn")
        self.video_toggle_btn.setAccessibleName("Alternar modo vídeo")
        self.video_toggle_btn.setToolTip("Mostrar u ocultar la vista de vídeo")
        self.video_toggle_btn.clicked.connect(self._on_video_toggled)
        self.video_toggle_btn.setMinimumHeight(44)  # WCAG 2.5.5 target size
        mode_row.addWidget(self.video_toggle_btn)

        mode_row.addSpacing(12)
        mode_row.addWidget(QLabel("Modo:"))
        self.size_mode_combo = QComboBox()
        self.size_mode_combo.setObjectName("VideoSizeCombo")
        self.size_mode_combo.setAccessibleName("Tamaño de vídeo")
        self.size_mode_combo.setToolTip("Seleccionar modo de visualización del vídeo")
        for mode in VideoSizeMode:
            self.size_mode_combo.addItem(mode.label(), mode)
        self.size_mode_combo.setMinimumHeight(44)  # WCAG 2.5.5 target size
        self.size_mode_combo.setMinimumWidth(180)
        self.size_mode_combo.currentIndexChanged.connect(self._on_size_mode_combo_changed)
        mode_row.addWidget(self.size_mode_combo)
        mode_row.addStretch()
        vob.addLayout(mode_row)

        # Fila 2: Controles de tamaño personalizado (solo visible en modo Responsivo)
        self.custom_size_row = QWidget()
        self.custom_size_row.setObjectName("CustomSizeRow")
        size_row = QHBoxLayout(self.custom_size_row)
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(8)
        size_row.addWidget(QLabel("Ancho:"))
        self.video_w_spin = QSpinBox()
        self.video_w_spin.setRange(VIDEO_MIN_SIZE.width(), 3840)
        self.video_w_spin.setValue(VIDEO_SIZE_STANDARD.width())
        self.video_w_spin.setSuffix(" px")
        self.video_w_spin.setFixedWidth(105)
        self.video_w_spin.setMinimumHeight(44)  # WCAG 2.5.5 target size
        self.video_w_spin.setAccessibleName("Ancho del vídeo")
        self.video_w_spin.valueChanged.connect(self._on_video_size_edited)
        size_row.addWidget(self.video_w_spin)

        size_row.addWidget(QLabel("×"))
        self.video_h_spin = QSpinBox()
        self.video_h_spin.setRange(VIDEO_MIN_SIZE.height(), 2160)
        self.video_h_spin.setValue(VIDEO_SIZE_STANDARD.height())
        self.video_h_spin.setSuffix(" px")
        self.video_h_spin.setFixedWidth(105)
        self.video_h_spin.setMinimumHeight(44)  # WCAG 2.5.5 target size
        self.video_h_spin.setAccessibleName("Alto del vídeo")
        self.video_h_spin.valueChanged.connect(self._on_video_size_edited)
        size_row.addWidget(self.video_h_spin)

        self.video_apply_btn = QPushButton("Aplicar")
        self.video_apply_btn.setObjectName("VideoApplyBtn")
        self.video_apply_btn.setAccessibleName("Aplicar tamaño de vídeo")
        self.video_apply_btn.setToolTip("Aplicar el ancho y alto indicados al vídeo")
        self.video_apply_btn.setMinimumSize(44, 44)  # WCAG 2.5.5 target size
        self.video_apply_btn.clicked.connect(self._on_apply_video_size)
        size_row.addWidget(self.video_apply_btn)
        size_row.addStretch()
        vob.addWidget(self.custom_size_row)

        self.video_options_bar.hide()
        root.addWidget(self.video_options_bar)

        self._pre_fullscreen_mode = VideoSizeMode.STANDARD
        self._pre_fullscreen_size = QSize(VIDEO_SIZE_STANDARD)

        # ------- Acciones propias de la pista (sin transporte duplicado) -------
        self.actions_bar = QWidget(self)
        self.actions_bar.setObjectName("NowPlayingActions")
        actions_row = QHBoxLayout(self.actions_bar)
        actions_row.setContentsMargins(16, 10, 16, 10)
        actions_row.setSpacing(12)
        actions_row.addStretch()

        self.favorite_btn = QPushButton("Favorito", self.actions_bar)
        self.favorite_btn.setObjectName("ActionBtn")
        self.favorite_btn.setAccessibleName("Marcar como favorito")
        self.favorite_btn.setToolTip("Añadir o quitar de favoritos")
        self.favorite_btn.clicked.connect(self.favorite_requested.emit)
        actions_row.addWidget(self.favorite_btn)

        self.lyrics_btn = QPushButton("Letras", self.actions_bar)
        self.lyrics_btn.setObjectName("ActionBtn")
        self.lyrics_btn.setAccessibleName("Mostrar letras")
        self.lyrics_btn.setToolTip("Mostrar la letra de la canción")
        self.lyrics_btn.clicked.connect(self.show_lyrics_requested.emit)
        actions_row.addWidget(self.lyrics_btn)

        self.open_folder_btn = QPushButton("Carpeta", self.actions_bar)
        self.open_folder_btn.setObjectName("ActionBtn")
        self.open_folder_btn.setAccessibleName("Abrir carpeta del archivo")
        self.open_folder_btn.setToolTip("Abrir la carpeta del archivo")
        self.open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        actions_row.addWidget(self.open_folder_btn)

        self.mini_player_btn = QPushButton("Mini", self.actions_bar)
        self.mini_player_btn.setCheckable(True)
        self.mini_player_btn.setObjectName("ActionBtn")
        self.mini_player_btn.setAccessibleName("Mini reproductor")
        self.mini_player_btn.setToolTip("Activar el mini reproductor flotante")
        self.mini_player_btn.toggled.connect(self.mini_toggled.emit)
        actions_row.addWidget(self.mini_player_btn)

        actions_row.addStretch()
        root.addWidget(self.actions_bar)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ================================================================
    # Video
    # ================================================================
    def _on_video_toggled(self) -> None:
        enabled = self.video_toggle_btn.isChecked()
        self.video_toggled.emit(enabled)

    def set_video_enabled(self, enabled: bool) -> None:
        """Muestra la página de vídeo o vuelve a la portada sin reemitir señales."""
        enabled = bool(enabled)
        self.video_toggle_btn.blockSignals(True)
        self.video_toggle_btn.setChecked(enabled)
        self.video_toggle_btn.blockSignals(False)
        if enabled:
            self.content_stack.setCurrentWidget(self.video_stage)
            self.video_widget.show()
            self.video_frame.apply_mode()
            self.setFocus()
        else:
            self.content_stack.setCurrentWidget(self.player_page)
            self.video_widget.clear()

    def set_video_available(self, available: bool) -> None:
        """Muestra/oculta los controles de vídeo según haya vídeo disponible."""
        self._video_available = bool(available)
        self.video_toggle_btn.setVisible(self._video_available and self._chrome_visible)
        self.video_options_bar.setVisible(self._video_available and self._chrome_visible)
        if not self._video_available and self.content_stack.currentWidget() is self.video_stage:
            self.set_video_enabled(False)

    def set_fullscreen_chrome(self, visible: bool) -> None:
        """Oculta metadatos/acciones durante la pantalla completa del vídeo."""
        self._chrome_visible = bool(visible)
        for widget in (
            self.title_label,
            self.artist_label,
            self.album_label,
            self.media_info_label,
            self.cover_caption,
            self.shortcuts_hint,
        ):
            widget.setVisible(visible)
        self.cover_label.setVisible(visible)
        self.actions_bar.setVisible(visible)
        self.video_toggle_btn.setVisible(visible and self._video_available)
        self.video_options_bar.setVisible(visible and self._video_available)

    def set_video_size_mode(self, mode: VideoSizeMode) -> None:
        """Fija el modo de visualizacion del video."""
        if mode == VideoSizeMode.FULLSCREEN:
            self._enter_fullscreen()
            return
        self.video_frame.set_mode(mode)
        self._update_size_mode_combo()
        self.video_size_mode_changed.emit(mode, self.video_frame.target_size())

    def set_video_size(self, width: int, height: int) -> None:
        """Fija un tamano personalizado (modo estandar/cine)."""
        self.video_frame.set_size(width, height)
        self._sync_video_size_spins()

    def current_video_size_mode(self) -> VideoSizeMode:
        return self.video_frame.current_mode()

    def _update_size_mode_combo(self) -> None:
        """Actualiza el combo box para reflejar el modo actual."""
        active = self.video_frame.current_mode()
        for i in range(self.size_mode_combo.count()):
            if self.size_mode_combo.itemData(i) == active:
                self.size_mode_combo.blockSignals(True)
                self.size_mode_combo.setCurrentIndex(i)
                self.size_mode_combo.blockSignals(False)
                break
        self._update_custom_size_visibility()

    def _update_custom_size_visibility(self) -> None:
        """Muestra/oculta la fila de tamaño personalizado según el modo."""
        current_mode = self.video_frame.current_mode()
        self.custom_size_row.setVisible(current_mode == VideoSizeMode.RESIZABLE)

    def _enter_fullscreen(self) -> None:
        if self.video_frame.current_mode() == VideoSizeMode.FULLSCREEN:
            return
        self._pre_fullscreen_mode = self.video_frame.current_mode()
        self._pre_fullscreen_size = self.video_frame.size()
        self.video_frame.set_mode(VideoSizeMode.FULLSCREEN)
        self.video_frame.fit_to(self.video_stage.size())
        self.video_fullscreen_requested.emit(True)
        self._update_size_mode_combo()

    def exit_fullscreen(self) -> None:
        """Restaura el modo anterior."""
        if self.video_frame.current_mode() != VideoSizeMode.FULLSCREEN:
            return
        previous = self._pre_fullscreen_mode
        self.video_frame.set_mode(previous)
        self.video_frame.fit_to(self.video_stage.size())
        self._update_size_mode_combo()

    def _on_size_mode_combo_changed(self, index: int) -> None:
        """Maneja el cambio de modo desde el combo box."""
        if index < 0:
            return
        mode = self.size_mode_combo.itemData(index)
        if mode == VideoSizeMode.FULLSCREEN:
            if self.video_frame.current_mode() == VideoSizeMode.FULLSCREEN:
                self.video_fullscreen_requested.emit(False)
                self.exit_fullscreen()
            else:
                self._enter_fullscreen()
            return
        if self.video_frame.current_mode() == VideoSizeMode.FULLSCREEN:
            self.video_fullscreen_requested.emit(False)
        self.video_frame.set_mode(mode)
        self._update_custom_size_visibility()

    def _on_video_frame_size_changed(self, size: QSize) -> None:
        if self.video_frame.current_mode() == VideoSizeMode.RESIZABLE:
            self.video_size_mode_changed.emit(VideoSizeMode.RESIZABLE, size)
        self._sync_video_size_spins()

    def _on_video_mode_changed(self, mode: VideoSizeMode) -> None:
        self._update_size_mode_combo()
        self._sync_video_size_spins()
        if mode != VideoSizeMode.FULLSCREEN:
            self.video_size_mode_changed.emit(mode, self.video_frame.target_size())

    def _sync_video_size_spins(self) -> None:
        """Sincroniza los spin boxes de ancho/alto con el tamaño actual del frame."""
        size = self.video_frame.target_size()
        self.video_w_spin.blockSignals(True)
        self.video_h_spin.blockSignals(True)
        self.video_w_spin.setValue(size.width())
        self.video_h_spin.setValue(size.height())
        self.video_w_spin.blockSignals(False)
        self.video_h_spin.blockSignals(False)

    def _on_video_size_edited(self) -> None:
        """El usuario edito ancho o alto: aplica el tamaño al frame inmediatamente."""
        self._apply_spin_size_to_frame()

    def _on_apply_video_size(self) -> None:
        """Confirma el tamaño editado y lo persiste como tamaño objetivo."""
        self._apply_spin_size_to_frame()
        self.video_size_mode_changed.emit(
            self.video_frame.current_mode(), self.video_frame.target_size()
        )

    def _apply_spin_size_to_frame(self) -> None:
        w = self.video_w_spin.value()
        h = self.video_h_spin.value()
        self.video_frame.set_size(w, h)
        self._sync_video_size_spins()

    # ================================================================
    # Atajos y estado de la interfaz
    # ================================================================
    def keyPressEvent(self, event) -> None:  # noqa: N802  # type: ignore[override]
        """Atajos de reproductor cuando el panel tiene el foco."""
        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Space:
            self.play_toggle_requested.emit()
        elif key == Qt.Key.Key_Left:
            self.seek_relative_requested.emit(-5)
        elif key == Qt.Key.Key_Right:
            self.seek_relative_requested.emit(5)
        elif key == Qt.Key.Key_Up:
            self.volume_relative_requested.emit(5)
        elif key == Qt.Key.Key_Down:
            self.volume_relative_requested.emit(-5)
        elif key == Qt.Key.Key_M:
            self.mute_requested.emit()
        elif key == Qt.Key.Key_F:
            self.fullscreen_toggle_requested.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def set_mini_enabled(self, enabled: bool) -> None:
        """Sincroniza el boton sin reemitir mini_toggled (evita bucles)."""
        self.mini_player_btn.blockSignals(True)
        self.mini_player_btn.setChecked(enabled)
        self.mini_player_btn.blockSignals(False)
        self.mini_player_btn.setText("Mini (activado)" if enabled else "Mini")

    def set_favorite_state(self, is_favorite: bool) -> None:
        """Actualiza el botón de favorito con texto claro (sin glifos frágiles)."""
        self.favorite_btn.setText("Quitar favorito" if is_favorite else "Favorito")
        self.favorite_btn.setAccessibleName(
            "Quitar de favoritos" if is_favorite else "Añadir a favoritos"
        )
        self.favorite_btn.setToolTip(
            "Quitar de favoritos" if is_favorite else "Añadir a favoritos"
        )

    def set_track_info(self, title: str, artist: str, album: str = "") -> None:
        self.title_label.setText(title or "Bienvenido")
        self.artist_label.setText(artist or "Selecciona una pista")
        self.album_label.setText(album or "")

    def set_media_info(self, info: dict) -> None:
        """Muestra formato/bitrate/muestra leídos de VLC."""
        if not info:
            self.media_info_label.setText("")
            return
        parts = []
        if info.get("codec"):
            parts.append(str(info["codec"]).upper())
        if info.get("sample_rate"):
            parts.append(f"{int(info['sample_rate']) // 1000} kHz")
        if info.get("channels"):
            channels = int(info["channels"])
            parts.append({1: "mono", 2: "estereo"}.get(channels, f"{channels} canales"))
        if info.get("bitrate"):
            parts.append(f"{int(info['bitrate']) // 1000} kbps")
        self.media_info_label.setText("  •  ".join(parts))

    def reset(self) -> None:
        self.set_track_info("Bienvenido", "Selecciona una pista", "")
        self.set_media_info({})
        self.cover_label.set_placeholder()
