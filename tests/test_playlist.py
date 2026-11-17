"""Pruebas del modelo de playlist (navegación, shuffle, repeat, historial)."""

from __future__ import annotations

import json

from core.playlist import Playlist, RepeatMode, Track


def test_next_sequential(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))

    assert playlist.next().id == "track1"
    assert playlist.next().id == "track2"
    assert playlist.next() is None  # fin de lista sin repetición
    assert playlist.current_index == 2


def test_next_wraps_with_repeat_all(make_track):
    playlist = Playlist("Prueba")
    for index in range(2):
        playlist.add_track(make_track(index))
    playlist.repeat_mode = RepeatMode.ALL

    playlist.next()
    assert playlist.next().id == "track0"


def test_repeat_one_keeps_track(make_track):
    playlist = Playlist("Prueba")
    playlist.add_track(make_track(0))
    playlist.add_track(make_track(1))
    playlist.repeat_mode = RepeatMode.ONE

    assert playlist.next().id == "track0"
    assert playlist.next().id == "track0"


def test_shuffle_never_repeats_current(make_track):
    playlist = Playlist("Prueba")
    for index in range(5):
        playlist.add_track(make_track(index))
    playlist.shuffle = True

    for _ in range(20):
        previous_index = playlist.current_index
        track = playlist.next()
        assert track is not None
        assert playlist.current_index != previous_index


def test_shuffle_single_track_stays(make_track):
    playlist = Playlist("Prueba")
    playlist.add_track(make_track(0))
    playlist.shuffle = True
    assert playlist.next().id == "track0"


def test_previous_uses_history(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))

    playlist.next()
    playlist.next()
    assert playlist.current_index == 2
    assert playlist.previous().id == "track1"
    assert playlist.previous().id == "track0"


def test_previous_at_start_without_repeat(make_track):
    playlist = Playlist("Prueba")
    for index in range(2):
        playlist.add_track(make_track(index))
    assert playlist.previous() is None


def test_previous_wraps_with_repeat_all(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))
    playlist.repeat_mode = RepeatMode.ALL
    assert playlist.previous().id == "track2"


def test_history_is_bounded(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))
    playlist.shuffle = True
    for _ in range(500):
        playlist.next()
    assert len(playlist.history) <= 200


def test_remove_track_adjusts_index(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))
    playlist.current_index = 2
    playlist.remove_track(0)
    assert playlist.current_index == 1
    assert len(playlist.tracks) == 2


def test_move_track_reorders(make_track):
    playlist = Playlist("Prueba")
    for index in range(3):
        playlist.add_track(make_track(index))
    assert playlist.move_track(0, 2)
    assert [t.id for t in playlist.tracks] == ["track1", "track2", "track0"]


def test_save_and_load_roundtrip(tmp_path, make_track):
    playlist = Playlist("Mi lista")
    playlist.add_track(make_track(0, title="Canción ñ", artist="Artista"))
    playlist.current_index = 0
    path = tmp_path / "playlist.json"
    playlist.save_to_file(str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tracks"][0]["title"] == "Canción ñ"

    loaded = Playlist.load_from_file(str(path))
    assert loaded.name == "Mi lista"
    assert loaded.tracks[0].title == "Canción ñ"
    assert loaded.tracks[0].track_key == playlist.tracks[0].track_key


def test_load_from_file_tolerates_missing_fields(tmp_path):
    path = tmp_path / "playlist.json"
    path.write_text(
        json.dumps({"name": "X", "tracks": [{"title": "Solo título"}]}), encoding="utf-8"
    )
    playlist = Playlist.load_from_file(str(path))
    assert playlist.tracks[0].title == "Solo título"
    assert playlist.tracks[0].file_path == ""


def test_track_key_youtube():
    track = Track(
        id="abc123",
        title="T",
        artist="A",
        album="",
        file_path="",
        duration=1,
        source="youtube",
    )
    assert track.track_key == "yt:abc123"


def test_track_key_local_is_fingerprint():
    track = Track(
        id="x.mp3",
        title="Canción",
        artist="Artista",
        album="",
        file_path="C:/a/x.mp3",
        duration=180.0,
        source="local",
    )
    other = Track(
        id="y.mp3",
        title="Canción",
        artist="Artista",
        album="",
        file_path="D:/b/y.mp3",
        duration=180.4,
        source="local",
    )
    assert track.track_key == other.track_key
