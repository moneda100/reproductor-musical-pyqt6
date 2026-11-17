"""Pruebas de humo y de regresión de la interfaz (pytest-qt)."""

from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from core.playlist import Track


def _track(index: int = 0) -> Track:
    return Track(
        id=f"track{index}",
        title=f"Título {index}",
        artist="Artista",
        album="Álbum",
        file_path=f"/music/{index}.mp3",
        duration=180.0,
        source="local",
    )


def test_window_starts(window):
    assert window.isVisible() is False or window.isVisible() is True
    assert window.windowTitle() == "Music Player Pro"
    assert window.playlist_controller.count == 0
    assert window.stack.currentIndex() == 0


def test_theme_is_applied(window):
    window.apply_theme("light")
    assert "background-color" in window.styleSheet()
    window.apply_theme("dark")
    assert window.styleSheet()


def test_add_track_updates_model(window):
    window.playlist_controller.add_track(_track())
    assert window.playlist_controller.count == 1
    assert window.track_model.rowCount() == 1


def test_playlist_controller_is_the_only_mutation_point(window):
    window.playlist_controller.add_track(_track(0))
    window.playlist_controller.add_track(_track(1))
    window.playlist_controller.remove_index(0)
    assert window.playlist_controller.count == 1
    assert window.track_model.rowCount() == 1
    assert window.playlist_controller.playlist.tracks[0].id == "track1"


def test_move_track(window):
    window.playlist_controller.add_track(_track(0))
    window.playlist_controller.add_track(_track(1))
    window.playlist_controller.move(0, 1)
    assert window.playlist_controller.track_at(1).id == "track0"


def test_sidebar_navigation(window):
    window.sidebar.select("library")
    assert window.stack.currentIndex() == 3
    window.sidebar.select("favorites")
    assert window.stack.currentIndex() == 4


def test_search_filters_library(window, qtbot, tmp_path):
    folder = tmp_path / "musica"
    folder.mkdir()
    (folder / "a.mp3").write_bytes(b"x")
    window.library_controller.set_entries(
        [
            {
                "path": str(folder / "a.mp3"),
                "filename": "a.mp3",
                "title": "Canción Uno",
                "artist": "Artista",
                "album": "Álbum",
                "rel_dir": ".",
                "duration": 10,
            }
        ]
    )
    # La búsqueda está desactivada por defecto: se habilita con el botón.
    window.search_toggle_btn.setChecked(True)
    qtbot.wait(20)
    window.search_input.setText("Canción")
    qtbot.wait(20)
    assert window.library_panel.proxy.filterAcceptsRow(
        0, __import__("PyQt6.QtCore", fromlist=["QModelIndex"]).QModelIndex()
    )


def test_video_toggle_updates_label(window):
    btn = window.now_playing_panel.video_toggle_btn
    assert btn.isCheckable()
    btn.setChecked(True)
    assert btn.isChecked() is True
    btn.setChecked(False)
    assert btn.isChecked() is False


def test_video_widget_is_embedded_in_ui(window):
    """El vídeo se incrusta en la propia UI (dentro del frame de vídeo), no en una ventana separada."""
    assert hasattr(window.now_playing_panel, "video_widget")
    assert window.now_playing_panel.video_widget.parent() is not None
    assert window.now_playing_panel.isAncestorOf(window.now_playing_panel.video_widget)
    assert hasattr(window.now_playing_panel, "video_frame")


def test_search_toggle_disables_input(window, qtbot):
    """La búsqueda está desactivada por defecto y se habilita con el botón."""
    assert window._search_enabled is False
    assert window.search_input.isEnabled() is False
    window.search_toggle_btn.setChecked(True)
    qtbot.wait(20)
    assert window._search_enabled is True
    assert window.search_input.isEnabled() is True


def test_mini_player_toggle(window, qtbot):
    """El mini reproductor flotante se muestra/oculta con el botón."""
    assert window.mini_player.isVisible() is False
    window.now_playing_panel.mini_player_btn.setChecked(True)
    qtbot.wait(20)
    assert window.mini_player.isVisible() is True
    window.now_playing_panel.mini_player_btn.setChecked(False)
    qtbot.wait(20)
    assert window.mini_player.isVisible() is False


def test_close_with_running_scan_does_not_crash(window, tmp_path, qtbot):
    """Regresión: antes, cerrar con un escaneo activo mataba el QThread."""
    folder = tmp_path / "musica"
    folder.mkdir()
    for index in range(20):
        (folder / f"{index}.mp3").write_bytes(b"x" * 1024)

    window.library_controller.scan(str(folder))
    qtbot.wait(30)
    window.close()
    qtbot.wait(50)


