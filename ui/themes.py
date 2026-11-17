"""Sistema de diseño de la aplicación.

``ui/themes.py`` ya era un mini design system (tokens en QSS). Aquí se
extiende con una capa de **espaciado, radios y tipografía** y con estilos de
componentes (foco, hover, disabled) que antes no existían: el tema solo
cubría controles básicos.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DesignTokens:
    """Capa de diseño: espaciado, radios, tipografía y elevación."""

    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 12
    space_lg: int = 16
    space_xl: int = 24

    radius_sm: int = 6
    radius_md: int = 10
    radius_lg: int = 14
    radius_pill: int = 999

    font_family: str = "'Segoe UI', 'Inter', 'Noto Sans', sans-serif"
    font_size_sm: int = 11
    font_size_md: int = 13
    font_size_lg: int = 15
    font_size_xl: int = 22

    focus_ring: int = 2
    elevation: int = 6


@dataclass(frozen=True)
class Theme:
    """Un tema completo: tokens de color + capa de diseño."""

    name: str
    colors: dict[str, str] = field(default_factory=dict)
    design: DesignTokens = field(default_factory=DesignTokens)


# ---------------------------------------------------------------------------
# Helpers de color para Claymorphism / Neumorfismo suave
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def lighten_color(hex_color: str, factor: float = 0.2) -> str:
    """Mezcla el color con blanco (factor 0..1) -> tono claro (luz)."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(tuple(int(c + (255 - c) * factor) for c in (r, g, b)))


