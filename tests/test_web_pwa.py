"""QA estática del compañero web/PWA (``web/``).

El navegador es un cliente más del reproductor. Estas pruebas no levantan un
navegador real: validan el contrato estático que afecta a la experiencia
móvil y a la accesibilidad (viewport, manifest instalable, etiquetas ARIA,
safe-area y tamaño de los objetivos táctiles). La verificación visual en dos
navegadores y en un dispositivo móvil queda documentada como checklist
manual en ``docs/QA_UI_REPORT.md``.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.qa

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class _IndexParser(HTMLParser):
    """Extrae metadatos, etiquetas y controles de ``index.html``."""

    def __init__(self) -> None:
        super().__init__()
        self.lang = ""
        self.title = ""
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self._in_title = False
        self._current_button: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        data = {name: value or "" for name, value in attrs}
        if tag == "html":
            self.lang = data.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(data)
        elif tag == "link":
            self.links.append(data)
        elif tag == "button":
            data["_text"] = ""
            self.buttons.append(data)
            self._current_button = data
        elif tag == "img":
            self.images.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "button":
            self._current_button = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._current_button is not None:
            self._current_button["_text"] += data


@pytest.fixture(scope="module")
def index_html() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index(index_html: str) -> _IndexParser:
    parser = _IndexParser()
    parser.feed(index_html)
    return parser


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((WEB_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_index_declares_mobile_viewport_and_language(index: _IndexParser):
    """La vista móvil no debe hacer zoom raro ni asumir un idioma distinto."""
    assert index.lang == "es"
    assert index.title.strip() == "Music Player Pro"

    viewport = next((meta for meta in index.metas if meta.get("name") == "viewport"), None)
    assert viewport is not None
    content = viewport["content"]
    assert "width=device-width" in content
    assert "initial-scale=1" in content
    assert "viewport-fit=cover" in content


def test_manifest_is_installable(manifest: dict):
    """El manifest permite instalar la PWA en Android/iOS y escritorio."""
    for key in ("name", "short_name", "start_url", "display", "background_color", "theme_color"):
        assert manifest.get(key), key
    assert manifest["display"] in {"standalone", "fullscreen", "minimal-ui"}
    assert manifest["lang"] == "es"

    icons = manifest.get("icons") or []
    assert icons, "el manifest debe declarar al menos un icono"
    assert any("maskable" in str(icon.get("purpose", "")) for icon in icons)


def test_interactive_controls_have_accessible_labels(index: _IndexParser):
    """Todo botón de icono tiene nombre accesible y toda imagen tiene alt."""
    assert index.buttons, "index.html debe contener controles"
    for button in index.buttons:
        accessible_name = button.get("aria-label", "").strip()
        visible_text = button.get("_text", "").strip()
        assert accessible_name or visible_text, button

    for image in index.images:
        assert image.get("alt", "").strip(), image


def test_styles_respect_safe_area_and_touch_targets():
    """La barra inferior evita el notch y los botones son táctiles (>=44 px)."""
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-bottom)" in css
    assert "env(safe-area-inset-top)" in css
    assert "@media (prefers-color-scheme: light)" in css

    # Los botones son cómodos para el pulgar: al menos 44 px en un eje.
    min_widths = [int(value) for value in re.findall(r"min-width:\s*(\d+)px", css)]
    primary_heights = [
        int(value) for value in re.findall(r"button\.primary\s*\{[^}]*height:\s*(\d+)px", css)
    ]
    assert min_widths and max(min_widths) >= 44
    assert primary_heights and max(primary_heights) >= 44
