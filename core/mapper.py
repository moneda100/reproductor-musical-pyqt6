"""Identidad de pistas: ``track_key`` estable entre dispositivos.

La clave de sincronización **no puede ser la ruta del fichero**, porque las
rutas locales difieren por dispositivo:

- Remotas (YouTube): ``yt:<video_id>``.
- Locales: ``local:<sha1(normalize(title)|normalize(artist)|round(duration))>``.

El binding ``track_key → file_path`` es local y **no** se sincroniza.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Optional

LOCAL_PREFIX = "local:"
YOUTUBE_PREFIX = "yt:"

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    """Normaliza un texto para el fingerprint.

    Minúsculas, sin diacríticos, sin puntuación y con espacios colapsados.
    ``"Café Tacvba"`` y ``"cafe  tacvba!"`` producen el mismo resultado.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def round_duration(duration: Optional[float]) -> int:
    """Redondea la duración a segundos enteros (tolerancia de ±1 s)."""
    if not duration:
        return 0
    return int(round(float(duration)))


def local_fingerprint(
    title: Optional[str], artist: Optional[str], duration: Optional[float]
) -> str:
    """Huella estable de una pista local, independiente del sistema de ficheros."""
    payload = "|".join(
        [normalize_text(title), normalize_text(artist), str(round_duration(duration))]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def local_track_key(title: Optional[str], artist: Optional[str], duration: Optional[float]) -> str:
    return f"{LOCAL_PREFIX}{local_fingerprint(title, artist, duration)}"


def youtube_track_key(video_id: Optional[str]) -> Optional[str]:
    if not video_id:
        return None
    return f"{YOUTUBE_PREFIX}{video_id}"


def is_youtube_key(track_key: Optional[str]) -> bool:
    return bool(track_key) and track_key.startswith(YOUTUBE_PREFIX)


def is_local_key(track_key: Optional[str]) -> bool:
    return bool(track_key) and track_key.startswith(LOCAL_PREFIX)


def track_key_for(track: Any) -> str:
    """Deriva el ``track_key`` de un objeto ``Track`` o de un dict."""
    if hasattr(track, "source") and hasattr(track, "title"):
        source = getattr(track, "source", "local")
        title = getattr(track, "title", "")
        artist = getattr(track, "artist", "")
        duration = getattr(track, "duration", 0)
        identifier = getattr(track, "id", "")
    else:
        source = (track or {}).get("source", "local")
        title = (track or {}).get("title", "")
        artist = (track or {}).get("artist", "")
        duration = (track or {}).get("duration", 0)
        identifier = (track or {}).get("id", "")

    if source == "youtube" and identifier:
        return youtube_track_key(identifier)
    return local_track_key(title, artist, duration)
