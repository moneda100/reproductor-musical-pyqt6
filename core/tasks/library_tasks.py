"""Tareas de biblioteca y de metadatos (I/O de disco y de red)."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Iterator

AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aiff", ".aac", ".opus")

# Lotes de señal: evita una señal Qt por archivo (10 000 pistas = 10 000 eventos)
SCAN_BATCH_SIZE = 25
SCAN_BATCH_INTERVAL = 0.1


def iter_audio_files(folder_path: str) -> Iterator[str]:
    """Recorre recursivamente los archivos de audio de una carpeta."""
    for root, _dirs, files in os.walk(folder_path):
        for name in files:
            if name.lower().endswith(AUDIO_EXTENSIONS):
                yield os.path.join(root, name)


class LibraryScanTask:
    """Escanea una carpeta musical y devuelve los metadatos de cada archivo.

    ``get_metadata`` se invoca con ``with_cover=False`` para no decodificar la
    imagen de portada en cada archivo: la carátula se resuelve bajo demanda.
    """

    def __init__(
        self,
        folder_path: str,
        metadata_service: Any,
        on_batch: Callable[[list[dict]], None] | None = None,
    ) -> None:
        self.folder_path = folder_path
        self.ms = metadata_service
        self.on_batch = on_batch

    def __call__(self, cancel_event: threading.Event | None = None) -> list[dict]:
        results: list[dict] = []
        batch: list[dict] = []
        for path in iter_audio_files(self.folder_path):
            if cancel_event is not None and cancel_event.is_set():
                break
            root = os.path.dirname(path)
            meta = self.ms.get_metadata(path, with_cover=False)
            batch.append(
                {
                    "path": path,
                    "filename": os.path.basename(path),
                    "title": meta.get("title") or os.path.basename(path),
                    "artist": meta.get("artist") or "Desconocido",
                    "album": meta.get("album") or "Desconocido",
                    "rel_dir": os.path.relpath(root, self.folder_path),
                    "duration": meta.get("duration", 0) or 0,
                }
            )
            if len(batch) >= SCAN_BATCH_SIZE:
                results.extend(batch)
                if self.on_batch:
                    self.on_batch(batch)
                batch = []
        if batch:
            results.extend(batch)
            if self.on_batch:
                self.on_batch(batch)
        return results


class CoverSearchTask:
    """Busca una carátula en línea (iTunes) para artista/álbum."""

    def __init__(self, metadata_service: Any, artist: str, album: str) -> None:
        self.ms = metadata_service
        self.artist = artist
        self.album = album

    def __call__(self, cancel_event: threading.Event | None = None) -> str | None:
        if cancel_event is not None and cancel_event.is_set():
            return None
        return self.ms.fetch_online_cover(self.artist, self.album)


class MetadataSuggestionsTask:
    """Busca sugerencias de metadatos en iTunes (no bloquea la GUI)."""

    def __init__(self, metadata_service: Any, query: str) -> None:
        self.ms = metadata_service
        self.query = query

    def __call__(self, cancel_event: threading.Event | None = None) -> list[dict]:
        if cancel_event is not None and cancel_event.is_set():
            return []
        return self.ms.search_metadata_suggestions(self.query)


class BatchTagWriteTask:
    """Escribe tags en varios archivos y devuelve un resumen por archivo."""

    def __init__(
        self,
        metadata_service: Any,
        updates: list[tuple[str, dict, bytes | None]],
    ) -> None:
        self.ms = metadata_service
        self.updates = updates

    def __call__(self, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        written = 0
        failed: list[str] = []
        for path, meta, cover in self.updates:
            if cancel_event is not None and cancel_event.is_set():
                break
            if self.ms.update_metadata(path, meta, cover):
                written += 1
            else:
                failed.append(path)
        return {"written": written, "failed": failed}
