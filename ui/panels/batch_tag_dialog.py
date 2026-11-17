"""Edición de etiquetas en lote con vista previa, agrupada por álbum.

Permite editar metadatos de varios ficheros a la vez, agrupándolos por álbum
para aplicar cambios masivos (mismo artista, álbum, género, año a todo el
álbum) o editar cada fichero de forma individual.

La escritura se hace en un worker (no bloquea la UI) y devuelve un resumen
por archivo: «12 escritos, 2 fallaron».
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.tasks.library_tasks import BatchTagWriteTask
from core.tasks.worker import Worker

logger = logging.getLogger(__name__)

# Campos que se pueden editar en lote por álbum.
_ALBUM_FIELDS = ("artist", "album", "genre", "year")
_TRACK_FIELDS = ("title",)


class BatchTagDialog(QDialog):
    """Aplica cambios de metadatos a varios ficheros con vista previa.

    Los ficheros se agrupan por álbum para aplicar cambios masivos al álbum
    entero, o individualmente por pista.
    """

    finished = pyqtSignal(dict)

    def __init__(self, file_paths: list[str], metadata_service, parent=None, pool=None):
        super().__init__(parent)
        self.file_paths = list(file_paths)
        self.ms = metadata_service
        self._pool = pool
        self._worker: Worker | None = None

        # Agrupar por álbum para el modo por álbum.
        self._by_album: dict[str, list[str]] = defaultdict(list)
        for path in self.file_paths:
            meta = self.ms.get_metadata(path, with_cover=False)
            album = meta.get("album") or "Sin álbum"
            self._by_album[album].append(path)

        self.setWindowTitle("Edición de etiquetas en lote")
        self.resize(720, 560)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Ficheros seleccionados: {len(self.file_paths)}"))

        # -- modo de edición --
        mode_box = QHBoxLayout()
        self.mode_album_btn = QPushButton("Por álbum (cambios masivos)")
        self.mode_album_btn.setCheckable(True)
        self.mode_album_btn.setChecked(True)
        self.mode_album_btn.setObjectName("SecondaryBtn")
        self.mode_album_btn.clicked.connect(self._switch_mode)

        self.mode_track_btn = QPushButton("Por pista (individual)")
        self.mode_track_btn.setCheckable(True)
        self.mode_track_btn.clicked.connect(self._switch_mode)
        mode_box.addWidget(self.mode_album_btn)
        mode_box.addWidget(self.mode_track_btn)
        mode_box.addStretch()
        layout.addLayout(mode_box)

        # -- formulario por álbum --
        self.album_form = QWidget()
        form = QHBoxLayout(self.album_form)
        form.setContentsMargins(0, 0, 0, 0)
        self.album_artist_input = QLineEdit()
        self.album_artist_input.setPlaceholderText("Artista (vacío = no cambiar)")
        self.album_album_input = QLineEdit()
        self.album_album_input.setPlaceholderText("Álbum (vacío = no cambiar)")
        self.album_genre_input = QLineEdit()
        self.album_genre_input.setPlaceholderText("Género (vacío = no cambiar)")
        self.album_year_input = QSpinBox()
        self.album_year_input.setRange(0, 2100)
        self.album_year_input.setValue(0)
        self.album_year_input.setSpecialValueText("Sin cambiar")
        form.addWidget(QLabel("Artista:"))
        form.addWidget(self.album_artist_input)
        form.addWidget(QLabel("Álbum:"))
        form.addWidget(self.album_album_input)
        form.addWidget(QLabel("Género:"))
        form.addWidget(self.album_genre_input)
        form.addWidget(QLabel("Año:"))
        form.addWidget(self.album_year_input)
        form.addStretch()
        layout.addWidget(self.album_form)

        # -- formulario por pista --
        self.track_form = QWidget()
        track_form = QHBoxLayout(self.track_form)
        track_form.setContentsMargins(0, 0, 0, 0)
        self.track_title_input = QLineEdit()
        self.track_title_input.setPlaceholderText("Título (vacío = no cambiar)")
        self.track_artist_input = QLineEdit()
        self.track_artist_input.setPlaceholderText("Artista (vacío = no cambiar)")
        self.track_album_input = QLineEdit()
        self.track_album_input.setPlaceholderText("Álbum (vacío = no cambiar)")
        track_form.addWidget(QLabel("Título:"))
        track_form.addWidget(self.track_title_input)
        track_form.addWidget(QLabel("Artista:"))
        track_form.addWidget(self.track_artist_input)
        track_form.addWidget(QLabel("Álbum:"))
        track_form.addWidget(self.track_album_input)
        track_form.addStretch()
        layout.addWidget(self.track_form)

        layout.addWidget(QLabel("Vista previa:"))
        self.preview = QListWidget()
        layout.addWidget(self.preview, stretch=1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("💾 Aplicar a todos")
        apply_btn.setObjectName("DangerBtn")
        apply_btn.clicked.connect(self.apply_changes)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(apply_btn)
        layout.addLayout(buttons)

        self._switch_mode()

    # -- modos -----------------------------------------------------------
    def _switch_mode(self) -> None:
        album_mode = self.mode_album_btn.isChecked()
        self.mode_album_btn.setChecked(album_mode)
        self.mode_track_btn.setChecked(not album_mode)
        self.album_form.setVisible(album_mode)
        self.track_form.setVisible(not album_mode)
        self._build_preview()

    # -- vista previa ----------------------------------------------------
    def _build_preview(self) -> None:
        self.preview.clear()
        if self.mode_album_btn.isChecked():
            for album, paths in self._by_album.items():
                item = QListWidgetItem(f"📀 Álbum: {album}  ({len(paths)} pista(s))")
                item.setData(Qt.ItemDataRole.UserRole, ("album", album, paths))
                self.preview.addItem(item)
        else:
            for path in self.file_paths:
                meta = self.ms.get_metadata(path, with_cover=False)
                item = QListWidgetItem(
                    f"🎵 {meta.get('artist', '?')} — {meta.get('title', Path(path).name)}"
                )
                item.setData(Qt.ItemDataRole.UserRole, ("track", path, [path]))
                self.preview.addItem(item)

    # -- aplicación ------------------------------------------------------
    def apply_changes(self) -> None:
        updates: list[tuple[str, dict, bytes | None]] = []

        if self.mode_album_btn.isChecked():
            # Cambios masivos por álbum: aplicar a todas las pistas del álbum.
            for album, paths in self._by_album.items():
                new_meta: dict[str, str] = {}
                if self.album_artist_input.text().strip():
                    new_meta["artist"] = self.album_artist_input.text().strip()
                if self.album_album_input.text().strip():
                    new_meta["album"] = self.album_album_input.text().strip()
                if self.album_genre_input.text().strip():
                    new_meta["genre"] = self.album_genre_input.text().strip()
                if self.album_year_input.value() > 0:
                    new_meta["year"] = str(self.album_year_input.value())
                for path in paths:
                    updates.append((path, new_meta, None))
        else:
            # Cambios individuales por pista.
            new_meta: dict[str, str] = {}
            if self.track_title_input.text().strip():
                new_meta["title"] = self.track_title_input.text().strip()
            if self.track_artist_input.text().strip():
                new_meta["artist"] = self.track_artist_input.text().strip()
            if self.track_album_input.text().strip():
                new_meta["album"] = self.track_album_input.text().strip()
            for path in self.file_paths:
                updates.append((path, new_meta, None))

        if not updates:
            QMessageBox.information(self, "Info", "Indica al menos un campo a cambiar.")
            return

        task = BatchTagWriteTask(self.ms, updates)
        worker = Worker(task)
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        self._worker = worker
        if self._pool is not None:
            self._pool.start(worker)
        else:
            worker.run()

    def _on_result(self, summary: dict) -> None:
        written = summary.get("written", 0)
        failed = summary.get("failed", [])
        self.finished.emit(summary)
        QMessageBox.information(
            self,
            "Resultado",
            f"{written} escritos, {len(failed)} fallaron."
            + ("\n\n" + "\n".join(failed) if failed else ""),
        )
        self.accept()

    def _on_error(self, error: str) -> None:
        QMessageBox.critical(self, "Error", f"No se pudieron escribir las etiquetas: {error}")
