"""Configuración común de las pruebas.

Las pruebas usan un directorio de datos temporal (``MUSICPLAYERPRO_HOME``) para
no tocar la configuración real del usuario.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# En CI (y en máquinas sin pantalla) Qt debe usar el backend "offscreen".
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Asegurar una instancia de QApplication para las pruebas de UI.
_qapp = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_app_home(tmp_path, monkeypatch):
    """Redirige las rutas de la app a un directorio temporal."""
    home = tmp_path / "appdata"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MUSICPLAYERPRO_HOME", str(home))

    from core import paths

    paths.get_paths.cache_clear()
    yield home
    paths.get_paths.cache_clear()


@pytest.fixture
def window(qtbot, monkeypatch):
    """Ventana principal con el reproductor sustituido por un doble."""
    from core.player import MusicPlayer
    from tests.fakes.fake_vlc import FakeVlcModule
    from ui.main_window import MainWindow

    fake = FakeVlcModule()
    win = MainWindow(player=MusicPlayer(vlc_module=fake))
    qtbot.addWidget(win)
    # La suite no debe depender de servicios externos ni dejar workers de red
    # terminando después del teardown.
    monkeypatch.setattr(win.lyrics_service, "get_lyrics", lambda *a, **k: None)
    monkeypatch.setattr(win.search_controller, "search_cover", lambda *a, **k: None)
    yield win
    win.close()


@pytest.fixture
def fake_vlc():
    from tests.fakes.fake_vlc import FakeVlcModule

    return FakeVlcModule()


@pytest.fixture
def player(fake_vlc):
    from core.player import MusicPlayer

    return MusicPlayer(vlc_module=fake_vlc)


@pytest.fixture
def playlist():
    from core.playlist import Playlist

    return Playlist("Prueba")


@pytest.fixture
def make_track():
    from core.playlist import Track

    def _make(index: int = 0, **overrides):
        payload = {
            "id": f"track{index}",
            "title": f"Título {index}",
            "artist": f"Artista {index}",
            "album": "Álbum",
            "file_path": f"/music/{index}.mp3",
            "duration": 180.0 + index,
            "source": "local",
        }
        payload.update(overrides)
        return Track(**payload)

    return _make
