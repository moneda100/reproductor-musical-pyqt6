"""Barra de controles de reproducción."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ui.widgets import ClickableSlider, IconButton


class ControlsPanel(QWidget):
    """Progreso, botones de transporte y volumen.

    Panel "tonto": solo renderiza los valores que recibe y emite las
    intenciones del usuario. La lógica de seeking (ignorar actualizaciones
    de VLC mientras se busca manualmente) vive en ``PlaybackController``.
    """

    play_toggled = pyqtSignal()
    next_requested = pyqtSignal()
    previous_requested = pyqtSignal()
    shuffle_toggled = pyqtSignal(bool)
    repeat_toggled = pyqtSignal()
    seek_requested = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    mute_toggled = pyqtSignal(bool)
    queue_toggled = pyqtSignal()
    lyrics_toggled = pyqtSignal()

    REPEAT_LABELS = {
        "none": ("➡️", "Repetición: desactivada"),
        "all": ("🔁", "Repetición: toda la lista"),
        "one": ("🔂", "Repetición: una pista"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ControlPanel")
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 10, 30, 20)
        layout.setSpacing(10)

        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)
        self.time_label = QLabel("0:00")
        self.time_label.setObjectName("MutedLabel")
        self.time_label.setMinimumWidth(45)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setAccessibleName("Progreso de reproducción")
        self.slider.setAccessibleDescription("Muestra y ajusta la posición de reproducción de la canción actual")
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)

        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("MutedLabel")
        self.duration_label.setMinimumWidth(45)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.slider, stretch=1)
        progress_layout.addWidget(self.duration_label)
        layout.addLayout(progress_layout)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch()

        self.shuffle_btn = IconButton(
            "shuffle", "Aleatorio", "Mezclar el orden de reproducción", 50
        )
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setObjectName("ToggleBtn")
        self.shuffle_btn.toggled.connect(self.shuffle_toggled.emit)

        self.prev_btn = IconButton("prev", "Pista anterior", "Pista anterior", 50)
        self.prev_btn.setObjectName("ControlBtn")
        self.prev_btn.clicked.connect(self.previous_requested.emit)

        self.play_btn = IconButton("play", "Reproducir o pausar", "Reproducir o pausar", 64)
        self.play_btn.setObjectName("PlayBtn")
        self.play_btn.clicked.connect(self.play_toggled.emit)

        self.next_btn = IconButton("next", "Pista siguiente", "Pista siguiente", 50)
        self.next_btn.setObjectName("ControlBtn")
        self.next_btn.clicked.connect(self.next_requested.emit)

        self.repeat_btn = IconButton("repeat", "Repetición", self.REPEAT_LABELS["none"][1], 50)
        self.repeat_btn.setObjectName("ControlBtn")
        self.repeat_btn.clicked.connect(self.repeat_toggled.emit)

        buttons_layout.addWidget(self.shuffle_btn)
        buttons_layout.addWidget(self.prev_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.next_btn)
        buttons_layout.addWidget(self.repeat_btn)
        buttons_layout.addStretch()

        volume_layout = QHBoxLayout()
        self.mute_btn = IconButton("volume_up", "Silenciar", "Silenciar / activar sonido", 44)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setObjectName("ControlBtn")
        self.mute_btn.toggled.connect(self.mute_toggled.emit)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setAccessibleName("Volumen")
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        volume_layout.addWidget(self.mute_btn)
        volume_layout.addWidget(self.volume_slider)

        self.lyrics_btn = IconButton("lyrics", "Letras", "Mostrar u ocultar la letra", 44)
        self.lyrics_btn.setObjectName("ControlBtn")
        self.lyrics_btn.clicked.connect(self.lyrics_toggled.emit)

        self.queue_btn = IconButton(
            "menu", "Cola de reproducción", "Ver la cola de reproducción", 44
        )
        self.queue_btn.setObjectName("ControlBtn")
        self.queue_btn.clicked.connect(self.queue_toggled.emit)

        volume_layout.addWidget(self.lyrics_btn)
        volume_layout.addWidget(self.queue_btn)
        buttons_layout.addLayout(volume_layout)
        layout.addLayout(buttons_layout)

    # -- estado -------------------------------------------------------
    def set_playing(self, playing: bool) -> None:
        self.play_btn.set_icon("pause" if playing else "play")
        self.play_btn.setAccessibleName("Pausar" if playing else "Reproducir")

    def set_repeat_mode(self, mode: str) -> None:
        icon_map = {
            "none": "repeat",
            "all": "repeat",
            "one": "repeat_one",
        }
        icon = icon_map.get(mode, "repeat")
        self.repeat_btn.set_icon(icon)
        _, tooltip = self.REPEAT_LABELS.get(mode, self.REPEAT_LABELS["none"])
        self.repeat_btn.setToolTip(tooltip)
        self.repeat_btn.setAccessibleName(tooltip)

    def set_position(self, seconds: float, duration: float) -> None:
        if self._dragging:
            return
        seconds_value = max(0.0, float(seconds or 0.0))
        duration_value = max(0.0, float(duration or 0.0))
        self.time_label.setText(format_time(seconds_value))
        if duration_value > 0:
            max_value = max(0, int(duration_value))
            if self.slider.maximum() != max_value:
                self.slider.setRange(0, max_value)
                self.duration_label.setText(format_time(duration_value))
                min_w = 60 if duration_value >= 3600 else 45
                if self.time_label.minimumWidth() != min_w:
                    self.time_label.setMinimumWidth(min_w)
                    self.duration_label.setMinimumWidth(min_w)
        if self.slider.maximum() > 0:
            self.slider.setValue(min(self.slider.maximum(), max(0, int(seconds_value))))

    def set_volume(self, value: int) -> None:
        self.volume_slider.setValue(int(value))

    def set_muted(self, muted: bool) -> None:
        """Sincroniza el icono del botón sin reemitir la señal."""
        self.mute_btn.blockSignals(True)
        self.mute_btn.setChecked(bool(muted))
        self.mute_btn.blockSignals(False)
        self.mute_btn.set_icon("volume_off" if muted else "volume_up")
        self.mute_btn.setAccessibleName("Activar sonido" if muted else "Silenciar")
        self.mute_btn.setToolTip("Activar sonido" if muted else "Silenciar / activar sonido")

    def _on_slider_pressed(self) -> None:
        self._dragging = True

    def _on_slider_moved(self, value: int) -> None:
        """Actualiza la etiqueta de tiempo en directo mientras se arrastra el slider."""
        self.time_label.setText(format_time(value))

    def _on_slider_released(self) -> None:
        self._dragging = False
        self.seek_requested.emit(int(self.slider.value()))


def format_time(seconds: float) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "0:00"
    if total < 0:
        return "0:00"
    if total >= 3600:
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{total // 60}:{total % 60:02d}"
