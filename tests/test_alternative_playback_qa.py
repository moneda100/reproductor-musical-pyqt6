"""Pruebas alternativas de robustez para reproducción, slider y avance continuo.

Diseñadas para validar escenarios que van más allá del camino feliz:
1. Suscripción real a EventManager de VLC (sin fallar silenciosamente).
2. Mecanismo Watchdog/Polling cuando los callbacks nativos de libvlc se pierden o tardan.
3. Detección alternativa de fin de pista mediante inspección de tiempo y estado.
4. Descongelamiento de seek por timeout de seguridad (1.5 s).
5. Sincronización en tiempo real de la barra de progreso y cambio dinámico a la siguiente canción.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from core.player import MusicPlayer, PlayerState
from core.playlist import Track
from tests.fakes.fake_vlc import FakeVlcModule, State


def _create_track(index: int, duration: float = 120.0) -> Track:
    return Track(
        id=f"alt_t{index}",
        title=f"Canción Alternativa {index}",
        artist=f"Artista {index}",
        album="Álbum QA",
        file_path=f"/music/alt_{index}.mp3",
        duration=duration,
        source="local",
    )


# ---------------------------------------------------------------------------
# 1. Prueba de compatibilidad con EventManager nativo de VLC
# ---------------------------------------------------------------------------
def test_real_vlc_event_manager_attachment():
    """MusicPlayer se engancha correctamente al EventManager oficial de VLC."""

    player = MusicPlayer()
    # No debe haber fallado _attach_events
    assert len(player._attended_events) > 0
    # Cada elemento registrado debe ser una tupla (manager, event, handler)
    mgr, evt, handler = player._attended_events[0]
    assert hasattr(mgr, "event_attach")
    player.stop()


# ---------------------------------------------------------------------------
# 2. Prueba alternativa: Watchdog de posición cuando VLC no emite callbacks
# ---------------------------------------------------------------------------
def test_watchdog_poll_updates_position_without_vlc_callbacks():
    """Si libvlc no emite callbacks, el temporizador de sondeo actualiza la posición."""
    fake_vlc = FakeVlcModule()
    player = MusicPlayer(vlc_module=fake_vlc)

    positions = []
    player.signals.position_changed.connect(positions.append)

    # Cargar y reproducir
    player.load("/music/test.mp3")
    player.play()
    assert player.state == PlayerState.PLAYING
    assert player._poll_timer.isActive()

    # Simular que el motor VLC avanzó el tiempo interno, pero NO emitió callback
    fake_vlc.instance.players[0]._time = 15_000
    player._poll_player_state()

    assert positions == [15_000]
    assert player.get_position() == 15.0

    # Avanza más
    fake_vlc.instance.players[0]._time = 22_500
    player._poll_player_state()

    assert positions == [15_000, 22_500]
    assert player.get_position() == 22.5
    player.stop()


# ---------------------------------------------------------------------------
# 3. Prueba alternativa: Fin de pista detectado por Watchdog
# ---------------------------------------------------------------------------
def test_watchdog_detects_track_end_when_callback_is_missed():
    """El Watchdog detecta fin de pista si se pierde el evento de VLC."""
    fake_vlc = FakeVlcModule()
    player = MusicPlayer(vlc_module=fake_vlc)

    ended = []
    player.signals.track_ended.connect(lambda: ended.append(True))

    player.load("/music/test.mp3")
    player.play()
    # Fijar duración a 60 segundos
    fake_vlc.instance.players[0]._length = 60_000
    player._duration_ms = 60_000

    # Simular que el tiempo llegó al final (>= 59.7 s) y VLC se detuvo
    fake_vlc.instance.players[0]._time = 60_000
    fake_vlc.instance.players[0].state = State.Ended

    player._poll_player_state()

    assert ended == [True]
    assert player.state == PlayerState.ENDED
    player.stop()


# ---------------------------------------------------------------------------
# 4. Prueba alternativa: Seek Timeout de seguridad en PlaybackController
# ---------------------------------------------------------------------------
def test_seek_timeout_unfreezes_slider_progress():
    """El filtro de seek no congela el progreso si VLC difiere de la posición objetivo."""
    from ui.controllers.playback_controller import PlaybackController
    from ui.controllers.playlist_controller import PlaylistController

    fake_vlc = FakeVlcModule()
    playlist = PlaylistController()
    playlist.add_track(_create_track(0, duration=200.0))
    controller = PlaybackController(playlist, MusicPlayer(vlc_module=fake_vlc))

    controller.play_index(0)

    # Usuario arrastra a segundo 100
    controller.seek(100.0)
    assert controller._seeking is True
    assert controller._seek_target_ms == 100_000

    # VLC reporta segundo 90 (diferencia de 10s, mayor a 2s)
    controller._on_position_changed(90_000)
    # Mientras no venza el deadline, mantiene en pantalla el objetivo del usuario
    assert controller._seeking is True

    # Forzar vencimiento del deadline de seguridad (1.5 s)
    controller._seek_deadline = time.time() - 0.1

    emitted = []
    controller.position_changed.connect(emitted.append)
    controller._on_position_changed(92_000)

    # Debe haberse desbloqueado automáticamente
    assert controller._seeking is False
    assert controller._seek_target_ms is None
    assert emitted == [92_000]


# ---------------------------------------------------------------------------
# 5. Prueba alternativa: Formateo y Tooltip en tiempo real de minutos y horas
# ---------------------------------------------------------------------------
def test_progress_slider_tooltip_and_hour_formatting():
    """El slider y tooltip formatean con precisión minutos y horas."""
    from ui.panels.controls_panel import ControlsPanel, format_time

    panel = ControlsPanel()

    # Formato de minutos estándar
    assert format_time(125) == "2:05"
    panel.set_position(125, 300)
    assert panel.time_label.text() == "2:05"
    assert panel.duration_label.text() == "5:00"
    assert panel.slider.value() == 125
    assert panel.slider.maximum() == 300

    # Formato de pista de más de una hora (ej: set DJ de 1h 15m)
    assert format_time(4505) == "1:15:05"
    panel.set_position(4505, 5400)
    assert panel.time_label.text() == "1:15:05"
    assert panel.duration_label.text() == "1:30:00"
    assert panel.slider.maximum() == 5400
    assert panel.time_label.minimumWidth() == 60

    # Hover tooltip en ClickableSlider
    panel.slider.resize(300, 20)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(150, 10),
        QPointF(150, 10),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.slider.mouseMoveEvent(event)
    assert panel.slider.toolTip() != ""
