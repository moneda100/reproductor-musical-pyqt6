"""Pruebas de PWA en navegador real con Playwright.

Validan que el compañero web (``web/``) renderiza correctamente en un
navegador Chromium real: título, controles con nombre accesible, manifest
instalable y objetivos táctiles mínimos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
INDEX_URL = f"file://{WEB_DIR / 'index.html'}"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(INDEX_URL)
        yield page
        browser.close()


def test_pwa_title_and_lang(page):
    """La PWA declara título y idioma español."""
    assert page.title() == "Music Player Pro"
    assert page.evaluate("document.documentElement.lang") == "es"


def test_pwa_interactive_controls_have_accessible_names(page):
    """Todo botón interactivo tiene nombre accesible (aria-label o texto visible)."""
    buttons = page.locator("button")
    count = buttons.count()
    assert count > 0, "index.html debe contener controles"
    for i in range(count):
        btn = buttons.nth(i)
        aria = btn.get_attribute("aria-label") or ""
        text = btn.inner_text() or ""
        assert aria.strip() or text.strip(), f"Botón {i} sin nombre accesible"


def test_pwa_images_have_alt(page):
    """Toda imagen tiene atributo alt."""
    imgs = page.locator("img")
    count = imgs.count()
    assert count > 0, "index.html debe contener imágenes"
    for i in range(count):
        alt = imgs.nth(i).get_attribute("alt") or ""
        assert alt.strip(), f"Imagen {i} sin alt"


def test_manifest_installable():
    """El manifest permite instalar la PWA (name, start_url, display, iconos)."""
    manifest = json.loads((WEB_DIR / "manifest.json").read_text(encoding="utf-8"))
    for key in ("name", "short_name", "start_url", "display"):
        assert manifest.get(key), key
    assert manifest["display"] in {"standalone", "fullscreen", "minimal-ui"}
    icons = manifest.get("icons") or []
    assert icons, "el manifest debe declarar al menos un icono"


def test_pwa_touch_targets_min_44px(page):
    """Los botones principales deben tener al menos 44 px de alto (objetivo táctil)."""
    min_height = page.evaluate(
        """
        () => {
            const buttons = Array.from(document.querySelectorAll('button'));
            if (!buttons.length) return 0;
            const heights = buttons.map(b => {
                const r = b.getBoundingClientRect();
                return Math.max(r.width, r.height);
            });
            return Math.max(...heights);
        }
        """
    )
    assert min_height >= 44, f"Objetivo táctil mínimo {min_height}px < 44px"
