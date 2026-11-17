"""Suite QA de la interfaz: funcionalidad, usabilidad, rendimiento y regresión.

Cada prueba usa un doble de VLC y un ``MUSICPLAYERPRO_HOME`` temporal (ver
``tests/conftest.py``), por lo que no toca la configuración real ni la red.
"""

from __future__ import annotations

import re
import time
import tracemalloc

import pytest
from PyQt6.QtCore import (
    QModelIndex,
    QPoint,
    QRect,
    Qt,
    QUrl,
    qInstallMessageHandler,
)
from PyQt6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QWidget,
)

from core.lyrics import LyricLine
from core.player import PlayerState
from core.playlist import Track
from ui.main_window import VIEW_INDEX, MainWindow
from ui.models.library_tree_model import NodeKind
from ui.models.track_list_model import TrackListModel
from ui.panels.now_playing import VIDEO_MIN_SIZE, VideoSizeMode
from ui.themes import ALL_THEMES, ThemeManager
from ui.widgets import MarqueeLabel, TrackListDelegate, VideoWidget

pytestmark = pytest.mark.qa


# ---------------------------------------------------------------------------
# Utilidades y fixture
# ---------------------------------------------------------------------------
def _track(index: int = 0, **overrides) -> Track:
    payload = {
        "id": f"track{index}",
        "title": f"Título {index}",
        "artist": f"Artista {index}",
        "album": f"Álbum {index % 4}",
        "file_path": f"/music/{index}.mp3",
        "duration": 180.0 + index,
        "source": "local",
    }
    payload.update(overrides)
    return Track(**payload)


@pytest.fixture
def qa_window(qtbot, monkeypatch):
    """Ventana principal aislada y sin dependencias de red."""
    from core.player import MusicPlayer
    from tests.fakes.fake_vlc import FakeVlcModule

    win = MainWindow(player=MusicPlayer(vlc_module=FakeVlcModule()))
    qtbot.addWidget(win)
    # Evitar que las pruebas de reproducción disparen búsquedas reales.
    monkeypatch.setattr(win.lyrics_service, "get_lyrics", lambda *a, **k: None)
    monkeypatch.setattr(win.search_controller, "search_cover", lambda *a, **k: None)
    win.resize(1200, 800)
    yield win
    win.close()


def _shortcut(window: QWidget, sequence: str) -> QShortcut | None:
    expected = QKeySequence(sequence)
    for shortcut in window.findChildren(QShortcut):
        if shortcut.key() == expected:
            return shortcut
    return None


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str, background: str) -> float:
    first, second = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (first + 0.05) / (second + 0.05)


def _iter_track_indexes(model, parent: QModelIndex = QModelIndex()):
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        node = index.internalPointer()
        if node.kind == NodeKind.TRACK:
            yield index
        else:
            yield from _iter_track_indexes(model, index)


class _PixmapProvider:
    """Proveedor mínimo para probar la caché de miniaturas sin disco."""

    def __init__(self) -> None:
        self.pixmap = QPixmap(120, 120)
        self.pixmap.fill(QColor("#3355AA"))

    def cached_pixmap(self, _url: str) -> QPixmap:
        return self.pixmap


# ---------------------------------------------------------------------------
# Funcionalidad
# ---------------------------------------------------------------------------
def test_play_pause_toggles_button_and_player_state(qa_window, qtbot):
    """Reproducir/pausar actualiza el motor y el estado visible del botón."""
    qa_window.playlist_controller.add_track(_track(0))
    play = qa_window.controls_panel.play_btn

    play.click()
    qtbot.wait(20)
    assert qa_window.playback_controller.state == PlayerState.PLAYING
    assert play.accessibleName() == "Pausar"

    play.click()
    qtbot.wait(20)
    assert qa_window.playback_controller.state == PlayerState.PAUSED
    assert play.accessibleName() == "Reproducir"


