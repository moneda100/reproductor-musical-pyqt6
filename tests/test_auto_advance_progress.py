"""Pruebas de avance automático y de la barra de progreso.

Cubren el camino completo:

``VLC MediaPlayerEndReached`` → ``MusicPlayer.track_ended`` →
``PlaybackController._on_track_ended`` → ``Playlist.next()`` → carga y
reproducción de la pista siguiente, además de la sincronización del slider y
las etiquetas de tiempo con los eventos de posición/duración de VLC.
"""

from __future__ import annotations

import pytest

from core.player import PlayerState
from core.playlist import RepeatMode, Track
from tests.fakes.fake_vlc import FakeVlcModule


def _track(index: int, *, duration: float = 180.0) -> Track:
    return Track(
        id=f"track{index}",
        title=f"Título {index}",
        artist=f"Artista {index}",
        album="Álbum",
        file_path=f"/music/{index}.mp3",
        duration=duration,
        source="local",
    )


def _add_tracks(playlist_controller, count: int = 3) -> None:
    for index in range(count):
        playlist_controller.add_track(_track(index, duration=180.0 + index))


@pytest.fixture
def playback():
    """Controlador de reproducción aislado con VLC simulado."""
    from core.player import MusicPlayer
    from ui.controllers.playback_controller import PlaybackController
    from ui.controllers.playlist_controller import PlaylistController

    fake_vlc = FakeVlcModule()
    playlist_controller = PlaylistController()
    controller = PlaybackController(
        playlist_controller, MusicPlayer(vlc_module=fake_vlc)
    )
    return controller, playlist_controller, fake_vlc


@pytest.fixture
def ui_window(qtbot, monkeypatch):
    """Ventana principal aislada; devuelve también el doble de VLC."""
    from core.player import MusicPlayer
    from ui.main_window import MainWindow

    fake_vlc = FakeVlcModule()
    win = MainWindow(player=MusicPlayer(vlc_module=fake_vlc))
    qtbot.addWidget(win)
    # La suite no debe tocar la red.
    monkeypatch.setattr(win.lyrics_service, "get_lyrics", lambda *a, **k: None)
    monkeypatch.setattr(win.search_controller, "search_cover", lambda *a, **k: None)
    win.resize(1000, 700)
    yield win, fake_vlc
    win.close()


# ---------------------------------------------------------------------------
# Avance automático (nivel controlador)
# ---------------------------------------------------------------------------
def test_end_of_track_auto_advances_and_plays_next(playback):
    """Al terminar la pista, se carga y reproduce la siguiente automáticamente."""
    controller, playlist, fake_vlc = playback
    _add_tracks(playlist, 3)
    assert controller.play_index(0) is True
    assert controller.state == PlayerState.PLAYING

    changed = []
    controller.track_changed.connect(lambda track: changed.append(track.title))

    fake_vlc.instance.players[0].end_reached()

    assert playlist.playlist.current_index == 1
    assert playlist.current_track().title == "Título 1"
    assert changed == ["Título 1"]
    assert controller.state == PlayerState.PLAYING
    # VLC recibió la ruta de la segunda pista y volvió a arrancar.
    assert fake_vlc.instance.players[0].media.source.endswith("1.mp3")
    assert fake_vlc.instance.players[0].play_calls == 2


def test_end_of_last_track_emits_playlist_finished(playback):
    """Sin repeat, el fin de la última pista no carga otra y avisa del final."""
    controller, playlist, fake_vlc = playback
    _add_tracks(playlist, 2)
    assert controller.play_index(1) is True
    player = fake_vlc.instance.players[0]
    play_calls_before = player.play_calls

    finished = []
    changed = []
    controller.playlist_finished.connect(lambda: finished.append(True))
    controller.track_changed.connect(lambda track: changed.append(track.title))

    player.end_reached()

    assert finished == [True]
    assert changed == []
    assert playlist.playlist.current_index == 1
    assert controller.state == PlayerState.ENDED
    assert player.play_calls == play_calls_before


