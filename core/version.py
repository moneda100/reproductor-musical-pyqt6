"""Versión de la aplicación.

Fuente única de verdad: el ``pyproject.toml`` y la app deben coincidir. La
comprobación automática lee el fichero si está disponible (para no tener que
mantener dos números a mano).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

FALLBACK_VERSION = "1.2.0-beta"


def _read_version_from_pyproject() -> Optional[str]:
    path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else None


APP_VERSION: str = _read_version_from_pyproject() or FALLBACK_VERSION


def parse_version(text: str) -> tuple:
    """Convierte ``"1.2.3"`` en ``(1, 2, 3)`` para comparaciones."""
    parts = []
    for chunk in re.split(r"[.\-+]", (text or "").strip()):
        match = re.match(r"^(\d+)", chunk)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    """``True`` si ``candidate`` es una versión más reciente que ``current``."""
    return parse_version(candidate) > parse_version(current)