def test_next_and_previous_buttons_navigate_the_playlist(qa_window, qtbot):
    """Los botones de salto cargan la pista contigua y actualizan la vista."""
    for index in range(3):
        qa_window.playlist_controller.add_track(_track(index))
    qa_window.playback_controller.play_index(0)
    qtbot.wait(20)
    assert qa_window.now_playing_panel.title_label.text() == "Título 0"

    qa_window.controls_panel.next_btn.click()
    qtbot.wait(20)
    assert qa_window.playlist_controller.playlist.current_index == 1
    assert qa_window.now_playing_panel.title_label.text() == "Título 1"

    qa_window.controls_panel.prev_btn.click()
    qtbot.wait(20)
    assert qa_window.playlist_controller.playlist.current_index == 0
    assert qa_window.now_playing_panel.title_label.text() == "Título 0"


def test_volume_slider_updates_player_config_and_mini_player(qa_window):
    """El volumen se propaga al motor, a la configuración y al mini reproductor."""
    slider = qa_window.controls_panel.volume_slider
    assert slider.accessibleName() == "Volumen"

    slider.setValue(42)
    assert qa_window.playback_controller.player.volume == pytest.approx(0.42)
    assert qa_window.config.volume == 42
    assert qa_window.mini_player.volume_slider.value() == 42


def test_timer_progress_updates_labels_and_slider(qa_window):
    """Caso clave: al reproducir, el temporizador y el slider avanzan juntos."""
    qa_window._on_duration_changed(200_000)
    qa_window._on_position_changed(65_000)

    panel = qa_window.controls_panel
    assert panel.time_label.text() == "1:05"
    assert panel.duration_label.text() == "3:20"
    assert panel.slider.maximum() == 200
    assert panel.slider.value() == 65

    qa_window._on_position_changed(0)
    assert panel.time_label.text() == "0:00"
    assert panel.slider.value() == 0


def test_lyrics_sync_highlights_the_active_line(qa_window):
    """La línea resaltada sigue la posición de reproducción."""
    lines = [
        LyricLine(timestamp_ms=0, text="Intro"),
        LyricLine(timestamp_ms=5_000, text="Primer verso"),
        LyricLine(timestamp_ms=10_000, text="Estribillo"),
    ]
    panel = qa_window.lyrics_panel
    panel.set_lyrics(lines)

    panel.set_position(6_000)
    assert panel._active_index == 1
    assert "Primer verso" in panel.text_browser.toPlainText()

    formats = {}
    block = panel.text_browser.document().firstBlock()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                formats[fragment.text()] = (
                    fmt.foreground().color().name(),
                    fmt.fontPointSize(),
                    fmt.fontWeight(),
                )
            iterator += 1
        block = block.next()

    assert formats["Primer verso"] == ("#ffffff", 18.0, 700)
    assert formats["Intro"] == ("#787878", 14.0, 400)
    assert panel.text_browser.textCursor().hasSelection() is False

    panel.set_position(12_000)
    assert panel._active_index == 2
    assert "Estribillo" in panel.text_browser.toPlainText()

    panel.set_position(1_000)
    assert panel._active_index == 0


def test_search_filters_library_by_title_artist_and_no_match(qa_window, qtbot):
    """La búsqueda global filtra por título y artista, y vacía si no hay coincidencias."""
    entries = [
        {
            "path": f"/music/{index}.mp3",
            "filename": f"{index}.mp3",
            "title": title,
            "artist": artist,
            "album": "Álbum",
            "rel_dir": ".",
            "duration": 120,
        }
        for index, (title, artist) in enumerate(
            [
                ("Canción Uno", "Artista Alfa"),
                ("Canción Dos", "Beta"),
                ("Otra Pista", "Gamma"),
            ]
        )
    ]
    qa_window.library_controller.set_entries(entries)
    qa_window.search_toggle_btn.setChecked(True)
    qtbot.wait(20)

    source_indexes = list(_iter_track_indexes(qa_window.library_panel.model))
    assert len(source_indexes) == 3

    def visible_titles() -> list[str]:
        titles = []
        for index in source_indexes:
            if qa_window.library_panel.proxy.mapFromSource(index).isValid():
                node = index.internalPointer()
                titles.append(str((node.entry or {}).get("title") or node.label))
        return titles

    qa_window.search_input.setText("alfa")
    qtbot.wait(20)
    assert visible_titles() == ["Canción Uno"]

    qa_window.search_input.setText("canción")
    qtbot.wait(20)
    assert sorted(visible_titles()) == ["Canción Dos", "Canción Uno"]

    qa_window.search_input.setText("no-existe")
    qtbot.wait(20)
    assert visible_titles() == []