def darken_color(hex_color: str, factor: float = 0.25) -> str:
    """Mezcla el color con negro (factor 0..1) -> tono oscuro (sombra)."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(tuple(int(c * (1.0 - factor)) for c in (r, g, b)))


def _is_dark(hex_color: str) -> bool:
    r, g, b = _hex_to_rgb(hex_color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


def clay_colors(bg: str) -> dict[str, str]:
    """Deriva los tokens de arcilla a partir del color de fondo de un tema.

    Claymorphism / Neumorfismo suave se basa en que el elemento parece
    tallado del mismo bloque que el fondo: mismo color de superficie, un
    resalte claro arriba-izquierda y una sombra oscura abajo-derecha, más una
    sombra exterior difusa que da elevación.
    """
    is_dark = _is_dark(bg)
    return {
        "CLAY_SURFACE": bg,
        "CLAY_LIGHT": lighten_color(bg, 0.17),
        "CLAY_LIGHT_SOFT": lighten_color(bg, 0.10),
        "CLAY_DARK": darken_color(bg, 0.22),
        "CLAY_DARK_DEEP": darken_color(bg, 0.38),
        "CLAY_SHADOW_OUTER": "rgba(0, 0, 0, 0.50)" if is_dark else "rgba(0, 0, 0, 0.16)",
    }


def clay_variant(base: Theme) -> Theme:
    """Devuelve una versión claymorphica de un tema existente."""
    colors = dict(base.colors)
    colors.update(clay_colors(base.colors.get("BG", "#000000")))
    return Theme(name=f"clay_{base.name}", colors=colors, design=base.design)


def is_clay_theme(name: str) -> bool:
    return bool(name) and name.lower().startswith("clay_")


DARK = Theme(
    name="dark",
    colors={
        "BG": "#0F0F0F",
        "BG_LIST": "#161616",
        "BG_INPUT": "#1E1E1E",
        "PRIMARY": "#1DB954",
        "PRIMARY_LIGHT": "#1ED760",
        "PRIMARY_DARK": "#15883E",
        "SECONDARY": "#282828",
        "SECONDARY_HOVER": "#3E3E3E",
        "TEXT_MAIN": "#FFFFFF",
        "TEXT_MUTED": "#B3B3B3",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#252525",
        "ITEM_HOVER": "#2A2A2A",
        "ITEM_SELECTED": "#282828",
        "DANGER": "#E5484D",
        "WARNING": "#F2C14E",
        "OVERLAY": "rgba(0, 0, 0, 0.65)",
    },
)

LIGHT = Theme(
    name="light",
    colors={
        "BG": "#F2F3F5",
        "BG_LIST": "#FFFFFF",
        "BG_INPUT": "#E3E5E8",
        "PRIMARY": "#5865F2",
        "PRIMARY_LIGHT": "#6773F3",
        "PRIMARY_DARK": "#4752C4",
        "SECONDARY": "#EBEDEF",
        "SECONDARY_HOVER": "#D1D3D6",
        "TEXT_MAIN": "#060607",
        "TEXT_MUTED": "#4E5058",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#EBEDEF",
        "ITEM_HOVER": "#F2F3F5",
        "ITEM_SELECTED": "#E3E5E8",
        "DANGER": "#D13438",
        "WARNING": "#B7860B",
        "OVERLAY": "rgba(0, 0, 0, 0.35)",
    },
)

CYBERPUNK = Theme(
    name="cyberpunk",
    colors={
        "BG": "#050505",
        "BG_LIST": "#0A0A0A",
        "BG_INPUT": "#121212",
        "PRIMARY": "#FF0055",
        "PRIMARY_LIGHT": "#FF3377",
        "PRIMARY_DARK": "#CC0044",
        "SECONDARY": "#1A1A1A",
        "SECONDARY_HOVER": "#2A2A2A",
        "TEXT_MAIN": "#00FFEA",
        "TEXT_MUTED": "#00AA9A",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#333",
        "ITEM_HOVER": "#121212",
        "ITEM_SELECTED": "#1A1A1A",
        "DANGER": "#FF3860",
        "WARNING": "#FFD166",
        "OVERLAY": "rgba(0, 0, 0, 0.7)",
    },
)

NORD = Theme(
    name="nord",
    colors={
        "BG": "#2E3440",
        "BG_LIST": "#3B4252",
        "BG_INPUT": "#434C5E",
        "PRIMARY": "#88C0D0",
        "PRIMARY_LIGHT": "#8FBCBB",
        "PRIMARY_DARK": "#81A1C1",
        "SECONDARY": "#4C566A",
        "SECONDARY_HOVER": "#4C566A",
        "TEXT_MAIN": "#ECEFF4",
        "TEXT_MUTED": "#D8DEE9",
        "BTN_TEXT": "#2E3440",
        "BORDER_SUBTLE": "#434C5E",
        "ITEM_HOVER": "#434C5E",
        "ITEM_SELECTED": "#88C0D0",
        "DANGER": "#BF616A",
        "WARNING": "#EBCB8B",
        "OVERLAY": "rgba(46, 52, 64, 0.75)",
    },
)

DRACULA = Theme(
    name="dracula",
    colors={
        "BG": "#282A36",
        "BG_LIST": "#282A36",
        "BG_INPUT": "#44475A",
        "PRIMARY": "#BD93F9",
        "PRIMARY_LIGHT": "#FF79C6",
        "PRIMARY_DARK": "#6272A4",
        "SECONDARY": "#44475A",
        "SECONDARY_HOVER": "#6272A4",
        "TEXT_MAIN": "#F8F8F2",
        "TEXT_MUTED": "#BD93F9",
        "BTN_TEXT": "#282A36",
        "BORDER_SUBTLE": "#6272A4",
        "ITEM_HOVER": "#44475A",
        "ITEM_SELECTED": "#BD93F9",
        "DANGER": "#FF5555",
        "WARNING": "#F1FA8C",
        "OVERLAY": "rgba(40, 42, 54, 0.8)",
    },
)

CATPPUCCIN = Theme(
    name="catppuccin",
    colors={
        "BG": "#1E1E2E",
        "BG_LIST": "#313244",
        "BG_INPUT": "#45475A",
        "PRIMARY": "#89B4FA",
        "PRIMARY_LIGHT": "#B4BEFE",
        "PRIMARY_DARK": "#74C7EC",
        "SECONDARY": "#45475A",
        "SECONDARY_HOVER": "#585B70",
        "TEXT_MAIN": "#CDD6F4",
        "TEXT_MUTED": "#A6ADC8",
        "BTN_TEXT": "#1E1E2E",
        "BORDER_SUBTLE": "#45475A",
        "ITEM_HOVER": "#45475A",
        "ITEM_SELECTED": "#89B4FA",
        "DANGER": "#F38BA8",
        "WARNING": "#FAB387",
        "OVERLAY": "rgba(30, 30, 46, 0.75)",
    },
)

SOLARIZED = Theme(
    name="solarized",
    colors={
        "BG": "#002B36",
        "BG_LIST": "#073642",
        "BG_INPUT": "#002B36",
        "PRIMARY": "#268BD2",
        "PRIMARY_LIGHT": "#2AA198",
        "PRIMARY_DARK": "#CB4B16",
        "SECONDARY": "#073642",
        "SECONDARY_HOVER": "#002B36",
        "TEXT_MAIN": "#EEE8D5",
        "TEXT_MUTED": "#93A1A1",
        "BTN_TEXT": "#002B36",
        "BORDER_SUBTLE": "#586E75",
        "ITEM_HOVER": "#073642",
        "ITEM_SELECTED": "#268BD2",
        "DANGER": "#DC322F",
        "WARNING": "#B58900",
        "OVERLAY": "rgba(0, 43, 54, 0.7)",
    },
)

# Tema High Contrast (WCAG AAA - 7:1 contrast ratio) para accesibilidad
HIGH_CONTRAST = Theme(
    name="high_contrast",
    colors={
        "BG": "#000000",
        "BG_LIST": "#000000",
        "BG_INPUT": "#1A1A1A",
        "PRIMARY": "#FFFF00",      # Amarillo brillante sobre negro = 19.6:1
        "PRIMARY_LIGHT": "#FFFF33",
        "PRIMARY_DARK": "#CCCC00",
        "SECONDARY": "#333333",
        "SECONDARY_HOVER": "#4A4A4A",
        "TEXT_MAIN": "#FFFFFF",    # Blanco puro sobre negro = 21:1
        "TEXT_MUTED": "#CCCCCC",   # Gris claro sobre negro = 15.3:1
        "BTN_TEXT": "#000000",
        "BORDER_SUBTLE": "#555555",
        "ITEM_HOVER": "#2A2A2A",
        "ITEM_SELECTED": "#FFFF00",
        "DANGER": "#FF0000",       # Rojo puro sobre negro = 5.25:1 (mejor en amarillo)
        "WARNING": "#FFFF00",
        "OVERLAY": "rgba(0, 0, 0, 0.9)",
    },
    design=DesignTokens(
        space_xs=4,
        space_sm=8,
        space_md=12,
        space_lg=16,
        space_xl=24,
        radius_sm=6,
        radius_md=10,
        radius_lg=14,
        radius_pill=999,
        font_family="'Segoe UI', 'Inter', 'Noto Sans', sans-serif",
        font_size_sm=12,
        font_size_md=14,
        font_size_lg=16,
        font_size_xl=24,
        focus_ring=3,
        elevation=8,
    ),
)

THEMES: dict[str, Theme] = {
    theme.name: theme for theme in (DARK, LIGHT, CYBERPUNK, NORD, DRACULA, CATPPUCCIN, SOLARIZED, HIGH_CONTRAST)
}

# Variantes Claymorphism / Neumorfismo suave de cada tema por defecto.
CLAY_THEMES: dict[str, Theme] = {}
for _base in THEMES.values():
    _variant = clay_variant(_base)
    CLAY_THEMES[_variant.name] = _variant

# Todos los temas disponibles (clásicos + clay).
ALL_THEMES: dict[str, Theme] = {**THEMES, **CLAY_THEMES}


class ThemeManager:
    """Administra los temas de estilo (QSS) de la aplicación."""

    BASE_STYLE = """
    * {
        font-family: {font_family};
        font-size: {font_size_md}px;
    }
    QMainWindow, QDialog {
        background-color: {BG};
    }
    QSplitter::handle { background: transparent; width: 4px; }

    /* Paneles */
    QWidget#ControlPanel {
        background-color: {BG_LIST};
        border-top: 1px solid {BORDER_SUBTLE};
        padding: {space_md}px {space_xl}px;
    }
    QWidget#Sidebar {
        background-color: {BG_LIST};
        border-right: 1px solid {BORDER_SUBTLE};
    }
    QWidget#NavList {
        background-color: {BG_LIST};
        border: none;
    }
    QWidget#NavList::item {
        padding: {space_md}px {space_lg}px;
        border-radius: {radius_md}px;
        color: {TEXT_MUTED};
    }
    QWidget#NavList::item:hover {
        background-color: {ITEM_HOVER};
        color: {TEXT_MAIN};
    }
    QWidget#NavList::item:selected {
        background-color: {ITEM_SELECTED};
        color: {PRIMARY};
        font-weight: 600;
    }

    /* Etiquetas */
    QLabel { color: {TEXT_MAIN}; font-size: {font_size_md}px; }
    QLabel#TitleLabel {
        font-size: {font_size_xl}px;
        font-weight: 800;
        color: {TEXT_MAIN};
    }
    QLabel#MutedLabel { color: {TEXT_MUTED}; font-size: {font_size_lg}px; }
    QLabel#StatusLabel {
        color: {PRIMARY};
        font-size: {font_size_sm}px;
        font-weight: bold;
    }
    QLabel#HintLabel { color: {TEXT_MUTED}; font-size: {font_size_sm}px; }
    QLabel#EyebrowLabel {
        color: {PRIMARY};
        font-size: {font_size_sm}px;
        font-weight: 800;
    }
    QLabel#HeroTitle {
        color: {TEXT_MAIN};
        font-size: 30px;
        font-weight: 800;
    }
    QLabel#HeroArtist {
        color: {TEXT_MUTED};
        font-size: {font_size_lg}px;
        font-weight: 600;
    }

    /* Inicio: acciones de la pista en una tarjeta limpia (sin transporte) */
    QWidget#NowPlayingInfo,
    QWidget#NowPlayingPlayerPage,
    QWidget#NowPlayingStack {
        background-color: transparent;
    }
    QWidget#NowPlayingActions,
    QWidget#VideoOptionsBar {
        background-color: {BG_LIST};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_lg}px;
    }

    /* Botones */
    QPushButton {
        background-color: {PRIMARY};
        color: {BTN_TEXT};
        border-radius: {radius_md}px;
        font-weight: 600;
        padding: {space_sm}px {space_lg}px;
        border: none;
        font-size: {font_size_md}px;
    }
    QPushButton:hover { background-color: {PRIMARY_LIGHT}; }
    QPushButton:pressed { background-color: {PRIMARY_DARK}; }
    QPushButton:disabled {
        background-color: {SECONDARY};
        color: {TEXT_MUTED};
    }
    QPushButton:focus {
        outline: none;
        border: {focus_ring}px solid {PRIMARY};
    }
    QPushButton#SecondaryBtn {
        background-color: {SECONDARY};
        color: {TEXT_MUTED};
    }
    QPushButton#SecondaryBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {TEXT_MAIN};
    }
    QPushButton#SecondaryBtn:checked {
        background-color: {SECONDARY_HOVER};
        color: {PRIMARY};
    }
    QPushButton#DangerBtn {
        background-color: {DANGER};
        color: white;
    }

    /* Botones de reproducción */
    QPushButton#PlayBtn {
        background-color: {PRIMARY};
        color: white;
        font-size: 28px;
        border-radius: {radius_pill}px;
        min-width: 70px;
        min-height: 70px;
    }
    QPushButton#PlayBtn:hover { background-color: {PRIMARY_LIGHT}; }
    QPushButton#ControlBtn {
        background-color: transparent;
        color: {TEXT_MUTED};
        font-size: 18px;
        border-radius: {radius_pill}px;
    }
    QPushButton#ControlBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {TEXT_MAIN};
    }
    QPushButton#ControlBtn:disabled { color: {BORDER_SUBTLE}; }
    QPushButton#ToggleBtn:checked {
        color: {PRIMARY};
        background-color: {SECONDARY_HOVER};
    }

    /* Botones de transporte con texto (sin iconos) - negritas y contraste */
    QPushButton#TransportBtn {
        background-color: {SECONDARY};
        color: {TEXT_MAIN};
        font-weight: 700;
        font-size: {font_size_sm}px;
        text-transform: uppercase;
        border-radius: {radius_md}px;
        padding: {space_sm}px {space_md}px;
        border: none;
        min-width: 70px;
    }
    QPushButton#TransportBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {PRIMARY};
    }
    QPushButton#TransportBtn:checked {
        background-color: {PRIMARY};
        color: white;
    }
    QPushButton#TransportBtn:disabled {
        background-color: {SECONDARY};
        color: {TEXT_MUTED};
    }

    /* Botón principal de reproducción (texto grande y prominente) */
    QPushButton#PlayBtn {
        background-color: {PRIMARY};
        color: white;
        font-weight: 700;
        font-size: {font_size_md}px;
        text-transform: uppercase;
        border-radius: {radius_pill}px;
        min-width: 100px;
        min-height: 56px;
        padding: {space_sm}px {space_lg}px;
    }
    QPushButton#PlayBtn:hover { background-color: {PRIMARY_LIGHT}; }

    /* Botones de acción secundaria */
    QPushButton#ActionBtn {
        background-color: {SECONDARY};
        color: {TEXT_MAIN};
        font-weight: 700;
        font-size: {font_size_sm}px;
        text-transform: uppercase;
        border-radius: {radius_md}px;
        padding: {space_sm}px {space_md}px;
        border: none;
        min-width: 60px;
    }
    QPushButton#ActionBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {PRIMARY};
    }
    QPushButton#ActionBtn:checked {
        background-color: {PRIMARY};
        color: white;
    }

    /* Botón silenciar */
    QPushButton#MuteBtn {
        background-color: {SECONDARY};
        color: {TEXT_MAIN};
        font-weight: 700;
        font-size: {font_size_sm}px;
        text-transform: uppercase;
        border-radius: {radius_md}px;
        padding: {space_sm}px {space_md}px;
        border: none;
        min-width: 70px;
    }
    QPushButton#MuteBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {PRIMARY};
    }
    QPushButton#MuteBtn:checked {
        background-color: {DANGER};
        color: white;
    }

    /* Botones de opciones de vídeo (apartado compacto) */
    QPushButton#VideoToggleBtn {
        background-color: {SECONDARY};
        color: {TEXT_MAIN};
        font-weight: 700;
        font-size: {font_size_sm}px;
        text-transform: uppercase;
        border-radius: {radius_md}px;
        padding: {space_xs}px {space_sm}px;
        border: none;
        min-width: 60px;
    }
    QPushButton#VideoToggleBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {PRIMARY};
    }
    QPushButton#VideoToggleBtn:checked {
        background-color: {PRIMARY};
        color: white;
    }

    QPushButton#VideoSizeBtn {
        background-color: {BG_LIST};
        color: {TEXT_MUTED};
        font-weight: 600;
        font-size: {font_size_sm}px;
        text-transform: capitalize;
        border-radius: {radius_md}px;
        padding: {space_xs}px {space_sm}px;
        border: 1px solid {BORDER_SUBTLE};
        min-width: 55px;
    }
    QPushButton#VideoSizeBtn:hover {
        background-color: {ITEM_HOVER};
        color: {PRIMARY};
        border-color: {PRIMARY};
    }
    QPushButton#VideoSizeBtn:checked {
        background-color: {PRIMARY};
        color: white;
        border-color: {PRIMARY};
    }

    QPushButton#VideoApplyBtn {
        background-color: {PRIMARY};
        color: white;
        font-weight: 700;
        font-size: {font_size_sm}px;
        text-transform: uppercase;
        border-radius: {radius_md}px;
        padding: {space_xs}px {space_sm}px;
        border: none;
        min-width: 60px;
    }
    QPushButton#VideoApplyBtn:hover { background-color: {PRIMARY_LIGHT}; }

    /* Listas y vistas */
    QListWidget, QListView, QTreeView, QTableWidget {
        background-color: {BG_LIST};
        color: {TEXT_MUTED};
        border: none;
        border-radius: {radius_md}px;
        padding: {space_sm}px;
        outline: none;
    }
    QListWidget::item, QTreeView::item, QTableWidget::item {
        padding: {space_sm}px;
        border-radius: {radius_sm}px;
        margin-bottom: 2px;
    }
    QListWidget::item:hover, QTreeView::item:hover, QTableWidget::item:hover {
        background-color: {ITEM_HOVER};
    }
    QListWidget::item:selected, QTreeView::item:selected, QTableWidget::item:selected {
        background-color: {ITEM_SELECTED};
        color: {PRIMARY};
    }
    QHeaderView::section {
        background-color: {BG_LIST};
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 1px solid {BORDER_SUBTLE};
        padding: {space_xs}px {space_sm}px;
        font-weight: 600;
    }
    QTableView QTableCornerButton::section {
        background-color: {BG_LIST};
        border: none;
    }
    QGroupBox {
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_md}px;
        margin-top: {space_md}px;
        padding-top: {space_sm}px;
        font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: {space_md}px;
        padding: 0 {space_xs}px;
        color: {TEXT_MUTED};
    }
    QListView::item, QTreeView::item {
        padding: {space_xs}px;
        border-radius: {radius_sm}px;
    }
    QTreeView::branch { background: transparent; }

    /* Tabs */
    QTabWidget::pane { border: none; top: -1px; background: transparent; }
    QTabBar::tab {
        background: transparent;
        color: {TEXT_MUTED};
        padding: {space_md}px {space_lg}px;
        font-weight: 600;
        border-bottom: 2px solid transparent;
    }
    QTabBar::tab:selected {
        color: {PRIMARY};
        border-bottom: 2px solid {PRIMARY};
    }
    QTabBar::tab:hover { color: {TEXT_MAIN}; }

    /* Inputs */
    QLineEdit, QComboBox, QSpinBox {
        background-color: {BG_INPUT};
        color: {TEXT_MAIN};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_pill}px;
        padding: {space_sm}px {space_lg}px;
        selection-background-color: {PRIMARY};
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
        border: {focus_ring}px solid {PRIMARY};
    }
    QComboBox::drop-down { border: none; width: {space_xl}px; }
    QComboBox QAbstractItemView {
        background-color: {BG_LIST};
        border: 1px solid {BORDER_SUBTLE};
        selection-background-color: {PRIMARY};
        color: {TEXT_MAIN};
    }

    /* Slider */
    QSlider::groove:horizontal {
        border: none;
        height: 6px;
        background: {SECONDARY};
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal { background: {PRIMARY}; border-radius: 3px; }
    QSlider::add-page:horizontal { background: {SECONDARY}; border-radius: 3px; }
    QSlider::handle:horizontal {
        background: {TEXT_MAIN};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
        border: 2px solid {PRIMARY};
    }
    QSlider::handle:horizontal:hover { background: {PRIMARY}; }
    QSlider::handle:horizontal:pressed { background: {PRIMARY}; }

    /* Barra de menús */
    QMenuBar { background-color: {BG_LIST}; color: {TEXT_MUTED}; }
    QMenuBar::item:selected { background: {ITEM_HOVER}; color: {TEXT_MAIN}; }
    QMenu { background-color: {BG_LIST}; color: {TEXT_MAIN}; border: 1px solid {BORDER_SUBTLE}; }
    QMenu::item:selected { background-color: {PRIMARY}; color: {BTN_TEXT}; }

    /* Dock */
    QDockWidget { titlebar-close-icon: none; }
    QDockWidget::title {
        background-color: {BG_LIST};
        padding: {space_sm}px;
        color: {TEXT_MUTED};
    }

    /* Barras de desplazamiento */
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: {SECONDARY};
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar:horizontal {
        border: none;
        background: transparent;
        height: 8px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background: {SECONDARY};
        min-width: 20px;
        border-radius: 4px;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

    /* Barras de progreso */
    QProgressBar {
        background-color: {SECONDARY};
        border: none;
        border-radius: {radius_sm}px;
        height: 8px;
        text-align: center;
        color: {TEXT_MAIN};
    }
    QProgressBar::chunk { background-color: {PRIMARY}; border-radius: {radius_sm}px; }

    /* Gestor de descargas (ventana independiente) */
    QDialog#DownloadManager { background-color: {BG}; }
    QWidget#ManagerHeader {
        background-color: {BG_LIST};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_lg}px;
    }
    QLabel#ManagerTitle {
        font-size: {font_size_xl}px;
        font-weight: 800;
        color: {TEXT_MAIN};
    }
    QLabel#SectionTitle {
        font-size: {font_size_lg}px;
        font-weight: 700;
        color: {TEXT_MAIN};
    }
    QLabel#HintLabel { color: {TEXT_MUTED}; font-size: {font_size_sm}px; }
    QLabel#CountChip {
        background-color: {SECONDARY};
        color: {PRIMARY};
        border-radius: {radius_pill}px;
        padding: 2px 10px;
        font-weight: 700;
        font-size: {font_size_sm}px;
    }
    QLabel#EmptyState {
        color: {TEXT_MUTED};
        font-size: {font_size_lg}px;
        padding: {space_xl}px;
    }
    QFrame#SummaryCard {
        background-color: {BG_LIST};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_md}px;
    }
    QGroupBox#SettingsCard {
        background-color: {BG_LIST};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_md}px;
    }
    QPushButton#GhostBtn {
        background-color: transparent;
        color: {TEXT_MUTED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_pill}px;
        padding: {space_xs}px {space_lg}px;
    }
    QPushButton#GhostBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {TEXT_MAIN};
    }
    QListView#ResultsList {
        background-color: transparent;
        border: none;
        padding: 0px;
    }

    /* Mini reproductor flotante */
    QWidget#MiniPlayer {
        background-color: {BG};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {radius_lg}px;
    }
    QWidget#MiniHeader {
        background-color: {BG_LIST};
        border-top-left-radius: {radius_lg}px;
        border-top-right-radius: {radius_lg}px;
    }
    QWidget#MiniBody { background-color: {BG}; }
    QLabel#MiniBrand {
        color: {TEXT_MUTED};
        font-size: {font_size_sm}px;
        font-weight: 700;
    }
    QLabel#MiniTitle {
        color: {TEXT_MAIN};
        font-size: {font_size_lg}px;
        font-weight: 700;
    }
    QPushButton#MiniPlayBtn {
        background-color: {PRIMARY};
        color: white;
        border-radius: {radius_pill}px;
        font-size: 20px;
    }
    QPushButton#MiniPlayBtn:hover { background-color: {PRIMARY_LIGHT}; }
    QPushButton#MiniControlBtn {
        background-color: transparent;
        color: {TEXT_MUTED};
        border-radius: {radius_pill}px;
        font-size: 15px;
    }
    QPushButton#MiniControlBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {TEXT_MAIN};
    }
    QPushButton#MiniControlBtn:checked {
        color: {PRIMARY};
        background-color: {SECONDARY_HOVER};
    }
    QPushButton#MiniCloseBtn {
        background-color: transparent;
        color: {TEXT_MUTED};
        border-radius: {radius_pill}px;
        font-size: 12px;
    }
    QPushButton#MiniCloseBtn:hover { background-color: {DANGER}; color: white; }
    QPushButton#MiniIconBtn {
        background-color: transparent;
        color: {TEXT_MUTED};
        border-radius: {radius_pill}px;
        font-size: 13px;
    }
    QPushButton#MiniIconBtn:hover {
        background-color: {SECONDARY_HOVER};
        color: {TEXT_MAIN};
    }
    """

    # ------------------------------------------------------------------
    # Claymorphism / Neumorfismo suave: bloque de estilos que se anexa
    # al BASE_STYLE cuando el tema activo es una variante clay_*.
    # ------------------------------------------------------------------
    CLAY_BASE_STYLE = """
    /* Estructura principal: superficies talladas del mismo bloque */
    QMainWindow, QDialog {
        background-color: {CLAY_SURFACE};
    }
    QWidget#ContentArea {
        background-color: {CLAY_SURFACE};
        border: none;
        border-radius: {radius_lg}px;
    }
    QWidget#Sidebar {
        background-color: {CLAY_SURFACE};
        border: none;
        border-radius: {radius_lg}px;
    }
    QWidget#ControlPanel {
        background-color: {CLAY_SURFACE};
        border: none;
        border-top: none;
        border-radius: 0px;
    }
    QWidget#NavList {
        background-color: transparent;
        border: none;
    }
    QWidget#NavList::item {
        background-color: transparent;
        color: {TEXT_MUTED};
        border-radius: {radius_md}px;
        padding: {space_md}px {space_lg}px;
    }
    QWidget#NavList::item:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT_SOFT}, stop:1 {CLAY_SURFACE});
        color: {TEXT_MAIN};
    }
    QWidget#NavList::item:selected {
        background-color: {PRIMARY};
        color: {BTN_TEXT};
        font-weight: 600;
    }

    /* Tarjetas clay */
    QWidget#ClayCard, QFrame#ClayCard, QWidget#VideoFrame {
        background-color: {CLAY_SURFACE};
        border: 1px solid {CLAY_DARK};
        border-radius: {radius_lg}px;
    }
    QWidget#NowPlayingActions,
    QWidget#VideoOptionsBar {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT_SOFT}, stop:1 {CLAY_SURFACE});
        border: 1px solid {CLAY_DARK};
        border-radius: {radius_lg}px;
    }

    /* Botones clay: resalte arriba-izquierda, sombra abajo-derecha */
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        border: 1px solid {CLAY_DARK};
        border-radius: {radius_md}px;
        color: {TEXT_MAIN};
        font-weight: 600;
        padding: {space_sm}px {space_lg}px;
        font-size: {font_size_md}px;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT_SOFT}, stop:1 {CLAY_LIGHT});
        border: 1px solid {PRIMARY};
        color: {TEXT_MAIN};
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_SURFACE}, stop:1 {CLAY_DARK_DEEP});
        border: 1px solid {CLAY_DARK_DEEP};
    }
    QPushButton:checked {
        background-color: {PRIMARY};
        border: 1px solid {PRIMARY_DARK};
        color: {BTN_TEXT};
    }
    QPushButton:disabled {
        background-color: {CLAY_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        color: {TEXT_MUTED};
    }
    QPushButton#PlayBtn, QPushButton#MiniPlayBtn {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        border: 1px solid {CLAY_DARK};
        border-radius: {radius_pill}px;
        color: {TEXT_MAIN};
    }
    QPushButton#PlayBtn:hover, QPushButton#MiniPlayBtn:hover {
        background-color: {PRIMARY};
        color: {BTN_TEXT};
        border: 1px solid {PRIMARY_DARK};
    }
    QPushButton#PlayBtn:pressed, QPushButton#MiniPlayBtn:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_SURFACE}, stop:1 {CLAY_DARK_DEEP});
    }
    QPushButton#ControlBtn, QPushButton#MiniControlBtn, QPushButton#ToggleBtn,
    QPushButton#MiniIconBtn, QPushButton#GhostBtn, QPushButton#SecondaryBtn {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT_SOFT}, stop:1 {CLAY_SURFACE});
        border: 1px solid {CLAY_DARK};
        color: {TEXT_MUTED};
    }
    QPushButton#ControlBtn:hover, QPushButton#MiniControlBtn:hover,
    QPushButton#ToggleBtn:hover, QPushButton#MiniIconBtn:hover,
    QPushButton#GhostBtn:hover, QPushButton#SecondaryBtn:hover {
        background-color: {CLAY_LIGHT};
        border: 1px solid {PRIMARY};
        color: {TEXT_MAIN};
    }
    QPushButton#ControlBtn:checked, QPushButton#ToggleBtn:checked,
    QPushButton#MiniControlBtn:checked {
        background-color: {PRIMARY};
        border: 1px solid {PRIMARY_DARK};
        color: {BTN_TEXT};
    }

    /* Entradas */
    QLineEdit, QComboBox, QSpinBox {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        border: 1px solid {CLAY_DARK};
        border-radius: {radius_pill}px;
        color: {TEXT_MAIN};
        padding: {space_sm}px {space_lg}px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
        border: {focus_ring}px solid {PRIMARY};
    }

    /* Slider */
    QSlider::groove:horizontal {
        border: none;
        height: 6px;
        background: {CLAY_DARK};
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal { background: {PRIMARY}; border-radius: 3px; }
    QSlider::add-page:horizontal { background: {CLAY_DARK}; border-radius: 3px; }
    QSlider::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        width: 18px; height: 18px; margin: -6px 0; border-radius: 9px;
        border: 1px solid {CLAY_DARK};
    }
    QSlider::handle:horizontal:hover {
        background: {PRIMARY}; border: 1px solid {PRIMARY};
    }

    /* Barras de desplazamiento clay */
    QScrollBar:vertical {
        border: none; background: transparent; width: 10px; margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        min-height: 30px; border-radius: 5px; border: 1px solid {CLAY_DARK};
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar:horizontal {
        border: none; background: transparent; height: 10px; margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {CLAY_LIGHT}, stop:1 {CLAY_SURFACE});
        min-width: 30px; border-radius: 5px; border: 1px solid {CLAY_DARK};
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

    QLabel { color: {TEXT_MAIN}; }
    QLabel#MutedLabel, QLabel#HintLabel { color: {TEXT_MUTED}; }
    QLabel#StatusLabel { color: {PRIMARY}; }
    """

    @staticmethod
    def get_system_theme() -> str:
        """Detecta el tema del sistema (Light/Dark) y devuelve el tema correspondiente.

        Returns:
            "light" si el sistema está en modo claro, "dark" si está en modo oscuro.
        """
        try:
            from PyQt6.QtGui import QGuiApplication
            hints = QGuiApplication.styleHints()
            # Qt 6.5+: colorScheme()
            scheme = getattr(hints, "colorScheme", lambda: None)()
            if scheme is not None:
                # QColorScheme: 0=Unknown, 1=Light, 2=Dark
                if scheme == 1:  # Light
                    return "light"
                elif scheme == 2:  # Dark
                    return "dark"
        except Exception:
            pass
        # Fallback: asumir dark
        return "dark"

    @staticmethod
    def get_theme(name: str = "dark") -> str:
        """Devuelve la hoja de estilos completa del tema indicado.

        Si el tema es una variante ``clay_*`` se anexa el bloque
        ``CLAY_BASE_STYLE`` para aplicar claymorphism / neumorfismo suave.
        """
        theme = ALL_THEMES.get((name or "dark").lower(), DARK)
        design = theme.design
        values = dict(theme.colors)
        values.update(
            {
                "font_family": design.font_family,
                "font_size_sm": design.font_size_sm,
                "font_size_md": design.font_size_md,
                "font_size_lg": design.font_size_lg,
                "font_size_xl": design.font_size_xl,
                "space_xs": design.space_xs,
                "space_sm": design.space_sm,
                "space_md": design.space_md,
                "space_lg": design.space_lg,
                "space_xl": design.space_xl,
                "radius_sm": design.radius_sm,
                "radius_md": design.radius_md,
                "radius_lg": design.radius_lg,
                "radius_pill": design.radius_pill,
                "focus_ring": design.focus_ring,
            }
        )
        style = ThemeManager.BASE_STYLE
        if is_clay_theme(name):
            style += ThemeManager.CLAY_BASE_STYLE
        for key, value in values.items():
            style = style.replace("{" + key + "}", str(value))
        return style

    @staticmethod
    def theme_names() -> list[str]:
        """Todos los temas disponibles: clásicos y sus variantes clay."""
        return list(ALL_THEMES)

    @staticmethod
    def apply_clay_shadow(
        widget,
        blur: int = 26,
        dx: int = 0,
        dy: int = 10,
        color: str = "#000000",
        alpha: float = 0.45,
    ):
        """Aplica una sombra exterior difusa (efecto de elevación neumórfica).

        Se combina con el degradado de QSS para lograr el aspecto tallado
        característico del claymorphism.
        """
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect

        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(dx, dy)
        qcolor = QColor(color)
        qcolor.setAlphaF(alpha)
        effect.setColor(qcolor)
        widget.setGraphicsEffect(effect)
        return effect
