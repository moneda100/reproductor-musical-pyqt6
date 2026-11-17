"""Letras de canciones: cliente LRCLIB con fallback a lyrics.ovh.

Diferencia entre pistas locales y de YouTube:
- Pistas locales: primero intenta leer letras incrustadas en el archivo
  (USLT para MP3, LYRICS para FLAC, \xa9lyr para MP4), y si no hay,
  busca online por título/artista/álbum.
- Pistas de YouTube: busca online usando título/artista y, opcionalmente,
  el video ID para afinar la búsqueda.

La letra se cachea en disco por ``track_key``.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from core.paths import get_paths

logger = logging.getLogger(__name__)

LRCLIB_GET = "https://lrclib.net/api/get"
LRCLIB_SEARCH = "https://lrclib.net/api/search"
LYRICS_OVH = "https://api.lyrics.ovh/v1/{artist}/{title}"

HEADERS = {"User-Agent": "MusicPlayerPro/1.2 (+https://github.com/musicplayerpro)"}
TIMEOUT = 8

_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\](.*)")


@dataclass
class LyricLine:
    """Una línea de letra con su marca de tiempo."""

    timestamp_ms: int
    text: str


def parse_lrc(content: str) -> list[LyricLine]:
    """Convierte el formato LRC en una lista de líneas ordenadas."""
    lines: list[LyricLine] = []
    for raw in (content or "").splitlines():
        match = _LRC_LINE.match(raw.strip())
        if not match:
            continue
        minutes, seconds, text = match.groups()
        seconds_value = float(seconds.replace(":", "."))
        timestamp = int(minutes) * 60_000 + int(seconds_value * 1000)
        lines.append(LyricLine(timestamp_ms=timestamp, text=text.strip()))
    lines.sort(key=lambda item: item.timestamp_ms)
    return lines


def active_line_index(lines: list[LyricLine], position_ms: int) -> int:
    """Índice de la línea activa para la posición dada (-1 si no hay)."""
    if not lines:
        return -1
    index = -1
    for position, line in enumerate(lines):
        if line.timestamp_ms <= position_ms:
            index = position
        else:
            break
    return index


class LyricsService:
    """Obtiene letras (sincronizadas si es posible) y las cachea localmente.

    Para pistas locales, primero intenta leer letras incrustadas en el archivo.
    Para pistas de YouTube, busca online con el video ID si está disponible.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else get_paths().cache_dir / "lyrics"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- caché --------------------------------------------------------
    def _cache_path(self, track_key: str) -> Path:
        safe = "".join(ch for ch in track_key if ch.isalnum() or ch in "-_")
        return self.cache_dir / f"{safe}.json"

    def read_cache(self, track_key: str) -> Optional[dict]:
        path = self._cache_path(track_key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Caché de letra ilegible %s: %s", path, exc)
            return None

    def write_cache(self, track_key: str, payload: dict) -> None:
        try:
            with open(self._cache_path(track_key), "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
        except OSError as exc:
            logger.debug("No se pudo cachear la letra: %s", exc)

    # -- letras incrustadas en archivos locales -----------------------
    def read_embedded_lyrics(self, file_path: str) -> Optional[str]:
        """Lee letras incrustadas en un archivo de audio local.

        Usa MetadataService para extraer letras de USLT (MP3),
        LYRICS (FLAC) o \xa9lyr (MP4).
        """
        from services.metadata_service import MetadataService

        ms = MetadataService()
        try:
            meta = ms.get_metadata(file_path, with_cover=False)
            lyrics = meta.get("lyrics", "")
            if lyrics and lyrics.strip():
                return lyrics
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudieron leer letras incrustadas de %s: %s", file_path, exc)
        return None

    # -- búsqueda ------------------------------------------------------
    def fetch_lyrics(
        self,
        title: str,
        artist: str,
        album: str = "",
        duration: Optional[float] = None,
        is_youtube: bool = False,
        video_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Devuelve ``{'synced': [...], 'plain': str}`` o ``None``.

        Para YouTube, añade el video ID como pista adicional en la búsqueda
        de LRCLIB cuando está disponible.
        """
        if is_youtube and video_id:
            # Búsqueda específica para YouTube: incluir video ID como pista
            payload = self._fetch_lrclib(title, artist, album, duration, extra_query=video_id)
            if payload is None:
                payload = self._fetch_lyrics_ovh(title, artist)
        else:
            payload = self._fetch_lrclib(title, artist, album, duration)
            if payload is None:
                payload = self._fetch_lyrics_ovh(title, artist)
        return payload

    def _fetch_lrclib(
        self,
        title: str,
        artist: str,
        album: str,
        duration: Optional[float],
        extra_query: Optional[str] = None,
    ) -> Optional[dict]:
        params = {
            "track_name": title,
            "artist_name": artist,
            "album_name": album or "",
        }
        if duration:
            params["duration"] = int(round(float(duration)))
        if extra_query:
            params["q"] = extra_query
        try:
            response = requests.get(LRCLIB_GET, params=params, timeout=TIMEOUT, headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                return self._to_payload(data)
            logger.debug("LRCLIB respondió %s", response.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LRCLIB falló: %s", exc)

        # Segundo intento: búsqueda laxa.
        try:
            query = f"{artist} {title}".strip()
            if extra_query:
                query = f"{query} {extra_query}"
            response = requests.get(
                LRCLIB_SEARCH,
                params={"q": query},
                timeout=TIMEOUT,
                headers=HEADERS,
            )
            if response.status_code == 200:
                candidates = response.json() or []
                if candidates:
                    return self._to_payload(candidates[0])
        except Exception as exc:  # noqa: BLE001
            logger.debug("Búsqueda en LRCLIB falló: %s", exc)
        return None

    @staticmethod
    def _to_payload(data: dict) -> dict:
        synced_raw = data.get("syncedLyrics") or ""
        plain = data.get("plainLyrics") or ""
        lines = parse_lrc(synced_raw) if synced_raw else []
        if not lines and plain:
            lines = [LyricLine(timestamp_ms=0, text=line) for line in plain.splitlines()]
        return {"synced": lines, "plain": plain}

    def _fetch_lyrics_ovh(self, title: str, artist: str) -> Optional[dict]:
        if not artist or not title:
            return None
        url = LYRICS_OVH.format(artist=urllib.parse.quote(artist), title=urllib.parse.quote(title))
        try:
            response = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            if response.status_code == 200 and response.text.strip():
                plain = response.text.strip()
                lines = [LyricLine(timestamp_ms=0, text=line) for line in plain.splitlines()]
                return {"synced": lines, "plain": plain}
        except Exception as exc:  # noqa: BLE001
            logger.debug("lyrics.ovh falló: %s", exc)
        return None

    def get_lyrics(
        self,
        track_key: str,
        title: str,
        artist: str,
        album: str = "",
        duration: Optional[float] = None,
        is_youtube: bool = False,
        video_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Optional[dict]:
        """Letra con caché en disco por ``track_key``.

        Para pistas locales con archivo disponible, primero intenta leer
        letras incrustadas antes de buscar online.
        """
        cached = self.read_cache(track_key)
        if cached is not None:
            lines = [LyricLine(**line) for line in cached.get("synced", [])]
            cached["synced"] = lines
            return cached

        # Para pistas locales, intentar letras incrustadas primero
        if not is_youtube and file_path:
            embedded = self.read_embedded_lyrics(file_path)
            if embedded:
                lines = [
                    LyricLine(timestamp_ms=0, text=line)
                    for line in embedded.splitlines()
                    if line.strip()
                ]
                payload = {"synced": lines, "plain": embedded}
                self.write_cache(
                    track_key,
                    {
                        "synced": [line.__dict__ for line in payload["synced"]],
                        "plain": payload["plain"],
                    },
                )
                return payload

        payload = self.fetch_lyrics(
            title, artist, album, duration, is_youtube=is_youtube, video_id=video_id
        )
        if payload is None:
            return None
        self.write_cache(
            track_key,
            {
                "synced": [line.__dict__ for line in payload["synced"]],
                "plain": payload["plain"],
            },
        )
        return payload
