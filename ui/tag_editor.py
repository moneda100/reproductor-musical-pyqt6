"""Diálogo de edición de etiquetas.

La búsqueda de sugerencias online se hace en un worker del ``QThreadPool``
(antes se hacía en el hilo de la GUI → congelaba la ventana).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.tasks.library_tasks import MetadataSuggestionsTask
from core.tasks.worker import Worker

logger = logging.getLogger(__name__)


class TagEditorDialog(QDialog):
    """Editor de metadatos de un fichero de audio."""

    def __init__(self, file_path, metadata, metadata_service, parent=None, pool=None):
        super().__init__(parent)
        self.file_path = file_path
        self.metadata = metadata
        self.ms = metadata_service
        self.temp_cover_data = None
        self._pool = pool
        self._worker: Worker | None = None

        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.setWindowTitle("Editor de Metadatos")
        self.resize(520, 620)
        self.setObjectName("TagEditorDialog")

        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.cover_prev = QLabel()
        self.cover_prev.setFixedSize(120, 120)
        self.cover_prev.setObjectName("CoverPreview")
        self.cover_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_prev.setText("Sin portada")
        top_layout.addWidget(self.cover_prev)

        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("Archivo:"))
        self.path_label = QLabel(self._file_name())
        self.path_label.setWordWrap(True)
        self.path_label.setObjectName("MutedLabel")
        info_layout.addWidget(self.path_label)
        top_layout.addLayout(info_layout, stretch=1)
        layout.addLayout(top_layout)

        self.title_input = QLineEdit()
        self.artist_input = QLineEdit()
        self.album_input = QLineEdit()
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("Género (opcional)")
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("Año (opcional)")
        self._is_video = bool(self.file_path) and Path(self.file_path).suffix.lower() in {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
        }

        layout.addWidget(QLabel("Título"))
        layout.addWidget(self.title_input)
        layout.addWidget(QLabel("Artista"))
        layout.addWidget(self.artist_input)
        layout.addWidget(QLabel("Álbum"))
        layout.addWidget(self.album_input)
        layout.addWidget(QLabel("Género"))
        layout.addWidget(self.genre_input)
        layout.addWidget(QLabel("Año"))
        layout.addWidget(self.year_input)

        if self._is_video:
            video_hint = QLabel("⚠️ Archivo de vídeo: se escribirán los metadatos del contenedor.")
            video_hint.setObjectName("MutedLabel")
            layout.addWidget(video_hint)

        self.search_btn = QPushButton("🔍 Buscar sugerencias online")
        self.search_btn.setObjectName("SecondaryBtn")
        self.search_btn.setAccessibleName("Buscar sugerencias de metadatos online")
        self.search_btn.clicked.connect(self.search_suggestions)
        layout.addWidget(self.search_btn)

        layout.addWidget(QLabel("Sugerencias similares:"))
        self.suggest_list = QListWidget()
        self.suggest_list.itemClicked.connect(self.apply_suggestion)
        layout.addWidget(self.suggest_list, stretch=1)

        btns = QHBoxLayout()
        btns.addStretch()
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton("💾 Guardar en el archivo")
        self.save_btn.setObjectName("DangerBtn")
        self.save_btn.clicked.connect(self.save_tags)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        layout.addLayout(btns)

    def _file_name(self) -> str:
        import os

        return os.path.basename(self.file_path or "")

    def load_data(self):
        self.title_input.setText(self.metadata.get("title", ""))
        self.artist_input.setText(self.metadata.get("artist", ""))
        self.album_input.setText(self.metadata.get("album", ""))
        self.genre_input.setText(self.metadata.get("genre", ""))
        self.year_input.setText(self.metadata.get("year", ""))

        if self.metadata.get("cover_data"):
            pixmap = QPixmap()
            pixmap.loadFromData(self.metadata["cover_data"])
            self.update_cover_preview(pixmap)
        else:
            self.cover_prev.setText("Sin portada")

    def update_cover_preview(self, pixmap):
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                120,
                120,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover_prev.setPixmap(scaled)
        else:
            self.cover_prev.setText("Error")

    # -- búsqueda de sugerencias ---------------------------------------
    def search_suggestions(self):
        query = f"{self.title_input.text()} {self.artist_input.text()}".strip()
        if not query:
            return
        self.search_btn.setEnabled(False)
        self.search_btn.setText("⏳ Buscando…")

        task = MetadataSuggestionsTask(self.ms, query)
        worker = Worker(task)
        worker.signals.result.connect(self._on_suggestions)
        worker.signals.error.connect(self._on_search_error)
        self._worker = worker
        if self._pool is not None:
            self._pool.start(worker)
        else:
            worker.run()

    def _on_suggestions(self, suggestions):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 Buscar sugerencias online")
        self.suggest_list.clear()
        for suggestion in suggestions:
            detail = f"{suggestion['title']}\n{suggestion['artist']} — {suggestion['album']}"
            if suggestion.get("year") or suggestion.get("genre"):
                detail += f"\n{suggestion.get('year', '')}  •  {suggestion.get('genre', '')}"
            item = QListWidgetItem(detail)
            item.setData(Qt.ItemDataRole.UserRole, suggestion)
            self.suggest_list.addItem(item)
        if not suggestions:
            QMessageBox.information(self, "Info", "No se encontraron sugerencias.")

    def _on_search_error(self, error):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 Buscar sugerencias online")
        QMessageBox.warning(self, "Error", f"No se pudo buscar sugerencias: {error}")

    def apply_suggestion(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.title_input.setText(data.get("title", ""))
        self.artist_input.setText(data.get("artist", ""))
        self.album_input.setText(data.get("album", ""))

        cover_url = data.get("cover_url")
        if cover_url:
            self._download_cover(cover_url)

    def _download_cover(self, url: str) -> None:
        """Descarga la portada de la sugerencia en un worker."""

        def fetch():
            import requests

            response = requests.get(url, timeout=8)
            response.raise_for_status()
            return response.content

        worker = Worker(fetch)
        worker.signals.result.connect(self._on_cover_data)
        worker.signals.error.connect(
            lambda err: logger.debug("No se pudo descargar la portada: %s", err)
        )
        if self._pool is not None:
            self._pool.start(worker)
        else:
            worker.run()

    def _on_cover_data(self, data: bytes) -> None:
        self.temp_cover_data = data
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.update_cover_preview(pixmap)

    # -- guardado --------------------------------------------------------
    def save_tags(self):
        new_meta = {
            "title": self.title_input.text(),
            "artist": self.artist_input.text(),
            "album": self.album_input.text(),
            "genre": self.genre_input.text(),
            "year": self.year_input.text(),
        }
        if self.ms.update_metadata(self.file_path, new_meta, self.temp_cover_data):
            QMessageBox.information(self, "Éxito", "Metadatos actualizados correctamente.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "No se pudieron guardar los cambios en el archivo.")