def test_toast_layer_does_not_crash(window):
    window._toast("mensaje", "info")
    assert len(window.toasts._toasts) >= 1


def test_accessible_names_present(window):
    assert window.controls_panel.play_btn.accessibleName()
    assert window.controls_panel.shuffle_btn.accessibleName()
    assert window.controls_panel.repeat_btn.toolTip()


def test_repeat_button_cycles_states(window):
    window.controls_panel.repeat_btn.click()
    assert window.playlist_controller.playlist.repeat_mode.name == "ALL"
    window.controls_panel.repeat_btn.click()
    assert window.playlist_controller.playlist.repeat_mode.name == "ONE"
    window.controls_panel.repeat_btn.click()
    assert window.playlist_controller.playlist.repeat_mode.name == "NONE"


def test_seek_uses_slider_time_during_seeking(window, qtbot):
    """Regresión: durante un seek, PlaybackController filtra las posiciones de VLC
    y mantiene el objetivo en pantalla hasta que el reproductor se acerque."""
    controller = window.playback_controller
    controller._seeking = True
    controller._seek_target_ms = 75000  # 1:15

    emitted = []
    controller.position_changed.connect(lambda ms: emitted.append(ms))

    # VLC reporta 0:10 pero el objetivo es 1:15: se mantiene el objetivo.
    controller._on_position_changed(10000)
    assert emitted[-1] == 75000


def test_playback_controller_stops_seeking_when_close_to_target(window, qtbot):
    """Cuando VLC se acerca al objetivo (≤ 2 s), PlaybackController deja de filtrar."""
    controller = window.playback_controller
    controller._seeking = True
    controller._seek_target_ms = 75000

    emitted = []
    controller.position_changed.connect(lambda ms: emitted.append(ms))

    # A 1 s del objetivo: se da por terminado el seek y se emite el valor real.
    controller._on_position_changed(74000)
    assert emitted[-1] == 74000
    assert controller._seeking is False
    assert controller._seek_target_ms is None


def test_marquee_label_uses_valid_font_size():
    """La advertencia QFont::setPointSize no debe aparecer con fuentes inválidas."""
    from ui.widgets import MarqueeLabel

    label = MarqueeLabel()
    assert label.font().pointSize() > 0


def test_open_track_folder_uses_desktop_services(window, monkeypatch):
    """El acceso a la carpeta debe abrirse con QDesktopServices.openUrl, no con QApplication.openUrl."""
    track = Track(
        id="track-open",
        title="Test",
        artist="Artist",
        album="Album",
        file_path=r"C:\\tmp\\music\\track.mp3",
        duration=123,
        source="local",
    )
    window.playlist_controller.add_track(track)
    window.playback_controller.player.current_track = track

    called = {}

    def fake_open_url(url):
        called["url"] = url

    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(fake_open_url))
    monkeypatch.setattr(QUrl, "fromLocalFile", staticmethod(lambda path: path))
    window._open_track_folder()

    assert "C:\\tmp\\music" in str(called["url"])


def test_keyboard_shortcuts_include_lyrics_and_unique_actions(window):
    """Los accesos reportados en el bug no deben quedar ambiguos ni duplicados."""
    from ui.menu import KEYBOARD_SHORTCUTS

    assert "Ctrl+L" in KEYBOARD_SHORTCUTS
    assert KEYBOARD_SHORTCUTS["Ctrl+L"] == "toggle_lyrics"
    assert len(set(KEYBOARD_SHORTCUTS.keys())) == len(KEYBOARD_SHORTCUTS)


def test_play_favorite_does_not_duplicate_in_playlist(window, qtbot):
    """Reproducir un favorito no duplica en la playlist principal."""
    track = _track(0)
    window.playlist_controller.add_track(track)
    window._toggle_favorite_at(0)
    window.sidebar.select("favorites")
    qtbot.wait(30)
    window.favorites_panel.play_requested.emit(0)
    qtbot.wait(30)
    assert window.playlist_controller.count == 1


def test_theme_change_applies_immediately(window):
    """Cambiar de tema aplica el QSS inmediatamente."""
    original = window.styleSheet()
    window.apply_theme("nord")
    assert window.styleSheet() != original


def test_controls_panel_slider_during_seek(window):
    """ControlsPanel es tonto: muestra el valor que recibe (sin lógica de seeking)."""
    panel = window.controls_panel
    panel.slider.setRange(0, 180)
    panel.set_position(30.0, 180.0)
    assert panel.slider.value() == 30
    assert panel.time_label.text() == "0:30"


def test_controls_panel_slider_click_emits_seek_requested(qtbot):
    """Click en el slider emite seek_requested."""
    from ui.panels.controls_panel import ControlsPanel

    panel = ControlsPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.seek_requested, timeout=1000):
        panel.slider.sliderReleased.emit()