def test_repeat_all_wraps_to_first_track_on_end(playback):
    """Con repetición de toda la lista, la última pista vuelve a la primera."""
    controller, playlist, fake_vlc = playback
    _add_tracks(playlist, 2)
    playlist.playlist.repeat_mode = RepeatMode.ALL
    assert controller.play_index(1) is True

    fake_vlc.instance.players[0].end_reached()

    assert playlist.playlist.current_index == 0
    assert playlist.current_track().title == "Título 0"
    assert controller.state == PlayerState.PLAYING


def test_repeat_one_replays_same_track_on_end(playback):
    """Con repetición de una pista, el fin recarga la misma pista."""
    controller, playlist, fake_vlc = playback
    _add_tracks(playlist, 2)
    playlist.playlist.repeat_mode = RepeatMode.ONE
    assert controller.play_index(0) is True
    player = fake_vlc.instance.players[0]

    player.end_reached()

    assert playlist.playlist.current_index == 0
    assert playlist.current_track().title == "Título 0"
    assert controller.state == PlayerState.PLAYING
    assert player.play_calls == 2


def test_auto_advance_clears_pending_seek_from_previous_track(playback):
    """Un seek pendiente no debe congelar el progreso de la pista siguiente.

    Regresión: si la pista termina antes de que VLC alcance el objetivo del
    seek, el objetivo antiguo se filtraba en la pista nueva y el slider se
    quedaba clavado en el minuto del seek anterior.
    """
    controller, playlist, fake_vlc = playback
    _add_tracks(playlist, 2)
    assert controller.play_index(0) is True

    controller.seek(170.0)
    assert controller._seeking is True

    # La pista termina antes de que VLC llegue al objetivo del seek.
    fake_vlc.instance.players[0].end_reached()

    emitted = []
    controller.position_changed.connect(emitted.append)
    fake_vlc.instance.players[0].advance(5_000)

    assert playlist.playlist.current_index == 1
    assert emitted == [5_000]
    assert controller._seeking is False
    assert controller._seek_target_ms is None


def test_manual_next_at_end_of_list_does_not_emit_finished(playback):
    """El botón «siguiente» al final no debe confundirse con el fin automático."""
    controller, playlist, _fake_vlc = playback
    _add_tracks(playlist, 2)
    assert controller.play_index(1) is True

    finished = []
    controller.playlist_finished.connect(lambda: finished.append(True))

    assert controller.next() is None
    assert finished == []


# ---------------------------------------------------------------------------
# Barra de progreso (nivel UI)
# ---------------------------------------------------------------------------
def test_progress_slider_tracks_minute_and_duration(ui_window):
    """El slider y las etiquetas reflejan el minuto actual y la duración."""
    win, fake_vlc = ui_window
    _add_tracks(win.playlist_controller, 2)
    assert win.playback_controller.play_index(0) is True

    panel = win.controls_panel
    assert panel.slider.maximum() == 180
    assert panel.duration_label.text() == "3:00"

    fake_vlc.instance.players[0].advance(65_000)

    assert panel.time_label.text() == "1:05"
    assert panel.slider.value() == 65
    assert panel.slider.maximum() == 180

    fake_vlc.instance.players[0].advance(35_000)

    assert panel.time_label.text() == "1:40"
    assert panel.slider.value() == 100


def test_slider_reaches_end_then_next_song_resets_progress(ui_window):
    """Al llegar al final, el slider marca el máximo y el avance lo reinicia."""
    win, fake_vlc = ui_window
    _add_tracks(win.playlist_controller, 2)
    assert win.playback_controller.play_index(0) is True

    panel = win.controls_panel
    player = fake_vlc.instance.players[0]

    player.advance(180_000)

    # La canción está al final: el slider llega al tope y el tiempo coincide.
    assert panel.slider.maximum() == 180
    assert panel.slider.value() == panel.slider.maximum()
    assert panel.time_label.text() == "3:00"

    player.end_reached()

    # Avance automático: nueva pista, estado reproduciendo y progreso a cero.
    assert win.playlist_controller.playlist.current_index == 1
    assert win.now_playing_panel.title_label.text() == "Título 1"
    assert win.playback_controller.state == PlayerState.PLAYING
    assert panel.slider.maximum() == 181
    assert panel.slider.value() == 0
    assert panel.time_label.text() == "0:00"
    assert panel.duration_label.text() == "3:01"


