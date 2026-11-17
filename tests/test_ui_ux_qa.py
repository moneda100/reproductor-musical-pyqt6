"""Pruebas QA y UI/UX del panel de inicio (``NowPlayingPanel``).

Validan:
- Un único conjunto de transporte (el global ``ControlsPanel``).
- Acciones del inicio con texto, tooltips y nombres accesibles.
- Colores de contraste y efecto hover en QSS.
- Vídeo que se adapta al frame (``ResizableVideoFrame``).
- Opciones de vídeo en un apartado compacto.
- Que los botones del inicio emiten señales funcionales.
"""

from __future__ import annotations

import re

from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.panels.now_playing import VideoSizeMode

# ---------------------------------------------------------------------------
# QA: Sin controles de transporte duplicados
# ---------------------------------------------------------------------------


def test_home_has_no_duplicate_transport_controls(window):
    """El inicio no repite el transporte: solo existe en ControlsPanel."""
    panel = window.now_playing_panel

    for name in (
        "play_btn",
        "prev_btn",
        "next_btn",
        "shuffle_btn",
        "repeat_btn",
        "mute_btn",
        "volume_slider",
        "slider",
        "time_label",
        "duration_label",
    ):
        assert not hasattr(panel, name), f"El inicio no debe duplicar «{name}»"

    assert panel.findChild(QWidget, "TransportBar") is None

    # El único conjunto de transporte está en la barra global.
    controls = window.controls_panel
    assert controls.play_btn is not None
    assert controls.prev_btn is not None
    assert controls.next_btn is not None
    assert controls.shuffle_btn is not None
    assert controls.repeat_btn is not None
    assert controls.mute_btn is not None


# ---------------------------------------------------------------------------
# QA: Botones con texto (sin iconos/emoji)
# ---------------------------------------------------------------------------


def test_action_buttons_use_text_not_icons(window):
    """Los botones de acción usan texto, no iconos."""
    panel = window.now_playing_panel

    for btn in (
        panel.favorite_btn,
        panel.lyrics_btn,
        panel.open_folder_btn,
        panel.mini_player_btn,
    ):
        assert isinstance(btn, QPushButton)
        text = btn.text()
        assert text, f"{btn.objectName()} no tiene texto"
        assert not re.search(r"[⭐☆📝📂🗟🔊🔇]", text), (
            f"{btn.objectName()} contiene emoji/icono: '{text}'"
        )


def test_video_option_buttons_use_text(window):
    """Los botones de opciones de vídeo usan texto, no iconos."""
    panel = window.now_playing_panel

    assert isinstance(panel.video_toggle_btn, QPushButton)
    assert panel.video_toggle_btn.text() == "Ver video"

    # El selector de modo ahora es un QComboBox con texto
    assert panel.size_mode_combo.count() == len(VideoSizeMode)
    for i in range(panel.size_mode_combo.count()):
        mode = panel.size_mode_combo.itemData(i)
        assert panel.size_mode_combo.itemText(i) == mode.label(), f"{mode} debería mostrar texto '{mode.label()}'"


# ---------------------------------------------------------------------------
# QA: Colores de contraste y efecto hover en QSS
# ---------------------------------------------------------------------------


def test_qss_has_transport_btn_styles(window):
    """El QSS mantiene estilos consistentes para los controles de transporte."""
    style = window.styleSheet()
    assert "TransportBtn" in style, "QSS debe contener estilos para TransportBtn"
    assert "TransportBtn:hover" in style, "QSS debe tener efecto hover para TransportBtn"
    assert "TransportBtn:checked" in style, "QSS debe tener estado checked para TransportBtn"
    assert "font-weight: 700" in style, "QSS debe usar negritas (font-weight 700)"


def test_qss_has_action_btn_styles(window):
    """El QSS contiene estilos para ActionBtn y la tarjeta de acciones."""
    style = window.styleSheet()
    assert "ActionBtn" in style, "QSS debe contener estilos para ActionBtn"
    assert "NowPlayingActions" in style, "QSS debe estilar la tarjeta de acciones"
    assert "font-weight: 700" in style, "QSS debe usar negritas en ActionBtn"