def test_playlist_add_move_remove_and_clear(qa_window, monkeypatch):
    """Alta, reordenación, borrado y limpieza de la lista principal."""
    for index in range(3):
        qa_window.playlist_controller.add_track(_track(index))
    panel = qa_window.playlist_panel
    assert panel.header_label.text() == "Mi lista (3)"

    assert qa_window.playlist_controller.move(0, 2) is True
    assert [track.id for track in qa_window.playlist_controller.tracks()] == [
        "track1",
        "track2",
        "track0",
    ]

    assert qa_window.playlist_controller.remove_index(1) is True
    assert qa_window.playlist_controller.count == 2
    assert panel.header_label.text() == "Mi lista (2)"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    qa_window._clear_playlist()
    assert qa_window.playlist_controller.count == 0
    assert qa_window.track_model.rowCount() == 0
    assert panel.header_label.text() == "Mi lista (0)"


def test_playlist_context_menu_actions_reorder_and_open_folder(qa_window, monkeypatch):
    """El menú contextual ofrece acciones y sus señales llegan a la ventana."""
    for index in range(3):
        qa_window.playlist_controller.add_track(_track(index))
    qa_window.playlist_controller.set_current(0)

    panel = qa_window.playlist_panel
    view = panel.list_view
    target_index = panel.model.index(2, 0)
    monkeypatch.setattr(view, "indexAt", lambda _pos: target_index)

    opened = {}
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.setdefault("url", url)),
    )
    monkeypatch.setattr(QUrl, "fromLocalFile", staticmethod(lambda path: path))

    captured = {}

    def fake_exec(menu, *args, **kwargs):
        actions = [action for action in menu.actions() if not action.isSeparator()]
        captured["texts"] = [action.text() for action in actions]
        for action in actions:
            if "Reproducir a continuación" in action.text() or "Abrir carpeta" in action.text():
                action.trigger()
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    panel._show_context_menu(QPoint(5, 5))

    texts = captured["texts"]
    for expected in (
        "Reproducir",
        "Reproducir a continuación",
        "Alternar favorita",
        "Editar etiquetas",
        "Abrir carpeta",
        "Copiar título",
        "Copiar artista",
        "Copiar ruta",
        "Quitar de la lista",
        "Limpiar lista",
    ):
        assert any(expected in text for text in texts), expected

    assert qa_window.playlist_controller.tracks()[1].id == "track2"
    assert "music" in str(opened.get("url", ""))


def test_historial_se_registra_al_reproducir(qa_window, qtbot, monkeypatch):
    """Al cambiar de pista se añade una entrada al historial y se muestra en la vista."""
    # Evitar escrituras reales de Last.fm/scrobbling.
    monkeypatch.setattr(qa_window, "_scrobble_now_playing", lambda *a, **k: None)

    qa_window.playlist_controller.add_track(_track(0, title="Canción A"))
    qa_window.playback_controller.play_index(0)
    qtbot.wait(20)

    assert qa_window.store.is_favorite(_track(0).track_key) is False
    rows = qa_window.store.history()
    assert any(row["title"] == "Canción A" for row in rows)

    qa_window.sidebar.select("history")
    qtbot.wait(20)
    assert qa_window.history_panel.model.rowCount() >= 1
    assert qa_window.history_panel.header_label.text().startswith("Historial")