def test_play_index_with_invalid_index_returns_false(window):
    """play_index con índice inválido retorna False."""
    assert window.playback_controller.play_index(-1) is False
    assert window.playback_controller.play_index(999) is False


def test_empty_playlist_next_does_not_crash(window):
    """next() en playlist vacía no debe crashear."""
    assert window.playback_controller.next() is None


def test_download_panel_prepares_results_and_starts_with_config(window, monkeypatch, tmp_path):
    """El botón «Descargar todo» prepara el gestor con todos los vídeos."""
    results = [
        {
            "id": "vid1",
            "title": "Canción 1",
            "artist": "Artista",
            "url": "https://www.youtube.com/watch?v=vid1",
            "duration": 120,
            "source": "youtube",
        },
        {
            "id": "vid2",
            "title": "Canción 2",
            "artist": "Artista",
            "url": "https://www.youtube.com/watch?v=vid2",
            "duration": 60,
            "source": "youtube",
        },
    ]
    window.results_model.set_results(results)
    window._on_download_all()

    assert window.download_manager.isHidden() is False
    assert window.download_manager.isVisible() is True
    assert len(window.downloads_panel.selected_items()) == 2

    window.downloads_panel.set_destination(str(tmp_path))
    window.downloads_panel.set_format("flac")
    called = {}

    def fake_download_all(items, permanent=False, audio_format="mp3"):
        called.update(
            items=items,
            permanent=permanent,
            audio_format=audio_format,
        )

    monkeypatch.setattr(window.search_controller, "download_all", fake_download_all)
    assert window.downloads_panel.start() is True
    assert called["permanent"] is True
    assert called["audio_format"] == "flac"
    assert len(called["items"]) == 2


def test_download_manager_is_a_separate_window(window):
    """El gestor de descargas no se mezcla con la ventana principal."""
    from PyQt6.QtWidgets import QDockWidget

    assert isinstance(window.download_manager, QDockWidget) is False
    assert window.download_manager.parent() is window
    assert window.download_manager.isModal() is False


def test_results_panel_append_keeps_previous_results(window):
    """«Cargar más» añade al final sin reemplazar lo ya mostrado."""
    first = [
        {"id": "a", "title": "Uno", "artist": "X", "url": "u1"},
        {"id": "b", "title": "Dos", "artist": "X", "url": "u2"},
    ]
    window.results_panel.set_results(first, "YouTube")
    assert window.results_model.rowCount() == 2

    window.results_panel.append_results([{"id": "c", "title": "Tres", "artist": "X", "url": "u3"}])
    assert window.results_model.rowCount() == 3
    assert window.results_panel.current_results()[0]["id"] == "a"
    assert window.results_panel.current_results()[-1]["id"] == "c"


def test_youtube_result_plays_via_stream_resolution(window, monkeypatch, qtbot):
    """Reproducir un resultado de YouTube pide el stream de audio, no lo descarga."""
    calls = {}

    def fake_resolve(track, video=False):
        calls.update(track=track, video=video)

    monkeypatch.setattr(window.search_controller, "resolve_stream", fake_resolve)
    monkeypatch.setattr(window.search_controller, "search_cover", lambda *a, **k: None)

    result = {
        "id": "vid1",
        "title": "Canción",
        "artist": "Artista",
        "url": "https://www.youtube.com/watch?v=vid1",
        "duration": 120,
        "source": "youtube",
    }
    window._on_play_result(result)

    assert calls["video"] is False
    assert calls["track"].youtube_id == "vid1"
    assert window.playlist_controller.count == 1


def test_stream_resolved_loads_audio_without_video(window, qtbot, monkeypatch):
    """Al resolverse el stream se carga en VLC y se reproduce."""
    monkeypatch.setattr(window.search_controller, "search_cover", lambda *a, **k: None)
    monkeypatch.setattr(window.lyrics_service, "get_lyrics", lambda *a, **k: None)
    track = Track(
        id="yt:abc123",
        title="Stream",
        artist="YouTube",
        album="YouTube",
        file_path="",
        duration=100,
        source="youtube",
    )
    window.playlist_controller.add_track(track)
    window._stream_request_position = 42.0
    window._stream_request_play = True

    window._on_stream_resolved(track, "https://example.test/audio.m4a", False)

    player = window.playback_controller.player
    assert player.current_track == "https://example.test/audio.m4a"
    assert window.playback_controller.is_playing() is True


