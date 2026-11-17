"""Controlador de la biblioteca: escaneo de carpetas y carga de la biblioteca."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from core.tasks.library_tasks import LibraryScanTask
from core.tasks.worker import TaskGroup, Worker

logger = logging.getLogger(__name__)


class LibraryController(QObject):
    """Gestiona el escaneo de carpetas musicales."""

    entries_added = pyqtSignal(list)
    batch_added = pyqtSignal(list)
    scan_progress = pyqtSignal(int)
    scan_finished = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        metadata_service,
        pool: Optional[QThreadPool] = None,
        task_group: Optional[TaskGroup] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.pool = pool or QThreadPool(self)
        self.tasks = task_group or TaskGroup()
        self._worker: Optional[Worker] = None
        self._entries: list[dict] = []

    # -- datos ----------------------------------------------------------
    def entries(self) -> list[dict]:
        return list(self._entries)

    def set_entries(self, entries: list[dict]) -> None:
        self._entries = list(entries)
        self.entries_added.emit(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self.entries_added.emit([])

    def find_by_path(self, path: str) -> Optional[dict]:
        for entry in self._entries:
            if entry.get("path") == path:
                return entry
        return None

    # -- escaneo ---------------------------------------------------------
    def scan(self, folder: str) -> None:
        """Escanea una carpeta (cancelando el escaneo anterior)."""
        self.cancel()

        def on_batch(batch: list) -> None:
            self._entries.extend(batch)
            self.batch_added.emit(batch)
            self.scan_progress.emit(len(self._entries))

        task = LibraryScanTask(folder, self.metadata_service, on_batch)
        worker = Worker(task)
        worker.signals.result.connect(lambda _: self.scan_finished.emit(len(self._entries)))
        worker.signals.error.connect(self.error_occurred.emit)
        self.tasks.add(worker)
        self._worker = worker
        self.pool.start(worker)

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
