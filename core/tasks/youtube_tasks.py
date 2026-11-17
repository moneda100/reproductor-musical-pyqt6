"""Tareas de YouTube (yt-dlp) ejecutadas en el ``QThreadPool``."""

from __future__ import annotations

import threading
from typing import Any, Callable

from core.playlist import Track
from core.tasks.worker import Worker


def _build_track(info: dict) -> Track:
    return Track(
        id=info["id"],
        title=info.get("title", "Sin título"),
        artist=info.get("artist", "Desconocido"),
        album=info.get("album", "YouTube"),
        file_path=info["local_file"],
        duration=info.get("duration", 0) or 0,
        cover_url=info.get("thumbnail"),
        source="youtube",
    )


def _download(
    service: Any,
    url: str,
    permanent: bool,
    audio_format: str,
    progress_hook: Callable[[dict], None] | None,
    cancel_event: threading.Event | None,
) -> dict | None:
    """Llama al servicio pasando el hook de progreso.

    Los dobles de prueba antiguos (y servicios de terceros) pueden no aceptar
    ``progress_hook``/``cancel_event``; en ese caso se reintenta sin ellos.
    """
    try:
        return service.get_info(
            url,
            permanent=permanent,
            audio_format=audio_format,
            progress_hook=progress_hook,
            cancel_event=cancel_event,
        )
    except TypeError:
        return service.get_info(url, permanent=permanent, audio_format=audio_format)


def _make_progress_hook(
    cancel_event: threading.Event | None,
    on_progress: Callable[[dict], None] | None,
) -> Callable[[dict], None]:
    def hook(data: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Descarga cancelada")
        if on_progress is not None:
            on_progress(data)

    return hook


class YouTubeSearchTask:
    """Busca canciones en YouTube (sin descargar)."""

    def __init__(
        self,
        service: Any,
        query: str,
        max_results: int = 20,
        offset: int = 0,
    ) -> None:
        self.service = service
        self.query = query
        self.max_results = max_results
        self.offset = offset

    def __call__(self, cancel_event: threading.Event | None = None) -> list[dict]:
        if cancel_event is not None and cancel_event.is_set():
            return []
        try:
            return self.service.search_songs(
                self.query,
                max_results=self.max_results,
                offset=self.offset,
            )
        except TypeError:
            # Dobles de prueba antiguos sin soporte de paginación.
            return self.service.search_songs(self.query, max_results=self.max_results)


class YouTubePlaylistTask:
    """Obtiene la lista de vídeos de una playlist de YouTube."""

    def __init__(self, service: Any, url: str) -> None:
        self.service = service
        self.url = url

    def __call__(self, cancel_event: threading.Event | None = None) -> list[dict]:
        if cancel_event is not None and cancel_event.is_set():
            return []
        return self.service.get_playlist_info(self.url)


class YouTubeDownloadTask:
    """Descarga el audio de una URL de YouTube."""

    def __init__(
        self,
        service: Any,
        url: str,
        permanent: bool = False,
        audio_format: str = "mp3",
        on_progress: Callable[[dict], None] | None = None,
    ) -> None:
        self.service = service
        self.url = url
        self.permanent = permanent
        self.audio_format = audio_format
        self.on_progress = on_progress

    def __call__(self, cancel_event: threading.Event | None = None) -> Track | None:
        if cancel_event is not None and cancel_event.is_set():
            return None
        hook = _make_progress_hook(cancel_event, self.on_progress)
        info = _download(
            self.service,
            self.url,
            self.permanent,
            self.audio_format,
            hook if self.on_progress is not None or cancel_event is not None else None,
            cancel_event,
        )
        if not info or not info.get("local_file"):
            return None
        return _build_track(info)


class YouTubeBatchDownloadTask:
    """Descarga secuencialmente varias pistas, con cancelación cooperativa.

    Callbacks (todos opcionales y ejecutados en el hilo del worker; la GUI debe
    limitarse a emitir señales Qt):

    - ``on_progress(index, total, item)``: empieza un elemento.
    - ``on_item_progress(index, data)``: hook de yt-dlp (bytes descargados).
    - ``on_item_finished(index, track)``: elemento completado.
    - ``on_item_failed(index, message)``: elemento fallido.
    """

    def __init__(
        self,
        service: Any,
        results: list[dict],
        permanent: bool = False,
        audio_format: str = "mp3",
        on_progress: Callable[[int, int, dict], None] | None = None,
        on_item_progress: Callable[[int, dict], None] | None = None,
        on_item_finished: Callable[[int, Track], None] | None = None,
        on_item_failed: Callable[[int, str], None] | None = None,
    ) -> None:
        self.service = service
        self.results = results
        self.permanent = permanent
        self.audio_format = audio_format
        self.on_progress = on_progress
        self.on_item_progress = on_item_progress
        self.on_item_finished = on_item_finished
        self.on_item_failed = on_item_failed

    def __call__(self, cancel_event: threading.Event | None = None) -> list[Track]:
        tracks: list[Track] = []
        total = len(self.results)
        for index, res in enumerate(self.results):
            if cancel_event is not None and cancel_event.is_set():
                break
            if self.on_progress:
                self.on_progress(index, total, res)

            hook = _make_progress_hook(
                cancel_event,
                (lambda data, idx=index: self.on_item_progress(idx, data))
                if self.on_item_progress
                else None,
            )
            try:
                info = _download(
                    self.service,
                    res["url"],
                    self.permanent,
                    self.audio_format,
                    hook,
                    cancel_event,
                )
            except Exception:  # noqa: BLE001 - un fallo no cancela el lote
                info = None

            if not info or not info.get("local_file"):
                if cancel_event is not None and cancel_event.is_set():
                    break
                if self.on_item_failed:
                    self.on_item_failed(index, "No se pudo descargar el audio")
                continue

            track = _build_track(info)
            tracks.append(track)
            if self.on_item_finished:
                self.on_item_finished(index, track)
        return tracks


class YouTubeStreamTask:
    """Resuelve la URL directa de un stream (audio o vídeo)."""

    def __init__(self, service: Any, url: str, video: bool = True) -> None:
        self.service = service
        self.url = url
        self.video = video

    def __call__(self, cancel_event: threading.Event | None = None) -> str | None:
        if cancel_event is not None and cancel_event.is_set():
            return None
        try:
            return self.service.get_stream_url(self.url, video=self.video)
        except TypeError:
            return self.service.get_stream_url(self.url)


def make_worker(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Worker:
    """Azúcar sintáctico: crea un :class:`Worker` a partir de una callable."""
    return Worker(fn, *args, **kwargs)
