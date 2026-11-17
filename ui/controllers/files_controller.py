"""Controlador de ficheros: apertura, edición de tags, duplicados.

Extrae del ``MainWindow`` las acciones que tocan el disco para que la
ventana quede como orquestador.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.playlist import Track
from core.playlist_manager import PlaylistManager
from services.metadata_service import MetadataService

logger = logging.getLogger(__name__)

AUDIO_FILTER = "Audio (*.mp3 *.flac *.wav *.webm *.m4a *.ogg *.mp4 *.aac *.opus);;Todos (*)"


class FilesController(QObject):
    """Abre ficheros, edita etiquetas y detecta duplicados."""

    track_added = pyqtSignal(object)  # Track
    tracks_added = pyqtSignal(list)  # list[Track]
    duplicates_found = pyqtSignal(list)  # list[DuplicateGroup]
    message = pyqtSignal(str, str)  # texto, tipo de toast

    def __init__(
        self,
        metadata_service: MetadataService,
        parent: Optional[QObject] = None,
        pool: Optional[QThreadPool] = None,
    ) -> None:
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.pool = pool

    # -- apertura ---------------------------------------------------------
    def choose_files(self, parent_widget) -> list[str]:
        files, _ = QFileDialog.getOpenFileNames(parent_widget, "Música", "", AUDIO_FILTER)
        return list(files)

    def build_track(self, path: str) -> Optional[Track]:
        """Construye un ``Track`` a partir de un fichero local."""
        if not path or not os.path.exists(path):
            return None
        meta = self.metadata_service.get_metadata(path)
        cover = (
            self.metadata_service.save_cover(meta["cover_data"]) if meta.get("cover_data") else None
        )
        return Track(
            id=Path(path).name,
            title=meta.get("title") or Path(path).name,
            artist=meta.get("artist", "Desconocido"),
            album=meta.get("album", "Desconocido"),
            file_path=path,
            duration=meta.get("duration", 0) or 0,
            cover_url=cover,
            source="local",
        )

    def add_files(self, paths: list[str]) -> list[Track]:
        tracks = []
        for path in paths:
            track = self.build_track(path)
            if track is not None:
                tracks.append(track)
        if tracks:
            self.tracks_added.emit(tracks)
        return tracks

    # -- etiquetas ---------------------------------------------------------
    def edit_tags(self, path: str, parent_widget) -> bool:
        """Abre el editor de etiquetas de un fichero. Devuelve si se guardó."""
        from ui.tag_editor import TagEditorDialog

        if not path or not os.path.exists(path):
            QMessageBox.warning(
                parent_widget, "Error", "No se puede editar: archivo no encontrado."
            )
            return False
        meta = self.metadata_service.get_metadata(path)
        dialog = TagEditorDialog(path, meta, self.metadata_service, parent_widget, pool=self.pool)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.message.emit("Metadatos actualizados", "success")
            return True
        return False

    def edit_tags_batch(self, paths: list[str], parent_widget) -> Optional[dict]:
        """Abre el editor de etiquetas en lote. Devuelve el resumen."""
        from ui.panels.batch_tag_dialog import BatchTagDialog

        if not paths:
            return None
        dialog = BatchTagDialog(paths, self.metadata_service, parent_widget, pool=self.pool)
        summary: dict = {}
        dialog.finished.connect(lambda result: summary.update(result))
        dialog.exec()
        return summary or None

    # -- duplicados ---------------------------------------------------------
    def find_duplicates(self, tracks: list[Track]) -> list:
        manager = PlaylistManager()
        return manager.find_duplicates(tracks)

    def purge_duplicates(self, paths: list[str], parent_widget) -> int:
        """Elimina los ficheros duplicados indicados. Devuelve cuántos se borraron."""
        if not paths:
            return 0
        reply = QMessageBox.question(
            parent_widget,
            "Confirmar",
            f"¿Eliminar {len(paths)} ficheros duplicados?\n"
            "Se conservará la primera copia de cada grupo.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return 0
        removed = 0
        for path in paths:
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                logger.warning("No se pudo eliminar %s: %s", path, exc)
        self.message.emit(f"{removed} duplicados eliminados", "success")
        return removed