def test_historial_reproducir_quitar_y_limpiar(qa_window, qtbot, monkeypatch):
    """El historial es funcional: reproducir, eliminar entrada y vaciar todo."""
    monkeypatch.setattr(qa_window, "_scrobble_now_playing", lambda *a, **k: None)

    qa_window.playlist_controller.add_track(_track(0, title="Canción A"))
    qa_window.playlist_controller.add_track(_track(1, title="Canción B"))
    qa_window.playback_controller.play_index(0)
    qtbot.wait(20)
    qa_window.playback_controller.play_index(1)
    qtbot.wait(20)

    qa_window.sidebar.select("history")
    qtbot.wait(20)
    assert qa_window.history_panel.model.rowCount() == 2

    # Reproducir la primera entrada del historial (más reciente: "Canción B",
    # que está en el índice 1 de la playlist).
    captured = {}
    monkeypatch.setattr(
        qa_window.playback_controller,
        "play_index",
        lambda idx: captured.setdefault("idx", idx),
    )
    qa_window.history_panel.play_requested.emit(0)
    qtbot.wait(20)
    assert captured["idx"] == 1

    # La fila 0 del historial corresponde a "Canción B".
    assert qa_window.history_panel.model.track_at(0).title == "Canción B"

    # Eliminar una entrada por track_key (menú contextual "Quitar de la lista").
    track_key = qa_window.history_panel.model.track_at(0).track_key
    qa_window.store.remove_history(track_key)
    qa_window.history_panel.model.remove_row(0)
    assert qa_window.history_panel.model.rowCount() == 1
    assert not any(row["track_key"] == track_key for row in qa_window.store.history())

    # Vaciar todo el historial.
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    qa_window.history_panel.clear_requested.emit()
    qtbot.wait(20)
    assert qa_window.history_panel.model.rowCount() == 0
    assert qa_window.store.history() == []


def test_historial_alternar_favorita_y_abrir_carpeta(qa_window, qtbot, monkeypatch):
    """Desde el historial se puede alternar favorita y abrir la carpeta del archivo."""
    monkeypatch.setattr(qa_window, "_scrobble_now_playing", lambda *a, **k: None)

    track = _track(0, title="Canción Local", file_path="/music/local.mp3")
    qa_window.store.add_history(track)
    qa_window.sidebar.select("history")
    qtbot.wait(20)
    assert qa_window.history_panel.model.rowCount() == 1

    # Alternar favorita.
    qa_window.history_panel.favorite_requested.emit(0)
    qtbot.wait(20)
    assert qa_window.store.is_favorite(track.track_key) is True
    qa_window.history_panel.favorite_requested.emit(0)
    qtbot.wait(20)
    assert qa_window.store.is_favorite(track.track_key) is False

    # Abrir carpeta (ruta local válida).
    opened = {}
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.setdefault("url", url)),
    )
    monkeypatch.setattr(QUrl, "fromLocalFile", staticmethod(lambda path: path))
    qa_window.history_panel.open_folder_requested.emit(0)
    qtbot.wait(20)
    assert "music" in str(opened.get("url", ""))


# ---------------------------------------------------------------------------
# Usabilidad y accesibilidad
# ---------------------------------------------------------------------------
def test_key_controls_expose_accessible_names(qa_window):
    """Los controles principales se pueden identificar con lector de pantalla."""
    controls = qa_window.controls_panel
    for button in (
        controls.play_btn,
        controls.prev_btn,
        controls.next_btn,
        controls.shuffle_btn,
        controls.repeat_btn,
        controls.lyrics_btn,
        controls.queue_btn,
    ):
        assert button.accessibleName().strip()

    assert controls.volume_slider.accessibleName() == "Volumen"
    assert qa_window.search_input.accessibleName()
    assert qa_window.search_toggle_btn.accessibleName()
    assert qa_window.library_panel.filter_input.accessibleName()
    assert qa_window.now_playing_panel.video_toggle_btn.accessibleName()


def test_required_keyboard_shortcuts_are_registered_and_unique(qa_window):
    """Espacio y Ctrl+←/→ están registrados, documentados y sin duplicados."""
    from ui.menu import KEYBOARD_SHORTCUTS, SHORTCUTS_HELP

    assert KEYBOARD_SHORTCUTS["Space"] == "play_pause"
    assert KEYBOARD_SHORTCUTS["Ctrl+Left"] == "previous"
    assert KEYBOARD_SHORTCUTS["Ctrl+Right"] == "next"
    assert len(set(KEYBOARD_SHORTCUTS)) == len(KEYBOARD_SHORTCUTS)
    assert "Espacio" in SHORTCUTS_HELP
    assert "Ctrl+←" in SHORTCUTS_HELP

    for sequence in ("Space", "Ctrl+Left", "Ctrl+Right"):
        assert _shortcut(qa_window, sequence) is not None, sequence


