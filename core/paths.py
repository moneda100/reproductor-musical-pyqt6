"""Rutas de aplicación resolvidas desde el entorno del usuario.

Todas las rutas de escritura (estado, logs, caché, playlists) cuelgan de
``QStandardPaths.AppDataLocation`` para que funcionen igual en modo fuente y
en un bundle congelado con PyInstaller (donde el CWD no es fiable).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

APP_NAME = "MusicPlayerPro"
APP_ORG = "MusicPlayerPro"


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / f".write_test_{os.getpid()}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _base_data_dir() -> Path:
    """Directorio raíz de datos de la aplicación.

    Se intenta usar ``QStandardPaths`` (respeta el SO), con un fallback a
    ``%LOCALAPPDATA%`` en Windows y a ``~/.local/share`` en Linux/macOS para
    que el módulo se pueda usar sin inicializar un ``QApplication``.
    """
    try:
        from PyQt6.QtCore import QCoreApplication, QStandardPaths

        if not QCoreApplication.applicationName():
            QCoreApplication.setApplicationName(APP_NAME)
        if not QCoreApplication.organizationName():
            QCoreApplication.setOrganizationName(APP_ORG)

        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if base:
            p = Path(base)
            if p.name != APP_NAME:
                p = p / APP_NAME
            if _is_writable(p):
                return p
    except Exception:  # pragma: no cover - depende del entorno de Qt
        pass

    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            p = Path(root) / APP_NAME
            if _is_writable(p):
                return p

    # Fallback portable o modo sandbox
    local_data = Path(__file__).resolve().parent.parent / "data"
    if _is_writable(local_data):
        return local_data

    fallback = Path.home() / ".local" / "share" / APP_NAME
    _is_writable(fallback)
    return fallback


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


@dataclass(frozen=True)
class AppPaths:
    """Conjunto de rutas de datos de la aplicación."""

    root: Path

    # --- directorios ---
    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def covers_dir(self) -> Path:
        return self.cache_dir / "covers"

    @property
    def images_dir(self) -> Path:
        return self.cache_dir / "images"

    @property
    def youtube_cache_dir(self) -> Path:
        return self.cache_dir / "youtube"

    @property
    def playlists_dir(self) -> Path:
        return self.root / "playlists"

    # --- ficheros ---
    @property
    def state_db(self) -> Path:
        return self.root / "state.db"

    @property
    def main_playlist(self) -> Path:
        return self.playlists_dir / "playlist.json"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "musicplayerpro.log"

    def ensure(self) -> "AppPaths":
        """Crea los directorios necesarios. Idempotente."""
        for directory in (
            self.root,
            self.logs_dir,
            self.cache_dir,
            self.covers_dir,
            self.images_dir,
            self.youtube_cache_dir,
            self.playlists_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def resource_path(self, *parts: str) -> Path:
        """Ruta a un recurso empaquetado (compatible con PyInstaller)."""
        if _is_frozen():
            import sys as _sys

            base = Path(getattr(_sys, "_MEIPASS", self.root))
        else:
            base = Path(__file__).resolve().parent.parent
        return base.joinpath(*parts)


@lru_cache(maxsize=1)
def get_paths() -> AppPaths:
    """Devuelve (y memoriza) las rutas de la aplicación."""
    override = os.environ.get("MUSICPLAYERPRO_HOME")
    if override:
        root = Path(override)
    else:
        root = _base_data_dir()
    return AppPaths(root=root).ensure()
