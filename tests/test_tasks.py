"""Pruebas de la infraestructura de tareas (QThreadPool + cancelación)."""

from __future__ import annotations

import threading
import time

from core.tasks.worker import TaskGroup, Worker


def test_worker_emits_result(qtbot):
    received = []
    worker = Worker(lambda: 42)
    worker.signals.result.connect(received.append)
    worker.run()
    assert received == [42]


def test_worker_emits_error(qtbot):
    errors = []

    def boom():
        raise ValueError("fallo")

    worker = Worker(boom)
    worker.signals.error.connect(errors.append)
    worker.run()
    assert errors == ["fallo"]


def test_worker_cancelled_before_run():
    results = []
    worker = Worker(lambda: 1)
    worker.signals.result.connect(results.append)
    worker.cancel()
    worker.run()
    assert results == []
    assert worker.cancelled


def test_worker_passes_cancel_event():
    seen = {}

    def task(cancel_event):
        seen["event"] = cancel_event
        return "ok"

    worker = Worker(task)
    worker.run()
    assert isinstance(seen["event"], threading.Event)


def test_task_group_tracks_and_cancels():
    group = TaskGroup()
    worker = Worker(lambda: 1)
    group.add(worker)
    assert len(group) == 1
    group.cancel_all()
    assert worker.cancelled
    worker.run()
    assert len(group) == 0


def test_task_group_wait_returns_when_done():
    group = TaskGroup()
    worker = Worker(lambda: time.sleep(0.01))
    group.add(worker)
    worker.run()
    assert group.wait(1000) is True
