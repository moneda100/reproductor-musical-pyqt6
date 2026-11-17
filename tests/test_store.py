"""Pruebas del almacén local (favoritos, historial, bindings, migraciones)."""

from __future__ import annotations

import sqlite3

from core.store import LocalStore


def _track(track_key="local:abc", title="Canción"):
    from core.playlist import Track

    return Track(
        id=track_key,
        title=title,
        artist="Artista",
        album="Álbum",
        file_path="/music/song.mp3",
        duration=120.0,
        source="local",
    )


def test_store_creates_schema(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    assert store.version >= 1
    tables = {
        row[0] for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"favorites", "history", "track_binding", "session_state"} <= tables
    store.close()


def test_favorites_roundtrip(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    track = _track()
    store.add_favorite(track)
    assert store.is_favorite(track.track_key)
    assert len(store.favorites()) == 1
    store.remove_favorite(track.track_key)
    assert not store.is_favorite(track.track_key)
    store.close()


def test_history_is_ordered_and_capped(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    for index in range(5):
        store.add_history(_track(f"local:{index}", f"Track {index}"))
    history = store.history()
    assert len(history) == 5
    assert history[0]["title"] == "Track 4"
    store.close()


def test_bindings(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    store.set_binding("local:abc", "/music/song.mp3")
    assert store.get_binding("local:abc") is None  # el fichero no existe
    store.close()


def test_session_values(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    store.set_session({"current_index": 3, "position": 12.5})
    session = store.get_session()
    assert session["current_index"] == 3
    assert session["position"] == 12.5
    store.close()


def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "state.db"
    store = LocalStore(path)
    version = store.version
    store.close()

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    store = LocalStore(path)
    assert store.version == version
    store.close()


def test_add_favorite_duplicate_does_not_create_duplicate(tmp_path):
    """Añadir el mismo favorito dos veces no crea duplicado."""
    store = LocalStore(tmp_path / "test.db")
    track = _track("key1", "Title")
    store.add_favorite(track)
    store.add_favorite(track)
    assert len(store.favorites()) == 1
    store.close()


def test_remove_nonexistent_favorite_does_not_crash(tmp_path):
    """Eliminar un favorito inexistente no debe crashear."""
    store = LocalStore(tmp_path / "test.db")
    store.remove_favorite("nonexistent_key")
    store.close()


def test_favorites_persist_after_close(tmp_path):
    """Los favoritos persisten tras cerrar y reabrir el store."""
    db_path = tmp_path / "test.db"
    store = LocalStore(db_path)
    track = _track("key1", "Title")
    store.add_favorite(track)
    store.close()
    store2 = LocalStore(db_path)
    assert store2.is_favorite(track.track_key)
    store2.close()


def test_session_roundtrip(tmp_path):
    """La sesión se guarda y restaura correctamente."""
    db_path = tmp_path / "test.db"
    store = LocalStore(db_path)
    store.set_session({"current_index": 5, "position": 120000})
    session = store.get_session()
    assert session["current_index"] == 5
    assert session["position"] == 120000
    store.close()


def test_concurrent_store_writes_do_not_lock(tmp_path):
    """Escrituras concurrentes al store no deben causar 'database is locked'."""
    import threading

    store = LocalStore(tmp_path / "test.db")
    errors = []

    def writer(i):
        try:
            track = _track(f"key{i}", f"Title{i}")
            store.add_favorite(track)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    assert len(store.favorites()) == 10
    store.close()
