"""Modelo de datos de pistas y cola de reproducción."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from core.mapper import track_key_for

logger = logging.getLogger(__name__)

MAX_HISTORY = 200


class RepeatMode(Enum):
    NONE = 0
    ALL = 1
    ONE = 2

    @classmethod
    def from_name(cls, name: str) -> "RepeatMode":
        try:
            return cls[str(name).upper()]
        except KeyError:
            return cls.NONE


@dataclass
class Track:
    """Representa una canción."""

    id: str
    title: str
    artist: str
    album: str
    file_path: str
    duration: float
    cover_url: Optional[str] = None
    source: str = "local"  # 'local' o 'youtube'
    headers: dict = field(default_factory=dict)

    @property
    def track_key(self) -> str:
        """Clave de identidad estable entre dispositivos."""
        return track_key_for(self)

    @property
    def is_youtube(self) -> bool:
        return self.source == "youtube"

    @property
    def youtube_id(self) -> str:
        """Identificador de YouTube, tolerando el prefijo ``yt:`` persistido."""
        value = str(self.id or "")
        if value.startswith("yt:"):
            return value[3:]
        return value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "file_path": self.file_path,
            "duration": self.duration,
            "cover_url": self.cover_url,
            "source": self.source,
            "headers": self.headers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        allowed = {
            "id",
            "title",
            "artist",
            "album",
            "file_path",
            "duration",
            "cover_url",
            "source",
            "headers",
        }
        payload = {k: v for k, v in (data or {}).items() if k in allowed}
        payload.setdefault("id", "")
        payload.setdefault("title", "")
        payload.setdefault("artist", "")
        payload.setdefault("album", "")
        payload.setdefault("file_path", "")
        payload.setdefault("duration", 0)
        return cls(**payload)


class Playlist:
    """Gestiona una lista de reproducción."""

    def __init__(self, name: str = "Mi Lista") -> None:
        self.name = name
        self.tracks: List[Track] = []
        self.current_index = 0
        self.shuffle = False
        self.repeat_mode = RepeatMode.NONE
        self._history: list[int] = []  # historial para retroceder en modo shuffle

    # -- contenido ---------------------------------------------------
    def __len__(self) -> int:
        return len(self.tracks)

    def add_track(self, track: Track) -> None:
        """Agrega una canción."""
        self.tracks.append(track)

    def add_tracks(self, tracks: list[Track]) -> None:
        self.tracks.extend(tracks)

    def remove_track(self, index: int) -> None:
        """Elimina una canción por índice."""
        if 0 <= index < len(self.tracks):
            self.tracks.pop(index)
            if index < self.current_index:
                self.current_index -= 1
            if self.current_index >= len(self.tracks):
                self.current_index = max(0, len(self.tracks) - 1)

    def clear(self) -> None:
        self.tracks.clear()
        self.current_index = 0
        self._history.clear()

    def move_track(self, source: int, destination: int) -> bool:
        """Reordena la cola moviendo una pista. Devuelve ``True`` si se movió."""
        if not (0 <= source < len(self.tracks)):
            return False
        destination = max(0, min(destination, len(self.tracks) - 1))
        if source == destination:
            return False
        track = self.tracks.pop(source)
        self.tracks.insert(destination, track)
        if self.current_index == source:
            self.current_index = destination
        elif source < self.current_index <= destination:
            self.current_index -= 1
        elif destination <= self.current_index < source:
            self.current_index += 1
        return True

    def find_index(self, track: Track) -> int:
        for index, candidate in enumerate(self.tracks):
            if candidate is track:
                return index
        return -1

    def find_index_by_key(self, track_key: str) -> int:
        """Índice de la pista con ese ``track_key`` (-1 si no está)."""
        for index, candidate in enumerate(self.tracks):
            if candidate.track_key == track_key:
                return index
        return -1

    # -- navegación ---------------------------------------------------
    def get_current_track(self) -> Optional[Track]:
        """Retorna la canción actual."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    def next(self) -> Optional[Track]:
        """Avanza a la siguiente canción."""
        if not self.tracks:
            return None

        if self.repeat_mode == RepeatMode.ONE:
            return self.get_current_track()

        if self.shuffle:
            if len(self.tracks) == 1:
                return self.get_current_track()
            # Nunca repetir la pista actual: elige entre el resto.
            choices = [i for i in range(len(self.tracks)) if i != self.current_index]
            self._push_history(self.current_index)
            self.current_index = random.choice(choices)
            return self.get_current_track()

        if self.current_index < len(self.tracks) - 1:
            self._push_history(self.current_index)
            self.current_index += 1
        elif self.repeat_mode == RepeatMode.ALL:
            self._push_history(self.current_index)
            self.current_index = 0
        else:
            return None
        return self.get_current_track()

    def previous(self) -> Optional[Track]:
        """Retrocede a la canción anterior."""
        if not self.tracks:
            return None

        if self.repeat_mode == RepeatMode.ONE:
            return self.get_current_track()

        if self._history:
            self.current_index = self._history.pop()
            return self.get_current_track()

        if self.current_index > 0:
            self.current_index -= 1
        elif self.repeat_mode == RepeatMode.ALL:
            self.current_index = len(self.tracks) - 1
        else:
            return None
        return self.get_current_track()

    def _push_history(self, index: int) -> None:
        self._history.append(index)
        if len(self._history) > MAX_HISTORY:
            del self._history[: len(self._history) - MAX_HISTORY]

    @property
    def history(self) -> list[int]:
        return list(self._history)

    # -- persistencia --------------------------------------------------
    def save_to_file(self, file_path: str) -> None:
        """Guarda la playlist en JSON."""
        data = {
            "name": self.name,
            "current_index": self.current_index,
            "shuffle": self.shuffle,
            "repeat_mode": self.repeat_mode.name,
            "tracks": [t.to_dict() for t in self.tracks],
        }
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, file_path: str) -> "Playlist":
        """Carga una playlist desde JSON."""
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        playlist = cls(data.get("name", "Mi Lista"))
        for track_data in data.get("tracks", []):
            playlist.add_track(Track.from_dict(track_data))
        playlist.current_index = int(data.get("current_index", 0) or 0)
        playlist.shuffle = bool(data.get("shuffle", False))
        playlist.repeat_mode = RepeatMode.from_name(data.get("repeat_mode", "NONE"))
        if playlist.tracks:
            playlist.current_index = max(0, min(playlist.current_index, len(playlist.tracks) - 1))
        else:
            playlist.current_index = 0
        return playlist
