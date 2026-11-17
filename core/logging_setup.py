"""Configuración del logging de la aplicación.

- Consola: nivel INFO.
- Fichero rotativo: nivel DEBUG en ``<AppData>/logs/``.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from core.paths import get_paths

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


class _MaxLevelFilter(logging.Filter):
    """Deja pasar solo los registros hasta ``max_level`` (inclusive)."""

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def setup_logging(
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    log_file: Path | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configura el logging global. Idempotente salvo que se fuerce."""
    global _configured
    root = logging.getLogger()
    if _configured and not force:
        return root

    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(formatter)
    console.addFilter(_MaxLevelFilter(console_level))
    root.addHandler(console)

    try:
        path = log_file or get_paths().log_file
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as exc:  # pragma: no cover - permisos de disco
        root.warning("No se pudo abrir el fichero de log: %s", exc)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
