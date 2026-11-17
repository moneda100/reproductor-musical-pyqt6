"""Pruebas del gestor de playlists, las letras y Last.fm."""

from __future__ import annotations

from core.lyrics import LyricLine, active_line_index, parse_lrc
from core.playlist import Track
from core.playlist_manager import PlaylistManager
from core.store import LocalStore


def _track(index: int = 0, **overrides) -> Track:
    payload = {
        "id": f"t{index}",
        "title": f"Título {index}",
        "artist": "Artista",
        "album": "Álbum",
        "file_path": f"/music/{index}.mp3",
        "duration": 180.0,
        "source": "local",
    }
    payload.update(overrides)
    return Track(**payload)


# ======================================================================
# Gestor de playlists
# ======================================================================
def test_playlist_crud(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    manager = PlaylistManager(store, tmp_path)

    playlist_id = manager.create("Mi lista")
    assert [p["name"] for p in manager.list_playlists()] == ["Mi lista"]

    manager.add_tracks(playlist_id, [_track(0), _track(1)])
    tracks = manager.tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "Título 0"

    manager.rename(playlist_id, "Renombrada")
    assert manager.get(playlist_id)["name"] == "Renombrada"

    copy_id = manager.duplicate(playlist_id)
    assert copy_id is not None
    assert len(manager.tracks(copy_id)) == 2

    manager.remove_track(playlist_id, tracks[0].track_key)
    assert len(manager.tracks(playlist_id)) == 1

    manager.delete(playlist_id)
    manager.delete(copy_id)
    assert manager.list_playlists() == []
    store.close()


def test_playlist_move_track(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    manager = PlaylistManager(store, tmp_path)
    playlist_id = manager.create("Lista")
    manager.add_tracks(playlist_id, [_track(0), _track(1), _track(2)])

    assert manager.move_track(playlist_id, 0, 2)
    titles = [t.title for t in manager.tracks(playlist_id)]
    assert titles == ["Título 1", "Título 2", "Título 0"]
    store.close()


def test_export_and_import_m3u(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    manager = PlaylistManager(store, tmp_path)

    # El M3U solo se importa si los ficheros existen en disco.
    song = tmp_path / "0.mp3"
    song.write_bytes(b"x")
    playlist_id = manager.create("Lista")
    manager.add_tracks(playlist_id, [_track(0, file_path=str(song))])

    export = tmp_path / "lista.m3u"
    manager.export_m3u(playlist_id, export)
    content = export.read_text(encoding="utf-8")
    assert content.startswith("#EXTM3U")
    assert "#EXTINF:180,Artista - Título 0" in content

    new_id, tracks = manager.import_m3u(export)
    assert len(tracks) == 1
    assert tracks[0].title == "Título 0"
    assert manager.get(new_id)["name"] == "lista"
    store.close()


def test_export_and_import_json(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    manager = PlaylistManager(store, tmp_path)
    playlist_id = manager.create("Lista")
    manager.add_tracks(playlist_id, [_track(0), _track(1)])

    export = tmp_path / "lista.json"
    manager.export_json(playlist_id, export)
    new_id, tracks = manager.import_json(export)
    assert len(tracks) == 2
    assert tracks[0].track_key == _track(0).track_key
    store.close()


def test_duplicate_detection_by_fingerprint(tmp_path):
    store = LocalStore(tmp_path / "state.db")
    manager = PlaylistManager(store, tmp_path)
    a = _track(0)
    b = _track(1, title="Título 0")  # mismo título/artista/duración
    groups = manager.find_duplicates([a, b, _track(2, title="Otra")])
    assert len(groups) == 1
    assert groups[0].count == 2
    store.close()


# ======================================================================
# Letras
# ======================================================================
def test_parse_lrc():
    content = "[00:12.00]Primera línea\n[00:15.50]Segunda línea\n[00:20.00]Tercera"
    lines = parse_lrc(content)
    assert len(lines) == 3
    assert lines[0].timestamp_ms == 12000
    assert lines[1].timestamp_ms == 15500
    assert lines[2].text == "Tercera"


def test_parse_lrc_ignores_garbage():
    assert parse_lrc("texto suelto\n[xx]nada") == []


def test_active_line_index():
    lines = [
        LyricLine(0, "a"),
        LyricLine(1000, "b"),
        LyricLine(2000, "c"),
    ]
    assert active_line_index(lines, 0) == 0
    assert active_line_index(lines, 1500) == 1
    assert active_line_index(lines, 5000) == 2
    assert active_line_index([], 100) == -1


# ======================================================================
# Last.fm
# ======================================================================
def test_lastfm_scrobble_rule():
    from services.lastfm_service import LastFmService

    service = LastFmService()
    # 50 % de 100 s = 50 s → se hace scrobble.
    assert service.should_scrobble(50, 100)
    assert not service.should_scrobble(49, 100)
    # La regla de los 4 minutos corta antes en pistas largas.
    assert service.should_scrobble(240, 1000)
    assert not service.should_scrobble(239, 1000)
    assert not service.should_scrobble(10, 0)


def test_lastfm_signature_is_deterministic():
    from services.lastfm_service import LastFmService

    service = LastFmService(api_key="key", api_secret="secret")
    params = {"b": "2", "a": "1", "api_key": "key"}
    assert service._sign(params) == service._sign(dict(reversed(list(params.items()))))


def test_lastfm_queue(tmp_path):
    from services.lastfm_service import LastFmService, Scrobble

    service = LastFmService(queue_path=tmp_path / "queue.json")
    service._enqueue(Scrobble(artist="A", title="T"))
    assert len(service.read_queue()) == 1
    service.flush_queue()  # sin configurar: no borra nada
    assert len(service.read_queue()) == 1
