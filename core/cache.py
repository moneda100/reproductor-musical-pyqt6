"""Caché en disco de imágenes (carátulas) indexada por hash de la URL.

Las carátulas **no** se sincronizan entre dispositivos: cada uno las resuelve
por URL y las cachea localmente.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

from core.paths import get_paths

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


class ImageCache:
    """Caché de imágenes en disco con clave por hash de URL."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory else get_paths().images_dir
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        return self.directory / f"{url_hash(url)}{self._extension_for(url)}"

    @staticmethod
    def _extension_for(url: str) -> str:
        clean = url.split("?")[0].lower()
        for ext in IMAGE_EXTENSIONS:
            if clean.endswith(ext):
                return ext
        return ".jpg"

    def get_path(self, url: str) -> Optional[Path]:
        """Ruta del fichero cacheado si existe."""
        path = self.path_for(url)
        return path if path.exists() else None

    def read(self, url: str) -> Optional[bytes]:
        path = self.get_path(url)
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.debug("No se pudo leer la imagen cacheada %s: %s", url, exc)
            return None

    def store(self, url: str, data: bytes) -> Optional[Path]:
        """Guarda los bytes de la imagen y devuelve su ruta."""
        if not data:
            return None
        path = self.path_for(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            return path
        except OSError as exc:
            logger.warning("No se pudo cachear la imagen %s: %s", url, exc)
            return None

    def size_bytes(self) -> int:
        total = 0
        for entry in self.directory.glob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
        return total

    def purge(self, max_bytes: int) -> int:
        """Elimina las imágenes más antiguas hasta quedar por debajo del límite."""
        if max_bytes <= 0 or self.size_bytes() <= max_bytes:
            return 0
        files = sorted(
            (p for p in self.directory.glob("*") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        )
        removed = 0
        total = self.size_bytes()
        for path in files:
            if total <= max_bytes:
                break
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
                removed += 1
            except OSError:
                continue
        if removed:
            logger.info("Caché de imágenes purgada: %d ficheros", removed)
        return removed

    def clear(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory.mkdir(parents=True, exist_ok=True)
