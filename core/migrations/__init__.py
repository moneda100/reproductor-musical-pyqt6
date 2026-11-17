"""Migraciones numeradas del almacén local (``state.db``).

Cada migración tiene un número y se aplica una sola vez. ``user_version`` de
SQLite registra la versión aplicada, de modo que un ``state.db`` antiguo se
actualiza solo al abrir la app.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, List, Tuple


def _m001_initial(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            track_key TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            artist TEXT NOT NULL DEFAULT '',
            album TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0,
            cover_url TEXT,
            file_path TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            added_at REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_key TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            artist TEXT NOT NULL DEFAULT '',
            album TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0,
            cover_url TEXT,
            file_path TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            played_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);

        CREATE TABLE IF NOT EXISTS track_binding (
            track_key TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            mtime REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS session_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        """
    )


def _m002_playlists(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS playlists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS playlist_items (
            playlist_id TEXT NOT NULL,
            track_key TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            artist TEXT NOT NULL DEFAULT '',
            album TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0,
            cover_url TEXT,
            file_path TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (playlist_id, track_key)
        );
        CREATE INDEX IF NOT EXISTS idx_playlist_items ON playlist_items(playlist_id, position);
        """
    )


def _m003_sync_outbox(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            op TEXT NOT NULL,
            item_id TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            base_version INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        """
    )


MIGRATIONS: List[Tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _m001_initial),
    (2, _m002_playlists),
    (3, _m003_sync_outbox),
]


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Aplica las migraciones pendientes. Devuelve la versión final."""
    version = current_version(conn)
    for number, apply in MIGRATIONS:
        if number > version:
            apply(conn)
            conn.execute(f"PRAGMA user_version = {number}")
            version = number
    conn.commit()
    return version
