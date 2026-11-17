"""Pruebas de rutas, configuración y logging."""

from __future__ import annotations

from pathlib import Path

from core.config import AppConfig, ConfigStore
from core.logging_setup import setup_logging
from core.paths import get_paths


def test_paths_are_inside_the_isolated_home(isolated_app_home):
    paths = get_paths()
    assert paths.root == Path(isolated_app_home)
    assert paths.state_db.parent == paths.root
    assert paths.log_file.parent == paths.logs_dir
    assert paths.covers_dir.is_dir()
    assert paths.youtube_cache_dir.is_dir()
    assert paths.playlists_dir.is_dir()


def test_paths_ensure_is_idempotent():
    paths = get_paths()
    assert paths.ensure() is paths


def test_config_roundtrip():
    store = ConfigStore()
    config = store.load()
    config.theme = "light"
    config.volume = 42
    config.download_dir = "C:/Descargas"
    store.save(config)

    reloaded = ConfigStore().load()
    assert reloaded.theme == "light"
    assert reloaded.volume == 42
    assert reloaded.download_dir == "C:/Descargas"


def test_config_defaults():
    config = AppConfig()
    assert config.theme == "auto"
    assert config.volume == 70
    assert config.max_cache_mb == 512


def test_config_from_dict_ignores_unknown_keys():
    config = AppConfig.from_dict({"theme": "cyberpunk", "nope": 1})
    assert config.theme == "cyberpunk"


def test_logging_setup_creates_file():
    paths = get_paths()
    logger = setup_logging(force=True)
    logger.info("mensaje de prueba")
    for handler in logger.handlers:
        handler.flush()
    assert paths.log_file.exists()
    assert "mensaje de prueba" in paths.log_file.read_text(encoding="utf-8")
    setup_logging(force=True)