def test_ui_pending_seek_does_not_freeze_next_track_progress(ui_window):
    """El slider de la pista nueva arranca en 0 aunque hubiera un seek pendiente."""
    win, fake_vlc = ui_window
    _add_tracks(win.playlist_controller, 2)
    assert win.playback_controller.play_index(0) is True

    panel = win.controls_panel
    win.playback_controller.seek(170.0)
    assert panel.slider.value() == 170

    player = fake_vlc.instance.players[0]
    player.end_reached()

    assert win.playlist_controller.playlist.current_index == 1
    assert panel.slider.value() == 0

    player.advance(7_000)

    assert panel.time_label.text() == "0:07"
    assert panel.slider.value() == 7


def test_vlc_duration_after_auto_advance_updates_slider_range(ui_window):
    """Si la pista siguiente no trae duración, VLC la fija al informar length."""
    win, fake_vlc = ui_window
    win.playlist_controller.add_track(_track(0, duration=0.0))
    win.playlist_controller.add_track(_track(1, duration=0.0))
    assert win.playback_controller.play_index(0) is True

    panel = win.controls_panel
    player = fake_vlc.instance.players[0]

    player.set_length(180_000)
    player.advance(30_000)
    assert panel.slider.maximum() == 180
    assert panel.slider.value() == 30

    player.end_reached()
    assert win.playlist_controller.playlist.current_index == 1
    assert win.playback_controller.state == PlayerState.PLAYING

    # VLC informa la duración real de la nueva pista.
    player.set_length(240_000)
    player.advance(12_000)

    assert panel.slider.maximum() == 240
    assert panel.slider.value() == 12
    assert panel.duration_label.text() == "4:00"
    assert panel.time_label.text() == "0:12"


def test_format_time_handles_minutes_and_hours():
    """format_time soporta pistas estándar y audios de más de 1 hora."""
    from ui.panels.controls_panel import format_time

    assert format_time(0) == "0:00"
    assert format_time(59) == "0:59"
    assert format_time(65) == "1:05"
    assert format_time(599) == "9:59"
    assert format_time(3600) == "1:00:00"
    assert format_time(3665) == "1:01:05"
    assert format_time(7325) == "2:02:05"
    assert format_time(-5) == "0:00"
    assert format_time("invalid") == "0:00"


def test_slider_accessibility_and_hover_tooltip(ui_window):
    """El slider tiene nombre accesible y tooltip dinámico en hover."""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    win, _ = ui_window
    _add_tracks(win.playlist_controller, 1)
    win.playback_controller.play_index(0)

    slider = win.controls_panel.slider
    assert slider.accessibleName() == "Progreso de reproducción"

    # Simular movimiento del ratón al 50 %
    slider.resize(200, 20)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100, 10),
        QPointF(100, 10),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    slider.mouseMoveEvent(event)
    assert slider.toolTip() != ""


def test_auto_advance_skips_unplayable_track(playback):
    """Si una pista intermedia falla al cargar en avance automático, salta a la siguiente."""
    controller, playlist, fake_vlc = playback
    # Pista 0 normal, pista 1 con ruta que hará fallar el load, pista 2 normal
    playlist.add_track(_track(0, duration=100.0))
    bad_track = _track(1, duration=100.0)
    bad_track.file_path = "/nonexistent/corrupt.mp3"
    playlist.add_track(bad_track)
    playlist.add_track(_track(2, duration=100.0))

    # Sobrescribir load en el reproductor simulado para que falle con corrupt.mp3
    original_load = fake_vlc.instance.players[0].set_media

    def mocked_set_media(media):
        if "corrupt.mp3" in getattr(media, "source", ""):
            raise RuntimeError("Archivo dañado")
        return original_load(media)

    fake_vlc.instance.players[0].set_media = mocked_set_media

    assert controller.play_index(0) is True
    errors = []
    controller.error_occurred.connect(errors.append)

    # Termina la pista 0
    fake_vlc.instance.players[0].end_reached()

    # Debe haber emitido error para la pista 1 y avanzado a la pista 2 automáticamente
    assert len(errors) == 1
    assert "Título 1" in errors[0]
    assert playlist.playlist.current_index == 2
    assert playlist.current_track().title == "Título 2"
    assert controller.state == PlayerState.PLAYING

