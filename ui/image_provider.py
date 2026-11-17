"""Proveedor de imágenes con caché en memoria (``QPixmapCache``) y en disco.

Antes cada cambio de pista volvía a descargar la misma carátula. Ahora:

1. Se busca en la caché de disco (indexada por hash de la URL).
2. Si no está, se descarga en un worker del ``QThreadPool`` y se guarda.
3. El ``QPixmap`` se cachea en memoria (el objeto ``QPixmap`` solo puede
   crearse en el hilo de la GUI: por eso se decodifica en el slot de la señal).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap

from core.cache import ImageCache
from core.tasks.worker import Worker

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MusicPlayerPro"
MEMORY_CACHE_KB = 64 * 1024  # 64 MB


class ImageProvider(QObject):
    """Descarga y cachea carátulas. Un solo provider por aplicación."""

    image_ready = pyqtSignal(str, object)  # url, QPixmap

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._disk = ImageCache()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._memory: dict[str, QPixmap] = {}
        self._max_memory = 64

    # -- caché de memoria -------------------------------------------
    def _remember(self, url: str, pixmap: QPixmap) -> None:
        if len(self._memory) >= self._max_memory:
            self._memory.pop(next(iter(self._memory)))
        self._memory[url] = pixmap

    def cached_pixmap(self, url: str) -> Optional[QPixmap]:
        """Pixmap ya disponible (memoria o disco) sin red."""
        if not url:
            return None
        pixmap = self._memory.get(url)
        if pixmap is not None:
            return pixmap
        data = self._disk.read(url)
        if not data:
            return None
        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            self._remember(url, pixmap)
            return pixmap
        return None

    # -- descarga asíncrona ------------------------------------------
    def request(
        self,
        url: str,
        on_ready: Callable[[QPixmap], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> Worker:
        """Pide una imagen. Devuelve el worker para poder cancelarlo."""
        if not url:
            if on_error:
                on_error("URL vacía")
            return Worker(lambda: None)

        cached = self.cached_pixmap(url)
        if cached is not None:
            if on_ready:
                on_ready(cached)
            self.image_ready.emit(url, cached)
            return Worker(lambda: None)

        def _fetch() -> bytes:
            import requests

            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=8)
            response.raise_for_status()
            return response.content

        worker = Worker(_fetch)
        worker.signals.result.connect(lambda data: self._deliver(url, data, on_ready, on_error))
        worker.signals.error.connect(lambda err: self._fail(url, err, on_error))
        self._pool.start(worker)
        return worker

    def _deliver(
        self,
        url: str,
        data: bytes,
        on_ready: Callable[[QPixmap], None] | None,
        on_error: Callable[[str], None] | None,
    ) -> None:
        self._disk.store(url, data)
        pixmap = QPixmap()
        if pixmap.isNull() or not pixmap.loadFromData(data):
            logger.debug("No se pudo decodificar la imagen %s", url)
            if on_error:
                on_error("Imagen no válida")
            return
        self._remember(url, pixmap)
        self.image_ready.emit(url, pixmap)
        if on_ready:
            on_ready(pixmap)

    def _fail(self, url: str, error: str, on_error: Callable[[str], None] | None) -> None:
        logger.debug("Error descargando la imagen %s: %s", url, error)
        if on_error:
            on_error(error)

    def clear_memory_cache(self) -> None:
        self._memory.clear()

    def purge_disk_cache(self, max_bytes: int) -> int:
        return self._disk.purge(max_bytes)


_default_image_provider: Optional[ImageProvider] = None


def get_default_image_provider() -> ImageProvider:
    """Instancia compartida de ImageProvider para evitar crear múltiples thread pools."""
    global _default_image_provider
    if _default_image_provider is None:
        _default_image_provider = ImageProvider()
    return _default_image_provider