def test_keyboard_shortcuts_drive_playback(qa_window, qtbot):
    """Las acciones registradas en los atajos controlan la reproducción real."""
    for index in range(2):
        qa_window.playlist_controller.add_track(_track(index))
    qa_window.playback_controller.play_index(0)
    qtbot.wait(20)

    space = _shortcut(qa_window, "Space")
    space.activated.emit()
    qtbot.wait(20)
    assert qa_window.playback_controller.state == PlayerState.PAUSED

    space.activated.emit()
    qtbot.wait(20)
    assert qa_window.playback_controller.state == PlayerState.PLAYING

    _shortcut(qa_window, "Ctrl+Right").activated.emit()
    qtbot.wait(20)
    assert qa_window.playlist_controller.playlist.current_index == 1

    _shortcut(qa_window, "Ctrl+Left").activated.emit()
    qtbot.wait(20)
    assert qa_window.playlist_controller.playlist.current_index == 0


def test_minimum_window_size_is_usable_on_small_screens(qa_window):
    """La ventana no baja de 980×680, el mínimo validado en la revisión manual."""
    minimum = qa_window.minimumSize()
    assert minimum.width() >= 980
    assert minimum.height() >= 680


def test_sidebar_shows_all_navigation_items(qa_window, qtbot):
    """Regresión: «Historial» no debe quedar recortado por falta de layout."""
    from ui.panels.sidebar import NAV_ITEMS

    qa_window.show()
    qtbot.wait(20)
    sidebar = qa_window.sidebar
    assert sidebar.list_widget.count() == len(NAV_ITEMS)

    last_item = sidebar.list_widget.item(len(NAV_ITEMS) - 1)
    last_rect = sidebar.list_widget.visualItemRect(last_item)
    assert last_rect.bottom() <= sidebar.list_widget.viewport().height()


def test_all_themes_meet_wcag_aa_contrast(qa_window):
    """Texto principal y secundario superan 4.5:1 en todos los temas."""
    for name, theme in ALL_THEMES.items():
        colors = theme.colors
        main = _contrast_ratio(colors["TEXT_MAIN"], colors["BG"])
        muted = _contrast_ratio(colors["TEXT_MUTED"], colors["BG_LIST"])
        assert main >= 4.5, f"{name}: texto principal {main:.2f}:1"
        assert muted >= 4.5, f"{name}: texto secundario {muted:.2f}:1"


def test_all_themes_generate_complete_stylesheets(qa_window):
    """Ningún tema deja placeholders sin sustituir y todos cubren los controles."""
    token = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
    for name in ThemeManager.theme_names():
        stylesheet = ThemeManager.get_theme(name)
        assert stylesheet.strip(), name
        assert "QPushButton" in stylesheet, name
        assert "QMainWindow" in stylesheet, name
        assert not token.search(stylesheet), f"{name}: token sin sustituir"


def test_visible_texts_are_clear_and_not_placeholders(qa_window):
    """Los textos clave están presentes y no exponen valores internos."""
    assert qa_window.playlist_panel.header_label.text().startswith("Mi lista")
    assert qa_window.library_panel.add_folder_btn.text().strip()
    assert qa_window.library_panel.filter_input.placeholderText().strip()
    assert qa_window.lyrics_panel.header_label.text() == "Letras"
    assert qa_window.controls_panel.time_label.text() == "0:00"

    for widget in qa_window.findChildren(QWidget):
        if isinstance(widget, (QLabel, QPushButton)):
            text = widget.text()
            assert "None" not in text
            assert "{}" not in text


# ---------------------------------------------------------------------------
# Rendimiento
# ---------------------------------------------------------------------------
def test_bulk_playlist_load_1000_tracks_within_budget(qa_window):
    """Cargar 1000 pistas en la playlist debe ser casi instantáneo para la UI."""
    tracks = [_track(index) for index in range(1000)]
    started = time.perf_counter()
    qa_window.playlist_controller.add_tracks(tracks)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert qa_window.playlist_controller.count == 1000
    assert qa_window.track_model.rowCount() == 1000
    assert elapsed_ms < 2000, f"carga de 1000 pistas: {elapsed_ms:.1f} ms"


