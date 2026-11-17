"""Gestión de múltiples playlists persistidas.

Cada playlist se guarda como un fichero JSON en ``<AppData>/playlists/`` y
sus ítems en la tabla ``playlist_items`` del almacén local, lo que permite
reordenar, mover pistas entre listas y detectar duplicados.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from core.mapper import local_track_key
from core.paths import get_paths
from core.playlist import Track
from core.store import LocalStore

logger = logging.getLogger(__name__)


@dataclass
class DuplicateGroup:
    """Grupo de pistas duplicadas."""

    key: str
    tracks: list[Track]

    @property
    def count(self) -> int:
        return len(self.tracks)


class PlaylistManager:
    """CRUD de playlists y operaciones de importación/exportación."""

    def __init__(self, store: Optional[LocalStore] = None, directory: Path | None = None):
        self.store = store or LocalStore()
        self.directory = Path(directory) if directory else get_paths().playlists_dir
        self.directory.mkdir(parents=True, exist_ok=True)

    # -- CRUD -----------------------------------------------------------
    def list_playlists(self) -> list[dict]:
        rows = self.store._conn.execute(
            "SELECT id, name, created_at, updated_at FROM playlists ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def create(self, name: str) -> str:
        playlist_id = uuid.uuid4().hex
        now = time.time()
        self.store._conn.execute(
            "INSERT INTO playlists (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (playlist_id, name, now, now),
        )
        self.store._conn.commit()
        return playlist_id

    def rename(self, playlist_id: str, name: str) -> None:
        self.store._conn.execute(
            "UPDATE playlists SET name = ?, updated_at = ? WHERE id = ?",
            (name, time.time(), playlist_id),
        )
        self.store._conn.commit()

    def delete(self, playlist_id: str) -> None:
        self.store._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self.store._conn.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
        self.store._conn.commit()

    def duplicate(self, playlist_id: str) -> Optional[str]:
        source = self.get(playlist_id)
        if source is None:
            return None
        new_id = self.create(f"{source['name']} (copia)")
        tracks = self.tracks(playlist_id)
        self.add_tracks(new_id, tracks)
        return new_id

    def get(self, playlist_id: str) -> Optional[dict]:
        row = self.store._conn.execute(
            "SELECT id, name, created_at, updated_at FROM playlists WHERE id = ?",
            (playlist_id,),
        ).fetchone()
        return dict(row) if row else None

    # -- pistas -----------------------------------------------------------
    def tracks(self, playlist_id: str) -> list[Track]:
        rows = self.store._conn.execute(
            """
            SELECT track_key, title, artist, album, duration, cover_url, file_path, source, position
            FROM playlist_items WHERE playlist_id = ? ORDER BY position
            """,
            (playlist_id,),
        ).fetchall()
        return [
            Track(
                id=row["track_key"],
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                file_path=row["file_path"],
                duration=row["duration"] or 0,
                cover_url=row["cover_url"],
                source=row["source"] or "local",
            )
            for row in rows
        ]

    def add_tracks(self, playlist_id: str, tracks: Iterable[Track]) -> int:
        added = 0
        row = self.store._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM playlist_items WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        position = int(row["pos"])
        for track in tracks:
            self.store._conn.execute(
                """
                INSERT OR REPLACE INTO playlist_items
                    (playlist_id, track_key, title, artist, album, duration, cover_url,
                     file_path, source, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    playlist_id,
                    track.track_key,
                    track.title,
                    track.artist,
                    track.album,
                    float(track.duration or 0),
                    track.cover_url,
                    track.file_path,
                    track.source,
                    position,
                ),
            )
            position += 1
            added += 1
        self.store._conn.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?", (time.time(), playlist_id)
        )
        self.store._conn.commit()
        return added

    def remove_track(self, playlist_id: str, track_key: str) -> None:
        self.store._conn.execute(
            "DELETE FROM playlist_items WHERE playlist_id = ? AND track_key = ?",
            (playlist_id, track_key),
        )
        self.store._conn.commit()

    def move_track(self, playlist_id: str, source: int, destination: int) -> bool:
        tracks = self.tracks(playlist_id)
        if not (0 <= source < len(tracks)):
            return False
        destination = max(0, min(destination, len(tracks) - 1))
        if source == destination:
            return False
        track = tracks.pop(source)
        tracks.insert(destination, track)
        for position, item in enumerate(tracks):
            self.store._conn.execute(
                "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND track_key = ?",
                (position, playlist_id, item.track_key),
            )
        self.store._conn.commit()
        return True

    def move_tracks_to(self, from_playlist: str, to_playlist: str, track_keys: list[str]) -> int:
        moved = 0
        for track_key in track_keys:
            row = self.store._conn.execute(
                "SELECT * FROM playlist_items WHERE playlist_id = ? AND track_key = ?",
                (from_playlist, track_key),
            ).fetchone()
            if row is None:
                continue
            track = Track(
                id=row["track_key"],
                title=row["title"],
                artist=row["artist"],
                album=row["album"],
                file_path=row["file_path"],
                duration=row["duration"] or 0,
                cover_url=row["cover_url"],
                source=row["source"] or "local",
            )
            self.add_tracks(to_playlist, [track])
            self.remove_track(from_playlist, track_key)
            moved += 1
        return moved

    # -- exportación -------------------------------------------------------
    def export_m3u(self, playlist_id: str, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = ["#EXTM3U"]
        for track in self.tracks(playlist_id):
            artist = track.artist or "Artista desconocido"
            title = track.title or "Sin título"
            seconds = int(track.duration or 0)
            lines.append(f"#EXTINF:{seconds},{artist} - {title}")
            lines.append(track.file_path)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    def export_json(self, playlist_id: str, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        playlist = self.get(playlist_id) or {"name": "Playlist"}
        payload = {
            "name": playlist.get("name", "Playlist"),
            "tracks": [track.to_dict() for track in self.tracks(playlist_id)],
        }
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    # -- importación ------------------------------------------------------
    def import_m3u(self, path: str | Path, name: str | None = None) -> tuple[str, list[Track]]:
        source = Path(path)
        playlist_id = self.create(name or source.stem)
        tracks: list[Track] = []
        pending: Optional[tuple[int, str, str]] = None
        for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                info = line[len("#EXTINF:") :]
                payload = info.split(",", 1)
                try:
                    seconds = int(payload[0])
                except (ValueError, IndexError):
                    seconds = 0
                label = payload[1] if len(payload) > 1 else ""
                artist, _, title = label.partition(" - ")
                pending = (seconds, artist.strip(), title.strip())
                continue
            if line.startswith("#"):
                continue
            if not os.path.exists(line):
                continue
            seconds, artist, title = pending or (0, "", Path(line).stem)
            pending = None
            tracks.append(
                Track(
                    id=Path(line).name,
                    title=title or Path(line).stem,
                    artist=artist or "Desconocido",
                    album="",
                    file_path=line,
                    duration=float(seconds),
                    source="local",
                )
            )
        self.add_tracks(playlist_id, tracks)
        return playlist_id, tracks

    def import_json(self, path: str | Path, name: str | None = None) -> tuple[str, list[Track]]:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        playlist_id = self.create(name or payload.get("name") or source.stem)
        tracks = [Track.from_dict(item) for item in payload.get("tracks", [])]
        self.add_tracks(playlist_id, tracks)
        return playlist_id, tracks

    # -- duplicados --------------------------------------------------------
    def find_duplicates(self, tracks: Iterable[Track]) -> list[DuplicateGroup]:
        """Detecta duplicados por hash de contenido y por fingerprint."""
        groups: dict[str, list[Track]] = {}
        for track in tracks:
            key = self._duplicate_key(track)
            groups.setdefault(key, []).append(track)
        return [
            DuplicateGroup(key=key, tracks=items) for key, items in groups.items() if len(items) > 1
        ]

    @staticmethod
    def _duplicate_key(track: Track) -> str:
        """Clave de duplicado: hash del contenido si es local, si no fingerprint."""
        if track.source == "local" and track.file_path and os.path.exists(track.file_path):
            try:
                digest = hashlib.sha1()
                with open(track.file_path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
                return f"file:{digest.hexdigest()}"
            except OSError as exc:
                logger.debug("No se pudo hashear %s: %s", track.file_path, exc)
        return f"fp:{local_track_key(track.title, track.artist, track.duration)}"
