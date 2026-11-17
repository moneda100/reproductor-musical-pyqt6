"""Scrobbling en Last.fm.

Implementación propia sobre la API HTTP (firma MD5), sin dependencias
externas: ``pylast`` es opcional. Las reglas oficiales se respetan:

- *now playing* al empezar a reproducir.
- *scrobble* al 50 % de la pista o a los 4 minutos, lo que ocurra antes.
- Cola offline en disco: si no hay red, el scrobble se guarda y se envía
  cuando vuelve la conexión.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from core.paths import get_paths
from core.playlist import Track

logger = logging.getLogger(__name__)

API_URL = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "MusicPlayerPro/1.2 (+https://github.com/musicplayerpro)"
SCROBBLE_AFTER_SECONDS = 240
SCROBBLE_AFTER_RATIO = 0.5


@dataclass
class Scrobble:
    """Un scrobble pendiente."""

    artist: str
    title: str
    album: str = ""
    duration: int = 0
    timestamp: int = 0
    track_number: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


class LastFmService:
    """Cliente de Last.fm con cola offline."""

    def __init__(
        self,
        api_key: str = "",
        username: str = "",
        session_key: str = "",
        api_secret: str = "",
        queue_path: Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.username = username
        self.session_key = session_key
        self.api_secret = api_secret or api_key
        self.queue_path = queue_path or get_paths().cache_dir / "lastfm_queue.json"
        self._last_track_key: Optional[str] = None

    # -- configuración ---------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.username and self.session_key)

    def configure(self, api_key: str, username: str, session_key: str = "") -> None:
        self.api_key = api_key
        self.username = username
        if session_key:
            self.session_key = session_key

    # -- firma ------------------------------------------------------------
    def _sign(self, params: dict[str, str]) -> str:
        payload = "".join(f"{key}{params[key]}" for key in sorted(params) if key != "api_sig")
        return hashlib.md5((payload + self.api_secret).encode("utf-8")).hexdigest()

    def _call(self, method: str, params: dict[str, str]) -> Optional[dict]:
        if not self.api_key:
            return None
        payload = dict(params)
        payload["method"] = method
        payload["api_key"] = self.api_key
        payload["api_sig"] = self._sign(payload)
        payload["format"] = "json"
        url = API_URL + "?" + urllib.parse.urlencode(payload)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Last.fm falló (%s): %s", method, exc)
            return None
        if "error" in data:
            logger.warning("Last.fm devolvió un error: %s", data.get("message"))
            return None
        return data

    # -- autenticación -----------------------------------------------------
    def authenticate(self, password: str) -> bool:
        """Obtiene una clave de sesión a partir del usuario y la contraseña."""
        if not self.api_key or not self.username:
            return False
        data = self._call(
            "auth.getMobileSession", {"username": self.username, "password": password}
        )
        if not data:
            return False
        session = data.get("session", {})
        key = session.get("key")
        if key:
            self.session_key = key
            return True
        return False

    # -- scrobbling ----------------------------------------------------------
    def now_playing(self, track: Track) -> bool:
        """Anuncia la pista en curso."""
        if not self.configured:
            return False
        if not track.artist or not track.title:
            return False
        data = self._call(
            "track.updateNowPlaying",
            {
                "artist": track.artist,
                "track": track.title,
                "album": track.album or "",
                "sk": self.session_key,
                "duration": str(int(track.duration or 0)),
            },
        )
        return data is not None

    def scrobble(self, track: Track, timestamp: int | None = None) -> bool:
        """Envía el scrobble. Si no hay red, se encola para más tarde."""
        if not track.artist or not track.title:
            return False
        payload = Scrobble(
            artist=track.artist,
            title=track.title,
            album=track.album or "",
            duration=int(track.duration or 0),
            timestamp=int(timestamp or time.time()),
        )
        if not self.configured:
            self._enqueue(payload)
            return False
        data = self._call(
            "track.scrobble",
            {
                "artist": payload.artist,
                "track": payload.title,
                "album": payload.album,
                "timestamp": str(payload.timestamp),
                "duration": str(payload.duration),
                "sk": self.session_key,
            },
        )
        if data is None:
            self._enqueue(payload)
            return False
        return True

    @staticmethod
    def should_scrobble(position_seconds: float, duration_seconds: float) -> bool:
        """Regla oficial: 50 % de la pista o 4 minutos, lo que ocurra antes."""
        if duration_seconds <= 0:
            return False
        return position_seconds >= min(
            duration_seconds * SCROBBLE_AFTER_RATIO, SCROBBLE_AFTER_SECONDS
        )

    # -- cola offline ---------------------------------------------------------
    def _enqueue(self, payload: Scrobble) -> None:
        queue = self.read_queue()
        queue.append(payload.to_dict())
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            self.queue_path.write_text(
                json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("No se pudo guardar la cola de Last.fm: %s", exc)

    def read_queue(self) -> list[dict]:
        if not self.queue_path.exists():
            return []
        try:
            return json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Cola de Last.fm ilegible: %s", exc)
            return []

    def flush_queue(self) -> int:
        """Reenvía los scrobbles pendientes. Devuelve el número enviado."""
        if not self.configured:
            return 0
        queue = self.read_queue()
        if not queue:
            return 0
        sent = 0
        remaining: list[dict] = []
        for item in queue:
            params = {
                "artist": item.get("artist", ""),
                "track": item.get("title", ""),
                "album": item.get("album", ""),
                "timestamp": str(item.get("timestamp", 0)),
                "duration": str(item.get("duration", 0)),
                "sk": self.session_key,
            }
            if self._call("track.scrobble", params) is not None:
                sent += 1
            else:
                remaining.append(item)
        try:
            self.queue_path.write_text(
                json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.debug("No se pudo actualizar la cola de Last.fm: %s", exc)
        if sent:
            logger.info("Last.fm: %d scrobbles pendientes enviados", sent)
        return sent