def test_qss_has_video_btn_styles(window):
    """El QSS contiene estilos para los botones de vídeo."""
    style = window.styleSheet()
    assert "VideoToggleBtn" in style, "QSS debe contener estilos para VideoToggleBtn"
    assert "VideoSizeBtn" in style, "QSS debe contener estilos para VideoSizeBtn"
    assert "VideoApplyBtn" in style, "QSS debe contener estilos para VideoApplyBtn"


# ---------------------------------------------------------------------------
# QA: Vídeo se adapta al frame
# ---------------------------------------------------------------------------


def test_video_frame_resizes_with_stage(window, qtbot):
    """El frame de vídeo se adapta al tamaño del stage (ResizableVideoFrame)."""
    panel = window.now_playing_panel

    panel.video_stage.resize(800, 450)
    qtbot.wait(10)

    frame_size = panel.video_frame.size()
    assert frame_size.width() > 0, "El frame de vídeo debe tener ancho > 0"
    assert frame_size.height() > 0, "El frame de vídeo debe tener alto > 0"
    ratio = frame_size.width() / frame_size.height()
    assert 1.7 < ratio < 1.9, f"Proporción 16:9 esperada, obtuvimos {ratio:.2f}"


def test_video_widget_paints_on_frame(window):
    """El VideoWidget está contenido dentro del VideoFrame."""
    panel = window.now_playing_panel
    assert panel.video_widget.parentWidget() is panel.video_frame, (
        "VideoWidget debe estar dentro de VideoFrame para que VLC pinte ahí"
    )


def test_video_toggle_switches_to_video_page_without_blank_space(window):
    """Ver vídeo sustituye la portada/información por el vídeo, sin huecos."""
    panel = window.now_playing_panel

    panel.set_video_available(True)
    panel.set_video_enabled(True)
    assert panel.content_stack.currentWidget() is panel.video_stage

    panel.set_video_enabled(False)
    assert panel.content_stack.currentWidget() is panel.player_page

    panel.set_video_available(False)


# ---------------------------------------------------------------------------
# QA: Opciones de vídeo en apartado compacto
# ---------------------------------------------------------------------------


def test_video_options_bar_is_compact(window):
    """La barra de opciones de vídeo es compacta y solo aparece con vídeo."""
    panel = window.now_playing_panel
    bar = panel.video_options_bar

    assert bar.isHidden() or bar.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred

    assert panel.video_w_spin.maximum() == 3840
    assert panel.video_h_spin.maximum() == 2160
    assert panel.video_w_spin.minimum() == 320
    assert panel.video_h_spin.minimum() == 180


def test_video_size_modes_are_four(window):
    """Hay exactamente 4 modos de tamaño de vídeo."""
    assert len(VideoSizeMode) == 4
    assert VideoSizeMode.STANDARD.label() == "Estándar"
    assert VideoSizeMode.CINEMA.label() == "Cine"
    assert VideoSizeMode.FULLSCREEN.label() == "Pantalla completa"
    assert VideoSizeMode.RESIZABLE.label() == "Responsivo"


# ---------------------------------------------------------------------------
# QA: Accesibilidad (nombres accesibles y tooltips)
# ---------------------------------------------------------------------------


def _home_buttons(panel):
    buttons = [
        panel.favorite_btn,
        panel.lyrics_btn,
        panel.open_folder_btn,
        panel.mini_player_btn,
        panel.video_toggle_btn,
        panel.video_apply_btn,
        panel.size_mode_combo,  # QComboBox también necesita nombre accesible
    ]
    return buttons


def test_all_buttons_have_accessible_names(window):
    """Todos los botones del inicio tienen nombre accesible."""
    for btn in _home_buttons(window.now_playing_panel):
        assert btn.accessibleName(), f"{btn.objectName()} no tiene nombre accesible"


def test_all_buttons_have_tooltips(window):
    """Todos los botones del inicio tienen tooltip descriptivo."""
    for btn in _home_buttons(window.now_playing_panel):
        assert btn.toolTip(), f"{btn.objectName()} no tiene tooltip"


