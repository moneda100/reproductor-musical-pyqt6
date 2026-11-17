"""Almacén local SQLite: favoritos, historial, bindings de pista y sesión.

Es **local**: no se sincroniza. La tabla ``track_binding`` relaciona un
``track_key`` (identidad global) con la ruta del fichero en **este**
dispositivo.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.migrations import migrate
from core.paths import get_paths

logger = logging.getLogger(__name__)


def _thread_safe(cls):
    """Serializa el acceso concurrente a SQLite con un RLock por instancia."""
    skip = {"__init__", "close", "closed"}
    for name, attr in list(cls.__dict__.items()):
        if name in skip or name.startswith("__"):
            continue
        if isinstance(attr, (classmethod, staticmethod, property)):
            continue
        if callable(attr):
            original = attr

            def make(original, method_name):
                def wrapper(self, *args, **kwargs):
                    with self._lock:
                        if self._conn is None:
                            if method_name in ("favorites", "history"):
                                return []
                            if method_name in ("all_bindings", "get_session"):
                                return {}
                            return None
                        return original(self, *args, **kwargs)

                wrapper.__name__ = getattr(original, "__name__", method_name)
                wrapper.__doc__ = original.__doc__
                return wrapper

            setattr(cls, name, make(original, name))
    return cls


@_thread_safe
class LocalStore:
    """Acceso al ``state.db`` de la aplicación."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self.path = Path(path) if path else get_paths().state_db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.version = migrate(self._conn)

    def close(self) -> None:
        if not hasattr(self, "_lock"):
            return
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error as exc:
                logger.debug("Error al cerrar el almacén: %s", exc)
            finally:
                self._conn = None

    @property
    def closed(self) -> bool:
        return self._conn is None

    # -- favoritos ------------------------------------------------------
    def add_favorite(self, track: Any) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO favorites
                (track_key, title, artist, album, duration, cover_url, file_path, source, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track.track_key,
                track.title,
                track.artist,
                track.album,
                float(track.duration or 0),
                track.cover_url,
                track.file_path,
                track.source,
                time.time(),
            ),
        )
        self._conn.commit()

    def remove_favorite(self, track_key: str) -> None:
        self._conn.execute("DELETE FROM favorites WHERE track_key = ?", (track_key,))
        self._conn.commit()

    def is_favorite(self, track_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM favorites WHERE track_key = ?", (track_key,)
        ).fetchone()
        return row is not None

    def favorites(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM favorites ORDER BY added_at DESC").fetchall()
        return [dict(row) for row in rows]

    # -- historial -------------------------------------------------------
    def add_history(self, track: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO history
                (track_key, title, artist, album, duration, cover_url, file_path, source, played_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track.track_key,
                track.title,
                track.artist,
                track.album,
                float(track.duration or 0),
                track.cover_url,
                track.file_path,
                track.source,
                time.time(),
            ),
        )
        self._conn.execute(
            """
            DELETE FROM history WHERE id NOT IN (
                SELECT id FROM history ORDER BY played_at DESC LIMIT 500
            )
            """
        )
        self._conn.commit()

    def history(self, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM history ORDER BY played_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def clear_history(self) -> None:
        self._conn.execute("DELETE FROM history")
        self._conn.commit()

    def remove_history(self, track_key: str) -> None:
        """Elimina una entrada del historial por su ``track_key``."""
        self._conn.execute("DELETE FROM history WHERE track_key = ?", (track_key,))
        self._conn.commit()

    # -- bindings de pista ------------------------------------------------
    def set_binding(self, track_key: str, file_path: str) -> None:
        try:
            stat = os.stat(file_path)
            size, mtime = stat.st_size, stat.st_mtime
        except OSError:
            size, mtime = 0, 0.0
        self._conn.execute(
            """
            INSERT OR REPLACE INTO track_binding (track_key, file_path, size, mtime)
            VALUES (?, ?, ?, ?)
            """,
            (track_key, file_path, size, mtime),
        )
        self._conn.commit()

    def get_binding(self, track_key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT file_path FROM track_binding WHERE track_key = ?", (track_key,)
        ).fetchone()
        if row is None:
            return None
        path = row["file_path"]
        return path if os.path.exists(path) else None

    def all_bindings(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT track_key, file_path FROM track_binding").fetchall()
        return {row["track_key"]: row["file_path"] for row in rows}

    # -- sesión ------------------------------------------------------------
    def set_session_value(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO session_state (key, value) VALUES (?, ?)", (key, value)
        )
        self._conn.commit()

    def get_session_value(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM session_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_session(self, state: dict[str, Any]) -> None:
        for key, value in state.items():
            self.set_session_value(key, json.dumps(value, ensure_ascii=False))

    def get_session(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM session_state").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                continue
        return result
