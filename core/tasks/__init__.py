"""Infraestructura de tareas en segundo plano sobre ``QThreadPool``."""

from core.tasks.library_tasks import (
    BatchTagWriteTask,
    CoverSearchTask,
    LibraryScanTask,
    MetadataSuggestionsTask,
    iter_audio_files,
)
from core.tasks.worker import TaskGroup, Worker, WorkerSignals
from core.tasks.youtube_tasks import (
    YouTubeBatchDownloadTask,
    YouTubeDownloadTask,
    YouTubePlaylistTask,
    YouTubeSearchTask,
    YouTubeStreamTask,
)

__all__ = [
    "BatchTagWriteTask",
    "CoverSearchTask",
    "LibraryScanTask",
    "MetadataSuggestionsTask",
    "TaskGroup",
    "Worker",
    "WorkerSignals",
    "YouTubeBatchDownloadTask",
    "YouTubeDownloadTask",
    "YouTubePlaylistTask",
    "YouTubeSearchTask",
    "YouTubeStreamTask",
    "iter_audio_files",
]