# ---------------------------------------------------------------------------
# QA: Layout limpio (portada izquierda, información derecha, acciones abajo)
# ---------------------------------------------------------------------------


def test_layout_has_left_panel(window):
    """El panel tiene un panel izquierdo para la carátula (responsive)."""
    panel = window.now_playing_panel
    left_panel = panel.findChild(QWidget, "LeftPanel")
    assert left_panel is not None, "Debe existir un panel izquierdo (LeftPanel)"
    # Responsive: ancho mínimo 220px, máximo 360px
    assert left_panel.minimumWidth() == 220, "El panel izquierdo debe tener ancho mínimo 220px"
    assert left_panel.maximumWidth() == 360, "El panel izquierdo debe tener ancho máximo 360px"


def test_layout_has_actions_bar(window):
    """Las acciones viven en una tarjeta propia, sin barra de transporte."""
    panel = window.now_playing_panel
    actions = panel.findChild(QWidget, "NowPlayingActions")
    assert actions is not None, "Debe existir la tarjeta de acciones (NowPlayingActions)"

    for btn in (
        panel.favorite_btn,
        panel.lyrics_btn,
        panel.open_folder_btn,
        panel.mini_player_btn,
    ):
        assert actions.isAncestorOf(btn)


def test_cover_label_on_left_panel(window):
    """La carátula está en el panel izquierdo."""
    panel = window.now_playing_panel
    left_panel = panel.findChild(QWidget, "LeftPanel")
    assert panel.cover_label.parentWidget() is left_panel, (
        "La carátula debe estar dentro del panel izquierdo"
    )


def test_video_stage_in_center_right(window):
    """El stage de vídeo es expansible y ocupa el área central."""
    panel = window.now_playing_panel
    assert panel.video_stage.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


# ---------------------------------------------------------------------------
# QA: Los botones del inicio son funcionales (emiten sus señales)
# ---------------------------------------------------------------------------


def test_home_action_buttons_emit_signals(window, qtbot):
    """Cada acción del inicio emite la señal que la ventana principal conecta."""
    panel = window.now_playing_panel

    with qtbot.waitSignal(panel.favorite_requested, timeout=1000):
        panel.favorite_btn.click()
    with qtbot.waitSignal(panel.show_lyrics_requested, timeout=1000):
        panel.lyrics_btn.click()
    with qtbot.waitSignal(panel.open_folder_requested, timeout=1000):
        panel.open_folder_btn.click()
    with qtbot.waitSignal(panel.mini_toggled, timeout=1000):
        panel.mini_player_btn.click()
    panel.mini_player_btn.setChecked(False)


def test_video_toggle_and_apply_are_functional(window, qtbot):
    """Ver vídeo y Aplicar tamaño emiten señales y no dejan botones muertos."""
    panel = window.now_playing_panel

    with qtbot.waitSignal(panel.video_toggled, timeout=1000):
        panel.video_toggle_btn.click()
    panel.video_toggle_btn.setChecked(False)

    with qtbot.waitSignal(panel.video_size_mode_changed, timeout=1000):
        panel.video_apply_btn.click()


def test_mute_button_silences_and_restores_volume(window):
    """El botón de silencio (barra global) baja a 0 y recupera el volumen previo."""
    controls = window.controls_panel
    controls.volume_slider.setValue(64)
    controls.mute_btn.setChecked(True)
    assert controls.volume_slider.value() == 0

    controls.mute_btn.setChecked(False)
    assert controls.volume_slider.value() == 64


def test_all_control_icons_exist():
    """Los iconos de la barra global existen: ningún botón queda en blanco."""
    from ui.widgets import load_icon

    for name in (
        "shuffle",
        "prev",
        "play",
        "pause",
        "next",
        "repeat",
        "repeat_one",
        "volume_up",
        "volume_off",
        "lyrics",
        "menu",
    ):
        assert not load_icon(name).isNull(), f"Falta el icono «{name}.svg»"
