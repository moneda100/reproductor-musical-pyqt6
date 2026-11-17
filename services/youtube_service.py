"""Servicio de YouTube basado en yt-dlp: búsqueda, descarga, playlists y stream."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import yt_dlp

from core.paths import get_paths

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_RESULTS = 20

# Bitrate medio usado para estimar el peso antes de descargar. El tamaño real
# de FLAC depende del contenido, así que se muestra siempre como aproximado.
AUDIO_BITRATES_KBPS = {
    "mp3": 192,
    "flac": 900,
    "m4a": 256,
    "wav": 1411,
}


class DownloadCancelled(Exception):
    """Cancela una descarga en curso desde un ``progress_hook``."""


def estimate_audio_size(duration: float, audio_format: str = "mp3") -> int:
    """Peso aproximado (bytes) de una pista según su duración y formato.

    Se usa para mostrar el total seleccionado antes de descargar. Cuando el
    archivo termina se reemplaza por su tamaño real.
    """
    bitrate = AUDIO_BITRATES_KBPS.get((audio_format or "mp3").lower(), 192)
    seconds = max(0.0, float(duration or 0))
    return int(seconds * bitrate * 1000 / 8)


class YouTubeService:
    """Servicio de YouTube con descarga a caché local y soporte de playlists."""

    def __init__(self, cache_dir: str | None = None) -> None:
        if cache_dir is None:
            cache_dir = str(get_paths().youtube_cache_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir = self.cache_dir  # por defecto descarga en caché

    # -- configuración ----------------------------------------------
    def set_download_dir(self, new_dir: str) -> None:
        self.download_dir = Path(new_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    @property
    def uses_cache_dir(self) -> bool:
        """``True`` cuando las descargas permanentes aún no tienen carpeta propia."""
        try:
            return self.download_dir.resolve() == self.cache_dir.resolve()
        except OSError:
            return self.download_dir == self.cache_dir

    # -- descarga ----------------------------------------------------
    def get_info(
        self,
        url: str,
        permanent: bool = False,
        audio_format: str = "mp3",
        progress_hook: Callable[[dict], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Optional[dict]:
        """Descarga el audio de un vídeo de YouTube.

        ``permanent=False`` guarda en la caché temporal; ``permanent=True``
        convierte al formato indicado (mp3 o flac) con metadatos en ``download_dir``.
        """
        audio_format = (audio_format or "mp3").lower()
        if audio_format not in ("mp3", "flac", "m4a", "wav"):
            audio_format = "mp3"

        def _hook(data: dict) -> None:
            # yt-dlp llama al hook desde su hilo; lanzar aquí aborta la descarga.
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled("Descarga cancelada")
            if progress_hook is not None:
                progress_hook(data)

        try:
            if permanent:
                output_template = str(self.download_dir / "%(title)s - %(uploader)s.%(ext)s")
                postprocessors = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_format,
                        "preferredquality": "0" if audio_format == "flac" else "192",
                    },
                    {"key": "FFmpegMetadata", "add_metadata": True},
                    {"key": "EmbedThumbnail", "already_have_thumbnail": False},
                ]
            else:
                output_template = str(self.cache_dir / "%(id)s.%(ext)s")
                postprocessors = []

            ydl_opts: dict[str, Any] = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "outtmpl": output_template,
                "extractor_args": {"youtube": {"player_client": ["android_music", "android"]}},
            }
            if permanent:
                ydl_opts["writethumbnail"] = True
                ydl_opts["postprocessors"] = postprocessors
            if progress_hook is not None or cancel_event is not None:
                ydl_opts["progress_hooks"] = [_hook]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if "entries" in info:
                    info = info["entries"][0]

                base_file = ydl.prepare_filename(info)
                if permanent:
                    local_file = os.path.abspath(os.path.splitext(base_file)[0] + f".{audio_format}")
                else:
                    local_file = os.path.abspath(base_file)

                if not os.path.exists(local_file):
                    logger.warning("Archivo no encontrado tras la descarga: %s", local_file)
                    return None

                try:
                    filesize = os.path.getsize(local_file)
                except OSError:
                    filesize = 0

                logger.info("Audio descargado (%s): %s", audio_format, local_file)
                return {
                    "id": info.get("id"),
                    "title": info.get("title", "Sin título"),
                    "artist": info.get("uploader", "Desconocido"),
                    "duration": info.get("duration", 0) or 0,
                    "thumbnail": info.get("thumbnail"),
                    "local_file": local_file,
                    "filesize": filesize,
                    "webpage_url": info.get("webpage_url"),
                    "audio_format": audio_format,
                }
        except DownloadCancelled:
            logger.info("Descarga cancelada: %s", url)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error en get_info: %s", exc)
            return None

    # -- consultas ---------------------------------------------------
    def get_playlist_info(self, url: str) -> list[dict]:
        """Extrae metadatos de todos los vídeos de una playlist (sin descargar)."""
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "noplaylist": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get("entries", []) or []
                if not entries:
                    return []

                playlist_title = info.get("title", "Playlist")
                logger.info("Playlist '%s': %d vídeos", playlist_title, len(entries))
                return [
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title", "Sin título"),
                        "artist": entry.get("uploader", "Desconocido"),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": entry.get("duration", 0) or 0,
                        "thumbnail": entry.get("thumbnail"),
                        "playlist": playlist_title,
                    }
                    for entry in entries
                    if entry.get("id")
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error en get_playlist_info: %s", exc)
            return []

    def search_songs(
        self,
        query: str,
        max_results: int = DEFAULT_SEARCH_RESULTS,
        offset: int = 0,
    ) -> list[dict]:
        """Busca canciones (rápido, sin descargar).

        ``offset`` permite implementar «cargar más»: yt-dlp no expone un
        desplazamiento nativo para las búsquedas, así que se piden
        ``offset + max_results`` resultados y se descartan los ya mostrados.
        """
        offset = max(0, int(offset))
        max_results = max(1, int(max_results))
        try:
            search_url = f"ytsearch{offset + max_results}:{query}"
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(search_url, download=False)
                entries = list(results.get("entries") or [])[offset : offset + max_results]
                return [
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title", "Sin título"),
                        "artist": entry.get("uploader", "Desconocido"),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": entry.get("duration", 0) or 0,
                        "thumbnail": entry.get("thumbnail"),
                    }
                    for entry in entries
                    if entry.get("id")
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error en search_songs: %s", exc)
            return []

    def get_stream_url(self, url: str, video: bool = True) -> Optional[str]:
        """Extrae la URL directa del stream.

        ``video=True`` devuelve vídeo + audio (para el modo vídeo);
        ``video=False`` devuelve solo audio, que es lo que se usa al
        reproducir en streaming desde los resultados de búsqueda.
        """
        try:
            ydl_opts = {
                "format": "best" if video else "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if "url" in info:
                    return info["url"]
                entries = info.get("entries") or []
                if entries:
                    return entries[0].get("url")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error extrayendo stream_url: %s", exc)
        return None

    # -- mantenimiento -----------------------------------------------
    def cleanup(self) -> int:
        """Limpia los archivos del caché temporal. Devuelve el número borrado."""
        count = 0
        for entry in self.cache_dir.glob("*"):
            try:
                if entry.is_file():
                    entry.unlink()
                    count += 1
            except OSError as exc:
                logger.debug("No se pudo borrar %s: %s", entry, exc)
        logger.info("Caché limpiado: %d archivos eliminados", count)
        return count
