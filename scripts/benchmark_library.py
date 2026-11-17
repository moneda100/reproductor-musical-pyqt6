"""Banco de pruebas de rendimiento de la biblioteca.

No se ejecuta en el CI (es manual): mide el escaneo, la construcción del
árbol y el cambio de vista con 20 000 pistas.

Uso::

    python scripts/benchmark_library.py --tracks 20000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.models.library_tree_model import LibraryTreeModel, LibraryViewMode  # noqa: E402

TRACKS = 20_000
ACCEPTANCE_MS = 200


def build_entries(count: int) -> list[dict]:
    """Entradas con los ficheros agrupados por carpeta (como un paseo real)."""
    entries = []
    for index in range(count):
        artist = f"Artista {index // 200}"
        album = f"Álbum {(index // 200) % 20}"
        entries.append(
            {
                "path": f"/music/{artist}/{album}/{index}.mp3",
                "filename": f"{index}.mp3",
                "title": f"Título {index}",
                "artist": artist,
                "album": album,
                "rel_dir": f"{artist}/{album}",
                "duration": 180.0,
            }
        )
    return entries


def _measure(model: LibraryTreeModel, entries: list[dict], mode: LibraryViewMode) -> float:
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        model.set_entries(entries, mode)
        best = min(best, (time.perf_counter() - start) * 1000)
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracks", type=int, default=TRACKS)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)

    entries = build_entries(args.tracks)
    model = LibraryTreeModel()

    folders_ms = _measure(model, entries, LibraryViewMode.FOLDERS)
    artists_ms = _measure(model, entries, LibraryViewMode.ARTISTS)
    albums_ms = _measure(model, entries, LibraryViewMode.ALBUMS)

    print(f"Pistas: {args.tracks}")
    print(f"Construcción (carpetas) : {folders_ms:8.1f} ms")
    print(f"Construcción (artistas) : {artists_ms:8.1f} ms")
    print(f"Construcción (álbumes)  : {albums_ms:8.1f} ms")

    worst = max(folders_ms, artists_ms, albums_ms)
    if worst > ACCEPTANCE_MS:
        print(f"FALLO: supera el criterio de aceptacion ({ACCEPTANCE_MS} ms)")
        return 1
    print(f"OK: cumple el criterio de aceptacion (< {ACCEPTANCE_MS} ms)")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
