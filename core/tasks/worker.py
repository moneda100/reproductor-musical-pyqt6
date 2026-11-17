"""Infraestructura de tareas en segundo plano.

Regla dura del proyecto: **VLC solo se toca desde el hilo de la GUI**. Los
workers (``QRunnable``) ejecutados en el ``QThreadPool`` únicamente hacen
I/O (yt-dlp, requests, mutagen, SQLite) y se comunican con la GUI
exclusivamente mediante ``pyqtSignal``.

Cada tarea expone un ``threading.Event`` de cancelación para que la interfaz
pueda abortar operaciones largas (descargas, escaneos) de forma cooperativa.
"""

from __future__ import annotations

import threading
import time
import traceback
from functools import partial
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    """Señales emitidas por un :class:`Worker`."""

    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    cancelled = pyqtSignal()


class Worker(QRunnable):
    """Ejecuta una callable en el ``QThreadPool``.

    Parameters
    ----------
    fn:
        Función a ejecutar. Recibe un argumento opcional ``cancel_event``
        si la callable acepta un parámetro llamado ``cancel_event``.
    args / kwargs:
        Argumentos de la callable.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancel_event = threading.Event()
        self._done_event = threading.Event()

    # -- cancelación ----------------------------------------------
    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    def cancel(self) -> None:
        """Pide la cancelación cooperativa de la tarea."""
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def is_done(self) -> bool:
        return self._done_event.is_set()

    # -- ejecución --------------------------------------------------
    @pyqtSlot()
    def run(self) -> None:
        try:
            if self._cancel_event.is_set():
                self.signals.cancelled.emit()
                return
            if _accepts_cancel(self.fn):
                result = self.fn(*self.args, cancel_event=self._cancel_event, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
            if self._cancel_event.is_set():
                self.signals.cancelled.emit()
                return
            self.signals.result.emit(result)
        except Exception as exc:  # noqa: BLE001 - se reporta a la GUI
            self.signals.error.emit(f"{exc}")
            traceback.print_exc()
        finally:
            self._done_event.set()
            self.signals.finished.emit()


def _accepts_cancel(fn: Callable[..., Any]) -> bool:
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    if "cancel_event" in sig.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


class TaskGroup:
    """Agrupa workers y permite cancelarlos/esperarlos en bloque.

    Sustituye a la antigua lista ``active_threads`` de ``MainWindow``, que
    filtraba hilos terminados pero nunca cancelaba los anteriores (lo que
    provocaba descargas de yt-dlp simultáneas no deseadas).
    """

    def __init__(self) -> None:
        self._workers: list[Worker] = []

    def add(self, worker: Worker) -> Worker:
        self._workers.append(worker)
        # ``partial`` acepta cero argumentos (la señal ``finished`` no lleva
        # ninguno) sin depender de la introspección de lambdas con defaults.
        worker.signals.finished.connect(partial(self._discard, worker))
        return worker

    def _discard(self, worker: Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def cancel_all(self) -> None:
        for worker in list(self._workers):
            worker.cancel()

    def wait(self, msecs: int = 5000) -> bool:
        """Espera a que terminen las tareas. Devuelve ``True`` si todas acabaron."""
        deadline = time.monotonic() + (msecs / 1000.0)
        pending = list(self._workers)
        while pending and time.monotonic() < deadline:
            pending = [w for w in pending if not w.is_done]
            if not pending:
                break
            time.sleep(0.02)
        return not pending

    def __len__(self) -> int:
        return len(self._workers)
