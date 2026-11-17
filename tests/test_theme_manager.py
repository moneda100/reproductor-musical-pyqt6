"""Pruebas unitarias para ui.themes.ThemeManager.

Validan la separación entre definición de tema (datos: DesignTokens/Theme)
y generación de presentación (QSS): get_theme() no debe dejar placeholders
sin remplazar y debe aplicar los tokens de diseño (espaciado, radios,
tipografía) en la hoja de estilos resultante.
"""

from __future__ import annotations

import pytest

from ui.themes import ALL_THEMES, ThemeManager


@pytest.mark.parametrize("theme_name", list(ALL_THEMES))
def test_get_theme_no_unreplaced_placeholders(theme_name: str) -> None:
    """Nunca debe quedar un placeholder {CLAVE} sin remplazar en el QSS."""
    qss = ThemeManager.get_theme(theme_name)
    import re

    unreplaced = re.findall(r"\{[A-Z_]+\}", qss)
    assert not unreplaced, f"Placeholders sin remplazar en {theme_name}: {unreplaced}"


@pytest.mark.parametrize("theme_name", list(ALL_THEMES))
def test_get_theme_applies_design_tokens(theme_name: str) -> None:
    """Los tokens de diseño (space_*, radius_*, font_size_*) deben aparecer en el QSS."""
    qss = ThemeManager.get_theme(theme_name)
    assert "font-family" in qss
    assert "border-radius" in qss
    assert "padding" in qss


def test_clay_variant_has_clay_prefix() -> None:
    """clay_variant debe nombrar el tema con prefijo clay_."""
    from ui.themes import DARK, clay_variant

    variant = clay_variant(DARK)
    assert variant.name == "clay_dark"
    assert "CLAY_SURFACE" in variant.colors


def test_all_themes_have_required_color_keys() -> None:
    """Cada tema debe definir las claves de color mínimas usadas por el QSS."""
    required = {"BG", "BG_LIST", "PRIMARY", "TEXT_MAIN", "TEXT_MUTED"}
    for name, theme in ALL_THEMES.items():
        missing = required - set(theme.colors)
        assert not missing, f"Tema {name} falta claves: {missing}"
