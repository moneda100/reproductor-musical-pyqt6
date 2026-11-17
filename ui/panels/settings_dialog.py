"""Diálogo de ajustes (Phase 1.21)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig
from ui.panels.now_playing import VideoSizeMode
from ui.themes import ThemeManager


class SettingsDialog(QDialog):
    """Ajustes de la aplicación: tema, carpetas, caché, sincronización, Last.fm."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(520)
        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # -- apariencia --
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(ThemeManager.theme_names())
        self.theme_combo.setCurrentText(config.theme)
        form.addRow("Tema", self.theme_combo)

        # -- tamaño de vídeo ------------------------------------------------
        self.video_mode_combo = QComboBox()
        for mode in VideoSizeMode:
            self.video_mode_combo.addItem(mode.label(), mode.value)
        index = self.video_mode_combo.findData(config.video_size_mode)
        self.video_mode_combo.setCurrentIndex(max(0, index))
        form.addRow("Tamaño de vídeo", self.video_mode_combo)

        size_row = QHBoxLayout()
        self.video_width_spin = QSpinBox()
        self.video_width_spin.setRange(160, 7680)
        self.video_width_spin.setValue(int(config.video_width))
        self.video_width_spin.setSuffix(" px")
        self.video_height_spin = QSpinBox()
        self.video_height_spin.setRange(90, 4320)
        self.video_height_spin.setValue(int(config.video_height))
        self.video_height_spin.setSuffix(" px")
        size_row.addWidget(QLabel("Ancho:"))
        size_row.addWidget(self.video_width_spin)
        size_row.addWidget(QLabel("Alto:"))
        size_row.addWidget(self.video_height_spin)
        form.addRow("Tamaño personalizado", size_row)

        # -- carpetas --
        self.download_dir_input = QLineEdit(config.download_dir)
        download_row = QHBoxLayout()
        download_row.addWidget(self.download_dir_input)
        browse_download = QPushButton("…")
        browse_download.setFixedWidth(32)
        browse_download.clicked.connect(self._browse_download_dir)
        download_row.addWidget(browse_download)
        form.addRow("Carpeta de descargas", download_row)

        self.download_format_combo = QComboBox()
        self.download_format_combo.addItem("MP3", "mp3")
        self.download_format_combo.addItem("FLAC", "flac")
        format_index = self.download_format_combo.findData(
            (config.download_format or "mp3").lower()
        )
        self.download_format_combo.setCurrentIndex(max(0, format_index))
        form.addRow("Formato de descarga", self.download_format_combo)

        self.library_dirs_input = QLineEdit("; ".join(config.library_dirs))
        library_row = QHBoxLayout()
        library_row.addWidget(self.library_dirs_input)
        browse_library = QPushButton("…")
        browse_library.setFixedWidth(32)
        browse_library.clicked.connect(self._browse_library_dirs)
        library_row.addWidget(browse_library)
        form.addRow("Carpetas de la biblioteca", library_row)

        # -- caché --
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(64, 16384)
        self.cache_spin.setSingleStep(64)
        self.cache_spin.setSuffix(" MB")
        self.cache_spin.setValue(int(config.max_cache_mb))
        form.addRow("Tamaño máximo de caché", self.cache_spin)

        # -- integraciones --
        self.lastfm_key_input = QLineEdit(config.lastfm_api_key)
        self.lastfm_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Clave API de Last.fm", self.lastfm_key_input)

        self.lastfm_user_input = QLineEdit(config.lastfm_username)
        form.addRow("Usuario de Last.fm", self.lastfm_user_input)

        self.lyrics_cb = QCheckBox("Mostrar letras")
        self.lyrics_cb.setChecked(config.features_lyrics)
        form.addRow("", self.lyrics_cb)

        self.lastfm_cb = QCheckBox("Enviar scrobbles a Last.fm")
        self.lastfm_cb.setChecked(config.features_lastfm)
        form.addRow("", self.lastfm_cb)

        self.tray_cb = QCheckBox("Minimizar a la bandeja del sistema")
        self.tray_cb.setChecked(config.features_tray)
        form.addRow("", self.tray_cb)

        self.smtc_cb = QCheckBox("Detectar medios de otras apps en la barra de notificaciones")
        self.smtc_cb.setChecked(config.features_smtc)
        form.addRow("", self.smtc_cb)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_download_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de descargas")
        if folder:
            self.download_dir_input.setText(folder)

    def _browse_library_dirs(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de la biblioteca")
        if folder:
            current = [p for p in self.library_dirs_input.text().split(";") if p.strip()]
            current.append(folder)
            self.library_dirs_input.setText("; ".join(current))

    def result_config(self) -> AppConfig:
        """Devuelve la configuración modificada por el usuario."""
        config = self._config
        config.theme = self.theme_combo.currentText()
        config.video_size_mode = str(self.video_mode_combo.currentData() or "standard")
        config.video_width = int(self.video_width_spin.value())
        config.video_height = int(self.video_height_spin.value())
        config.download_dir = self.download_dir_input.text().strip()
        config.download_format = str(self.download_format_combo.currentData() or "mp3")
        config.library_dirs = [
            path.strip() for path in self.library_dirs_input.text().split(";") if path.strip()
        ]
        config.max_cache_mb = int(self.cache_spin.value())
        config.lastfm_api_key = self.lastfm_key_input.text().strip()
        config.lastfm_username = self.lastfm_user_input.text().strip()
        config.features_lyrics = self.lyrics_cb.isChecked()
        config.features_lastfm = self.lastfm_cb.isChecked()
        config.features_tray = self.tray_cb.isChecked()
        config.features_smtc = self.smtc_cb.isChecked()
        return config
