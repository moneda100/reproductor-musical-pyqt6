"""Pruebas del reproductor con el doble de VLC."""

from __future__ import annotations

from core.player import MusicPlayer, PlayerState
from tests.fakes.fake_vlc import EventType, State


def test_player_initialises(fake_vlc):
    player = MusicPlayer(vlc_module=fake_vlc)
    assert player.state == PlayerState.STOPPED
    assert player.get_state() == PlayerState.STOPPED


def test_play_without_media_returns_false(player):
    assert player.play() is False


def test_play_loads_and_reports_state(player, fake_vlc):
    assert player.load("/music/song.mp3") is True
    assert player.play() is True
    assert player.get_state() == PlayerState.PLAYING


def test_pause_when_stopped_does_not_change_state(player):
    """Regresión: antes ``pause()`` marcaba PAUSED estando parado."""
    player.load("/music/song.mp3")
    player.pause()
    assert player.get_state() == PlayerState.STOPPED
    assert player.state != PlayerState.PAUSED


def test_pause_and_resume(player):
    player.load("/music/song.mp3")
    player.play()
    player.pause()
    assert player.get_state() == PlayerState.PAUSED
    player.resume()
    assert player.get_state() == PlayerState.PLAYING


def test_stop_resets_state(player):
    player.load("/music/song.mp3")
    player.play()
    player.stop()
    assert player.get_state() == PlayerState.STOPPED


def test_set_position_and_get_position(player, fake_vlc):
    player.load("/music/song.mp3")
    player.set_position(42.5)
    assert player.get_position() == pytest_approx(42.5)


def pytest_approx(value, tolerance=0.001):
    class _Approx:
        def __eq__(self, other):
            return abs(other - value) <= tolerance

        def __repr__(self):
            return f"≈ {value}"

    return _Approx()


def test_vlc_playing_event_updates_state(player, fake_vlc):
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].state = State.Playing
    fake_vlc.instance.players[0].event_manager().emit(EventType.MediaPlayerPlaying)
    assert player.state == PlayerState.PLAYING


def test_end_reached_emits_track_ended(player, fake_vlc):
    received = []
    player.register_callback("track_ended", lambda: received.append(True))
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].end_reached()
    assert received == [True]
    assert player.state == PlayerState.ENDED


def test_time_changed_event_emits_position(player, fake_vlc):
    positions = []
    player.register_callback("position_changed", positions.append)
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].advance(1500)
    assert positions == [1500]


def test_length_changed_event_emits_duration(player, fake_vlc):
    durations = []
    player.register_callback("duration_changed", durations.append)
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].set_length(210_000)
    assert durations == [210_000]


def test_error_event_emits_error(player, fake_vlc):
    errors = []
    player.register_callback("error", errors.append)
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].encountered_error()
    assert errors and "VLC" in errors[0]


def test_set_video_widget_windows(player, fake_vlc):
    player.set_video_widget(1234)
    assert fake_vlc.instance.players[0].hwnd == 1234


def test_set_volume_clamps(player, fake_vlc):
    player.set_volume(2.0)
    assert player.volume == 1.0
    player.set_volume(-1.0)
    assert player.volume == 0.0
    player.set_volume(0.5)
    assert fake_vlc.instance.players[0].audio_get_volume() == 50


def test_unregister_callback(player):
    calls = []

    def handler(state):
        calls.append(state)

    player.register_callback("state_changed", handler)
    player.unregister_callback("state_changed", handler)
    player._set_state(PlayerState.PLAYING)
    assert calls == []


def test_set_position_with_negative_value(player, fake_vlc):
    """set_position con valor negativo no debe crashear."""
    player.load("/music/song.mp3")
    player.set_position(-5.0)
    assert player.get_position() == 0.0


def test_set_position_with_nan(player, fake_vlc):
    """set_position con NaN no debe crashear."""
    import math

    player.load("/music/song.mp3")
    player.set_position(math.nan)
    assert player.get_position() == 0.0


def test_get_position_returns_cached_value(player, fake_vlc):
    """get_position debe retornar el valor cacheado."""
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].advance(5000)
    assert player.get_position() == pytest_approx(5.0)


def test_load_empty_source_returns_false(player):
    """load con fuente vacía debe retornar False."""
    assert player.load("") is False


def test_load_none_source_returns_false(player):
    """load con None debe retornar False."""
    assert player.load(None) is False


def test_seek_during_paused_state(player, fake_vlc):
    """Seek durante pausa debe funcionar."""
    player.load("/music/song.mp3")
    player.play()
    player.pause()
    player.set_position(30.0)
    assert player.get_position() == pytest_approx(30.0)


def test_volume_clamping(player, fake_vlc):
    """El volumen se clampea entre 0 y 1."""
    player.set_volume(1.5)
    assert player.volume == 1.0
    player.set_volume(-0.5)
    assert player.volume == 0.0


def test_load_clears_pending_seek_from_previous_media(player, fake_vlc):
    """Un seek pendiente no debe descartar el progreso del medio siguiente."""
    player.load("/music/one.mp3")
    player.play()
    player.set_position(170.0)
    assert player._pending_seek_ms == 170_000

    player.load("/music/two.mp3")
    player.play()
    assert player._pending_seek_ms is None

    positions = []
    player.register_callback("position_changed", positions.append)
    fake_vlc.instance.players[0].advance(5_000)

    assert positions == [5_000]
