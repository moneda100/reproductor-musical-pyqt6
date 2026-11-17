"""Pruebas del mapeo de identidad de pistas (fingerprints)."""

from __future__ import annotations

from core.mapper import (
    local_fingerprint,
    local_track_key,
    normalize_text,
    round_duration,
    track_key_for,
    youtube_track_key,
)


def test_normalize_removes_accents_and_punctuation():
    assert normalize_text("Café Tacvba!") == "cafe tacvba"
    assert normalize_text("  MÚLTIPLE   Espacios ") == "multiple espacios"


def test_normalize_is_case_insensitive():
    assert normalize_text("UPPER lower") == normalize_text("upper LOWER")


def test_normalize_handles_none():
    assert normalize_text(None) == ""


def test_round_duration():
    assert round_duration(180.4) == 180
    assert round_duration(180.6) == 181
    assert round_duration(None) == 0


def test_fingerprint_is_stable_across_variations():
    a = local_fingerprint("Café Tacvba", "Kaseba", 180.0)
    b = local_fingerprint("CAFE  TACVBA", "kaseba!", 180.4)
    assert a == b


def test_fingerprint_differs_for_different_tracks():
    a = local_fingerprint("Canción A", "Artista", 180.0)
    b = local_fingerprint("Canción B", "Artista", 180.0)
    assert a != b


def test_track_key_prefixes():
    assert local_track_key("a", "b", 1).startswith("local:")
    assert youtube_track_key("xyz") == "yt:xyz"


def test_track_key_for_dict_and_object():
    from core.playlist import Track

    track = Track(
        id="vid1",
        title="T",
        artist="A",
        album="",
        file_path="",
        duration=10,
        source="youtube",
    )
    assert track_key_for(track) == "yt:vid1"
    assert (
        track_key_for(
            {"source": "youtube", "id": "vid1", "title": "T", "artist": "A", "duration": 10}
        )
        == "yt:vid1"
    )
