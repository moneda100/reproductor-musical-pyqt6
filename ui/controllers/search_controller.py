"""Controlador de búsqueda y descargas de YouTube."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from core.playlist import Track
from core.tasks.library_tasks import CoverSearchTask
from core.tasks.worker import TaskGroup, Worker
from core.tasks.youtube_tasks import (
    YouTubeBatchDownloadTask,
    YouTubeDownloadTask,
    YouTubePlaylistTask,
    YouTubeSearchTask,
    YouTubeStreamTask,
)

logger = logging.getLogger(__name__)


class SearchController(QObject):
    """Búsquedas y descargas ejecutadas en el ``QThreadPool``."""

    results_ready = pyqtSignal(list, str)  # resultados, título
    results_appended = pyqtSignal(list, str)  # resultados nuevos, consulta
    error_occurred = pyqtSignal(str)
    status_message = pyqtSignal(str)
    download_started = pyqtSignal(int)  # número de elementos del lote
    download_progress = pyqtSignal(int, int, dict)  # índice, total, elemento
    download_item_started = pyqtSignal(int, dict)
    download_item_progress = pyqtSignal(int, dict)  # índice, datos de yt-dlp
    download_item_finished = pyqtSignal(int, object)  # índice, Track
    download_item_failed = pyqtSignal(int, str)
    download_finished = pyqtSignal(list)  # list[Track]
    download_cancelled = pyqtSignal()
    download_item_ready = pyqtSignal(object)  # Track
    cover_found = pyqtSignal(str)  # URL de carátula
    stream_found = pyqtSignal(str)
    stream_resolved = pyqtSignal(object, str, bool)  # Track, URL, es_vídeo

    def __init__(
        self,
        youtube_service,
        metadata_service=None,
        pool: Optional[QThreadPool] = None,
        task_group: Optional[TaskGroup] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.service = youtube_service
        self.metadata_service = metadata_service
        self.pool = pool or QThreadPool(self)
        self.tasks = task_group or TaskGroup()
        self._search_worker: Optional[Worker] = None
        self._download_worker: Optional[Worker] = None
        self._search_token = 0
        self.last_query = ""

    # -- búsqueda --------------------------------------------------------
    def search(self, query: str, max_results: int = 20, offset: int = 0) -> None:
        """Busca canciones en YouTube (cancela la búsqueda anterior).

        Con ``offset > 0`` los resultados se emiten por ``results_appended``
        en lugar de ``results_ready``, para implementar «Cargar más».
        """
        self.cancel_search()
        token = self._search_token
        self.last_query = query
        task = YouTubeSearchTask(
            self.service,
            query,
            max_results=max_results,
            offset=offset,
        )

        def on_result(results: list) -> None:
            if token != self._search_token:
                return
            if offset > 0:
                self.results_appended.emit(results, query)
            else:
                self.results_ready.emit(results, f"Resultados de «{query}»")

        worker = Worker(task)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self._search_worker = worker
        self.pool.start(worker)

    def load_playlist(self, url: str) -> None:
        """Carga la lista de vídeos de una playlist de YouTube."""
        self.cancel_search()
        token = self._search_token
        self.last_query = ""
        task = YouTubePlaylistTask(self.service, url)

        def on_result(results: list) -> None:
            if token != self._search_token:
                return
            title = results[0].get("playlist", "Playlist") if results else "Playlist"
            self.results_ready.emit(results, f"📜 {title}")

        worker = Worker(task)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self._search_worker = worker
        self.pool.start(worker)

    def cancel_search(self) -> None:
        self._search_token += 1
        if self._search_worker is not None:
            self._search_worker.cancel()
            self._search_worker = None

    # -- descargas -------------------------------------------------------
    def download(self, url: str, permanent: bool = False, audio_format: str = "mp3") -> None:
        """Descarga una pista concreta."""
        self.cancel_download()
        self.download_started.emit(1)
        task = YouTubeDownloadTask(
            self.service,
            url,
            permanent=permanent,
            audio_format=audio_format,
            on_progress=lambda data: self.download_item_progress.emit(0, data),
        )

        def on_result(track: Optional[Track]) -> None:
            if track is None:
                self.download_item_failed.emit(0, "No se pudo descargar el audio.")
                self.error_occurred.emit("No se pudo descargar el audio.")
                return
            self.download_item_finished.emit(0, track)
            self.download_item_ready.emit(track)

        worker = Worker(task)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error_occurred.emit)
        worker.signals.cancelled.connect(lambda: self._on_cancelled(worker))
        self.tasks.add(worker)
        self._download_worker = worker
        self.pool.start(worker)

    def download_all(
        self, results: list[dict], permanent: bool = False, audio_format: str = "mp3"
    ) -> None:
        """Descarga secuencialmente una lista de resultados."""
        self.cancel_download()
        if not results:
            self.download_finished.emit([])
            return
        self.download_started.emit(len(results))

        def progress(index: int, total: int, item: dict) -> None:
            self.download_progress.emit(index, total, item)
            self.download_item_started.emit(index, item)

        task = YouTubeBatchDownloadTask(
            self.service,
            results,
            permanent,
            audio_format,
            progress,
            on_item_progress=lambda index, data: self.download_item_progress.emit(index, data),
            on_item_finished=lambda index, track: self.download_item_finished.emit(index, track),
            on_item_failed=lambda index, message: self.download_item_failed.emit(index, message),
        )

        def on_result(tracks: list) -> None:
            self.download_finished.emit(tracks)

        worker = Worker(task)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error_occurred.emit)
        worker.signals.cancelled.connect(lambda: self._on_cancelled(worker))
        self.tasks.add(worker)
        self._download_worker = worker
        self.pool.start(worker)

    def _on_cancelled(self, worker: Worker) -> None:
        # Ignora la cancelación de un lote antiguo si ya empezó otro.
        if self._download_worker is worker:
            self._download_worker = None
            self.download_cancelled.emit()

    def cancel_download(self) -> None:
        if self._download_worker is not None:
            # No se borra la referencia aquí: el worker sigue emitiendo
            # ``cancelled`` cuando su hook de progreso detecta el evento.
            self._download_worker.cancel()

    # -- carátulas y vídeo -------------------------------------------------
    def search_cover(self, artist: str, album: str) -> None:
        """Busca una carátula en línea (no bloquea la GUI)."""
        if self.metadata_service is None:
            return
        task = CoverSearchTask(self.metadata_service, artist, album)
        worker = Worker(task)
        worker.signals.result.connect(lambda url: self.cover_found.emit(url) if url else None)
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self.pool.start(worker)

    def fetch_stream(self, url: str, video: bool = True) -> None:
        task = YouTubeStreamTask(self.service, url, video=video)
        worker = Worker(task)
        worker.signals.result.connect(lambda url_found: self.stream_found.emit(url_found or ""))
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self.pool.start(worker)

    def resolve_stream(self, track, video: bool = False) -> None:
        """Resuelve en segundo plano el stream de una pista de YouTube.

        La pista puede venir de la playlist y no tener archivo local: en ese
        caso se resuelve al vuelo y se emite ``stream_resolved(track, url)``.
        """
        if track is None:
            return
        video_id = getattr(track, "youtube_id", "") or ""
        source = getattr(track, "file_path", "") or ""
        raw_id = str(getattr(track, "id", "") or "")
        if source.startswith("http"):
            url = source
        elif raw_id.startswith("http"):
            url = raw_id
        elif video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
        else:
            url = source
        if not url:
            self.stream_resolved.emit(track, "", video)
            return

        task = YouTubeStreamTask(self.service, url, video=video)
        worker = Worker(task)
        stream_resolved = self.stream_resolved

        def on_result(url_found: str) -> None:
            # El worker puede terminar después de cerrar la ventana; no se debe
            # emitir sobre un QObject ya destruido.
            if not sip.isdeleted(self):
                stream_resolved.emit(track, url_found or "", video)

        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self.pool.start(worker)
