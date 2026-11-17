"""Genera métricas de rendimiento de la UI para el informe QA.

Uso::

    python scripts/qa_metrics.py

Escribe ``docs/qa/metrics.json`` y muestra el resultado por consola. Se ejecuta
en modo ``offscreen`` y con un ``MUSICPLAYERPRO_HOME`` temporal para no tocar
la configuración real del usuario.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEMP_HOME = tempfile.mkdtemp(prefix="musicplayerpro-qa-")
os.environ["MUSICPLAYERPRO_HOME"] = _TEMP_HOME

from PyQt6.QtCore import QT_VERSION_STR  # noqa: E402
from PyQt6.QtGui import QColor, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.player import MusicPlayer  # noqa: E402
from core.playlist import Track  # noqa: E402
from tests.fakes.fake_vlc import FakeVlcModule  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.models.track_list_model import TrackListModel  # noqa: E402
from ui.themes import ALL_THEMES, ThemeManager  # noqa: E402

PLAYLIST_TRACKS = 1000
LIBRARY_ENTRIES = 1000
MEMORY_TRACKS = 5000


def _track(index: int) -> Track:
    return Track(
        id=f"track{index}",
        title=f"Título {index}",
        artist=f"Artista {index % 50}",
        album=f"Álbum {index % 20}",
        file_path=f"/music/{index}.mp3",
        duration=180.0 + index,
        source="local",
    )


def _library_entries(count: int) -> list[dict]:
    return [
        {
            "path": f"/music/{index}.mp3",
            "filename": f"{index}.mp3",
            "title": f"Canción {index}",
            "artist": f"Artista {index % 50}",
            "album": f"Álbum {index % 20}",
            "rel_dir": ".",
            "duration": 180,
        }
        for index in range(count)
    ]


def _measure(callback):
    started = time.perf_counter()
    result = callback()
    return (time.perf_counter() - started) * 1000, result


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str, background: str) -> float:
    first, second = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (first + 0.05) / (second + 0.05)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MusicPlayerPro-QA-Metrics")

    window_ms, window = _measure(lambda: MainWindow(player=MusicPlayer(vlc_module=FakeVlcModule())))

    theme_times = []
    for name in ThemeManager.theme_names():
        elapsed, stylesheet = _measure(lambda theme_name=name: ThemeManager.get_theme(theme_name))
        assert stylesheet
        theme_times.append(elapsed)

    playlist_tracks = [_track(index) for index in range(PLAYLIST_TRACKS)]
    playlist_ms, _ = _measure(lambda: window.playlist_controller.add_tracks(playlist_tracks))

    library_ms, _ = _measure(
        lambda: window.library_panel.set_entries(_library_entries(LIBRARY_ENTRIES))
    )
    filter_ms, _ = _measure(lambda: window.library_panel.proxy.set_filter_text("Artista 42"))

    cover_path = Path(_TEMP_HOME) / "qa-cover.png"
    cover = QPixmap(600, 600)
    cover.fill(QColor("#224466"))
    cover.save(str(cover_path), "PNG")

    label = window.now_playing_panel.cover_label
    local_ms, _ = _measure(lambda: [label.set_cover(str(cover_path)) for _ in range(20)])
    placeholder_ms, _ = _measure(lambda: [label.set_cover("") for _ in range(20)])

    tracemalloc.start()
    try:
        large_tracks = [_track(index) for index in range(MEMORY_TRACKS)]
        model = TrackListModel()
        model.set_tracks(large_tracks)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    contrasts = {}
    for name, theme in ALL_THEMES.items():
        colors = theme.colors
        contrasts[name] = {
            "text_main": round(_contrast_ratio(colors["TEXT_MAIN"], colors["BG"]), 2),
            "text_muted": round(_contrast_ratio(colors["TEXT_MUTED"], colors["BG_LIST"]), 2),
        }

    minimum = window.minimumSize()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "qt": QT_VERSION_STR,
            "platform": platform.platform(),
            "offscreen": os.environ.get("QT_QPA_PLATFORM") == "offscreen",
        },
        "metrics": {
            "window_build_ms": round(window_ms, 2),
            "theme_generation_ms": {
                "average": round(sum(theme_times) / len(theme_times), 2),
                "max": round(max(theme_times), 2),
            },
            f"playlist_{PLAYLIST_TRACKS}_tracks_ms": round(playlist_ms, 2),
            f"library_{LIBRARY_ENTRIES}_entries_ms": round(library_ms, 2),
            "library_filter_ms": round(filter_ms, 2),
            "cover_local_load_ms": round(local_ms / 20, 2),
            "cover_placeholder_ms": round(placeholder_ms / 20, 2),
            f"memory_{MEMORY_TRACKS}_tracks_peak_mb": round(peak / (1024 * 1024), 2),
            "window_min_size": {"width": minimum.width(), "height": minimum.height()},
            "theme_count": len(ALL_THEMES),
            "contrast_min": {
                "text_main": min(item["text_main"] for item in contrasts.values()),
                "text_muted": min(item["text_muted"] for item in contrasts.values()),
            },
            "contrast_by_theme": contrasts,
        },
        "thresholds": {
            "window_build_ms": 10000,
            "theme_generation_ms": 200,
            "playlist_1000_tracks_ms": 2000,
            "library_1000_entries_ms": 3000,
            "library_filter_ms": 1000,
            "cover_local_load_ms": 60,
            "cover_placeholder_ms": 30,
            "memory_5000_tracks_peak_mb": 35,
            "contrast_min": 4.5,
        },
    }

    output_dir = ROOT / "docs" / "qa"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "metrics.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    window.close()
    app.processEvents()
    shutil.rmtree(_TEMP_HOME, ignore_errors=True)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nMétricas guardadas en: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