def test_theme_stylesheet_generation_within_budget():
    """Generar todos los temas (QSS) no debe bloquear el cambio de apariencia."""
    started = time.perf_counter()
    for _ in range(10):
        for name in ThemeManager.theme_names():
            assert ThemeManager.get_theme(name)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 2000, f"generación de temas: {elapsed_ms:.1f} ms"


def test_library_filter_1000_entries_within_budget(qa_window):
    """El filtro de biblioteca responde con 1000 entradas sin congelar la UI."""
    entries = [
        {
            "path": f"/music/{index}.mp3",
            "filename": f"{index}.mp3",
            "title": f"Canción {index}",
            "artist": f"Artista {index % 50}",
            "album": f"Álbum {index % 20}",
            "rel_dir": ".",
            "duration": 180,
        }
        for index in range(1000)
    ]

    started = time.perf_counter()
    qa_window.library_panel.set_entries(entries)
    qa_window.library_panel.proxy.set_filter_text("Artista 42")
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert qa_window.library_panel.model.rowCount() > 0
    assert elapsed_ms < 3000, f"filtro de 1000 entradas: {elapsed_ms:.1f} ms"


def test_cover_placeholder_and_local_cover_load_within_budget(qa_window, tmp_path):
    """La portada de reserva y la carga de una imagen local no bloquean la UI."""
    cover_path = tmp_path / "cover.png"
    pixmap = QPixmap(600, 600)
    pixmap.fill(QColor("#224466"))
    assert pixmap.save(str(cover_path), "PNG")

    label = qa_window.now_playing_panel.cover_label
    started = time.perf_counter()
    for _ in range(50):
        label.set_cover("")
    placeholder_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    for _ in range(50):
        label.set_cover(str(cover_path))
    local_ms = (time.perf_counter() - started) * 1000

    assert placeholder_ms < 1500, f"placeholder: {placeholder_ms:.1f} ms"
    assert local_ms < 3000, f"portada local: {local_ms:.1f} ms"


def test_thumbnail_cache_reuses_scaled_pixmaps(qapp):
    """La caché del delegado evita reescalar la misma portada en cada repintado."""
    model = TrackListModel()
    model.set_tracks([_track(0, cover_url="cover://demo")])
    delegate = TrackListDelegate(_PixmapProvider())
    index = model.index(0, 0)

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 400, 56)
    option.font = qapp.font()
    option.state = QStyle.StateFlag.State_Enabled

    canvas = QPixmap(400, 56)
    painter = QPainter(canvas)
    try:
        delegate.paint(painter, option, index)
        key = ("cover://demo", 44, 44)
        assert key in delegate._scaled_cache
        first = delegate._scaled_cache[key]

        delegate.paint(painter, option, index)
        assert delegate._scaled_cache[key] is first
    finally:
        painter.end()


def test_marquee_timer_only_runs_when_text_overflows(qtbot):
    """El temporizador del marquee se detiene si el texto cabe o el control se oculta."""
    label = MarqueeLabel()
    qtbot.addWidget(label)
    label.resize(140, 24)

    label.setText("Corto")
    label.show()
    qtbot.wait(20)
    assert label._scroll_enabled is False
    assert label._timer.isActive() is False

    label.setText("Texto muy largo " * 20)
    qtbot.wait(20)
    assert label._scroll_enabled is True
    assert label._timer.isActive() is True

    label.hide()
    qtbot.wait(20)
    assert label._timer.isActive() is False


def test_large_track_model_memory_is_bounded():
    """3000 pistas no disparan el consumo de memoria del modelo de lista."""
    tracemalloc.start()
    try:
        tracks = [_track(index) for index in range(3000)]
        model = TrackListModel()
        model.set_tracks(tracks)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    assert model.rowCount() == 3000
    assert peak_mb < 35, f"pico de memoria: {peak_mb:.1f} MB"