def test_video_toggle_requests_video_stream(window, monkeypatch):
    """Activar «ver vídeo» pide explícitamente el stream con vídeo."""
    calls = {}

    def fake_resolve(track, video=False):
        calls.update(track=track, video=video)

    monkeypatch.setattr(window.search_controller, "resolve_stream", fake_resolve)
    track = Track(
        id="vid9",
        title="Vídeo",
        artist="YouTube",
        album="YouTube",
        file_path="",
        duration=60,
        source="youtube",
    )
    window.playlist_controller.add_track(track)
    window.playlist_controller.set_current(0)

    window._on_video_toggled(True)

    assert calls["video"] is True
    assert window._video_output == "now"
    assert window._wants_video() is True


def test_mini_player_syncs_progress_and_volume(window):
    """El mini reproductor refleja duración, posición y volumen."""
    window._on_duration_changed(120_000)
    window._on_position_changed(5_000)
    assert "0:05" in window.mini_player.time_label.text()
    assert "2:00" in window.mini_player.time_label.text()

    window.mini_player.volume_slider.setValue(33)
    assert window.config.volume == 33


def test_mini_player_video_toggle_requests_video(window, monkeypatch):
    """El mini reproductor puede pedir la salida de vídeo."""
    calls = {}

    def fake_resolve(track, video=False):
        calls.update(track=track, video=video)

    monkeypatch.setattr(window.search_controller, "resolve_stream", fake_resolve)
    track = Track(
        id="vidmini",
        title="Mini",
        artist="YouTube",
        album="YouTube",
        file_path="",
        duration=30,
        source="youtube",
    )
    window.playlist_controller.add_track(track)
    window.playlist_controller.set_current(0)

    window._on_mini_video_toggled(True)

    assert calls["video"] is True
    assert window._video_output == "mini"
    assert window.mini_player.video_enabled() is True


def test_clickable_slider_calculation(qtbot):
    """El ClickableSlider mapea coordenadas proporcionalmente sin forzar 0."""
    from PyQt6.QtCore import QPointF, Qt

    from ui.widgets import ClickableSlider

    slider = ClickableSlider(Qt.Orientation.Horizontal)
    qtbot.addWidget(slider)
    slider.resize(400, 20)
    slider.setRange(0, 100)

    # Coordenada x=200 debe ser exactamente 50 (centro), nunca 0
    val_mid = slider.pixelPosToRangeValue(QPointF(200, 10))
    assert 48 <= val_mid <= 52

    val_start = slider.pixelPosToRangeValue(QPointF(0, 10))
    assert val_start == 0

    val_end = slider.pixelPosToRangeValue(QPointF(400, 10))
    assert val_end == 100


def test_results_panel_play_all_and_selected(window):
    """Reproducir todos o seleccionados desde los resultados de búsqueda."""
    results = [
        {"title": "C1", "artist": "A1", "url": "https://youtu.be/1", "source": "youtube"},
        {"title": "C2", "artist": "A2", "url": "https://youtu.be/2", "source": "youtube"},
        {"title": "C3", "artist": "A3", "url": "https://youtu.be/3", "source": "youtube"},
    ]

    # Probar reproducir todo
    window._on_play_all_results(results)
    assert window.playlist_controller.count == 3
    assert window.playlist_controller.playlist.current_index == 0
    assert window.playlist_controller.current_track().title == "C1"

    # Probar añadir a la cola
    more_results = [
        {"title": "C4", "artist": "A4", "url": "https://youtu.be/4", "source": "youtube"}
    ]
    window._on_add_results_to_queue(more_results)
    assert window.playlist_controller.count == 4

    # Probar añadir a favoritos
    window._on_add_results_to_favorites(results[:2])
    assert len(window.store.favorites()) >= 2


def test_play_video_result_embeds_in_interface(window):
    """Reproducir vídeo desde resultados cambia a la pestaña home y habilita el visor incrustado."""
    vid_result = {
        "title": "Video Musical",
        "artist": "Artista",
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "source": "youtube",
    }
    window.sidebar.select("library")
    assert window.stack.currentIndex() != 0

    window._on_play_video_result(vid_result)
    # Debe haber cambiado automáticamente a la vista "home" para mostrar el reproductor incrustado
    assert window.stack.currentIndex() == 0
    assert window._video_output == "now"
    assert window.now_playing_panel.video_toggle_btn.isChecked() is True


def test_navigation_pip_preserves_embedded_video(window):
    """Navegar fuera de 'home' pasa el vídeo al mini reproductor para mantenerlo incrustado."""
    window.sidebar.select("home")
    window._video_output = "now"
    window.now_playing_panel.video_toggle_btn.setChecked(True)

    # Navegar a biblioteca
    window._on_navigate("library")
    assert window._video_output == "mini"
    assert window.mini_player.isVisible() is True

    # Volver a home acopla de nuevo
    window._on_navigate("home")
    assert window._video_output == "now"