# ---------------------------------------------------------------------------
# Regresión
# ---------------------------------------------------------------------------
def test_startup_has_no_known_qt_warnings(qtbot):
    """Regresión: sin avisos de paintEngine, fuentes inválidas ni tamaños negativos."""
    messages: list[str] = []
    previous = qInstallMessageHandler(
        lambda _mode, _context, message: messages.append(str(message))
    )
    win = None
    try:
        from core.player import MusicPlayer
        from tests.fakes.fake_vlc import FakeVlcModule

        win = MainWindow(player=MusicPlayer(vlc_module=FakeVlcModule()))
        qtbot.addWidget(win)
        win.show()
        qtbot.wait(50)
        for name in ThemeManager.theme_names():
            win.apply_theme(name)
        qtbot.wait(20)
    finally:
        qInstallMessageHandler(previous)
        if win is not None:
            win.close()

    forbidden = (
        "QWidget::paintEngine",
        "QFont::setPointSize",
        "negative size",
        "QWindowsWindow::setGeometry",
        "QObject::startTimer",
    )
    bad = [message for message in messages if any(pattern in message for pattern in forbidden)]
    assert not bad, bad


def test_video_surface_is_embedded_without_paint_on_screen(qa_window):
    """El vídeo vive dentro de la UI y no usa WA_PaintOnScreen (aviso de Qt6)."""
    panel = qa_window.now_playing_panel
    video = panel.video_widget

    assert isinstance(video, VideoWidget)
    assert panel.isAncestorOf(video)
    assert video.parent() is panel.video_frame
    assert video.testAttribute(Qt.WidgetAttribute.WA_PaintOnScreen) is False
    assert video.testAttribute(Qt.WidgetAttribute.WA_NativeWindow) is True


def test_clay_theme_only_shadows_safe_panels(qa_window):
    """Las sombras clay se limitan a paneles sin superficie nativa de VLC."""
    content = qa_window.findChild(QWidget, "ContentArea")

    qa_window.apply_theme("clay_dracula")
    assert qa_window.sidebar.graphicsEffect() is not None
    assert qa_window.controls_panel.graphicsEffect() is not None
    assert content.graphicsEffect() is None
    assert qa_window.now_playing_panel.video_frame.graphicsEffect() is None

    qa_window.apply_theme("dark")
    assert qa_window.sidebar.graphicsEffect() is None
    assert qa_window.controls_panel.graphicsEffect() is None


def test_video_size_modes_persist_and_clamp_invalid_sizes(qa_window, qtbot):
    """Los modos de vídeo se guardan con debounce y los tamaños negativos se corrigen."""
    panel = qa_window.now_playing_panel

    panel.video_frame.set_mode(VideoSizeMode.CINEMA)
    assert panel.current_video_size_mode() == VideoSizeMode.CINEMA
    assert qa_window.config.video_size_mode == "cinema"
    assert qa_window._video_cfg_timer.isActive() is True

    panel.video_frame.set_mode(VideoSizeMode.STANDARD)
    panel.set_video_size(-40, -20)
    assert panel.video_frame.width() >= VIDEO_MIN_SIZE.width()
    assert panel.video_frame.height() >= VIDEO_MIN_SIZE.height()

    qtbot.wait(450)
    assert qa_window._video_cfg_timer.isActive() is False


def test_video_fullscreen_round_trip_restores_previous_mode(qa_window, qtbot):
    """Entrar y salir de pantalla completa restaura el modo anterior del vídeo."""
    panel = qa_window.now_playing_panel
    panel.video_frame.set_mode(VideoSizeMode.CINEMA)

    with qtbot.waitSignal(panel.video_fullscreen_requested, timeout=1000) as blocker:
        panel.set_video_size_mode(VideoSizeMode.FULLSCREEN)
    assert blocker.args == [True]
    assert panel.current_video_size_mode() == VideoSizeMode.FULLSCREEN

    panel.exit_fullscreen()
    assert panel.current_video_size_mode() == VideoSizeMode.CINEMA
    qa_window.showNormal()


def test_view_navigation_keeps_expected_stack_indexes(qa_window):
    """Cada entrada de la barra lateral sigue apuntando a su vista."""
    from ui.panels.sidebar import NAV_ITEMS

    for item in NAV_ITEMS:
        qa_window.sidebar.select(item.key)
        assert qa_window.stack.currentIndex() == VIEW_INDEX[item.key], item.key
