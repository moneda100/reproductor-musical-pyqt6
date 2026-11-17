"""Captura pantallazos de la UI para el informe QA.

Uso::

    python scripts/qa_capture.py

Las imágenes se guardan en ``screenshots/qa/``. Se ejecuta en modo
``offscreen`` con datos de demostración y sin acceso a red.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEMP_HOME = tempfile.mkdtemp(prefix="musicplayerpro-qa-capture-")
os.environ["MUSICPLAYERPRO_HOME"] = _TEMP_HOME

from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontDatabase,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.lyrics import LyricLine  # noqa: E402
from core.player import MusicPlayer  # noqa: E402
from core.playlist import Track  # noqa: E402
from tests.fakes.fake_vlc import FakeVlcModule  # noqa: E402
from ui.main_window import VIEW_INDEX, MainWindow  # noqa: E402

OUTPUT_DIR = ROOT / "screenshots" / "qa"

SONGS = [
    ("Luz de Neón", "Aurora Norte", "Ciudad Eléctrica", 214),
    ("Marea Baja", "Los Cobaltos", "Horizonte", 187),
    ("Cristal", "Nova Sur", "Reflejos", 243),
    ("Ruta 9", "Motor Azul", "Carretera", 198),
    ("Jardín Lunar", "Selva Estelar", "Botánica", 226),
    ("Pulso", "Circuito Abierto", "Señales", 172),
    ("Amanecer", "Alba Roja", "Frontera", 251),
    ("Silencio", "ECO", "Vacío", 205),
]

LYRICS = [
    LyricLine(0, "Se encienden las luces de la ciudad"),
    LyricLine(12_000, "y el asfalto respira otra vez"),
    LyricLine(26_000, "bailamos despacio bajo el neón"),
    LyricLine(41_000, "con la noche cosida a los pies"),
    LyricLine(58_000, "Si el ruido se apaga, quedan las voces"),
    LyricLine(72_000, "y un reflejo de nosotros en el cristal"),
    LyricLine(88_000, "no hay mapa que llegue a este lugar"),
    LyricLine(102_000, "solo el pulso que marca el compás"),
]


def _cover_pixmap(index: int) -> QPixmap:
    palettes = [
        ("#7C3AED", "#22D3EE"),
        ("#F97316", "#FACC15"),
        ("#10B981", "#3B82F6"),
        ("#EC4899", "#8B5CF6"),
        ("#06B6D4", "#14B8A6"),
        ("#F43F5E", "#FB923C"),
        ("#6366F1", "#22D3EE"),
        ("#84CC16", "#10B981"),
    ]
    start, end = palettes[index % len(palettes)]
    pixmap = QPixmap(400, 400)
    painter = QPainter(pixmap)
    try:
        gradient = QLinearGradient(QPointF(0, 0), QPointF(400, 400))
        gradient.setColorAt(0.0, QColor(start))
        gradient.setColorAt(1.0, QColor(end))
        painter.fillRect(pixmap.rect(), gradient)
        painter.setBrush(QColor(255, 255, 255, 45))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(90, 70, 220, 220)
        painter.setBrush(QColor(0, 0, 0, 35))
        painter.drawEllipse(150, 190, 160, 160)
    finally:
        painter.end()
    return pixmap


def _build_tracks() -> list[Track]:
    tracks = []
    for index, (title, artist, album, duration) in enumerate(SONGS):
        tracks.append(
            Track(
                id=f"qa-track-{index}",
                title=title,
                artist=artist,
                album=album,
                file_path=f"/music/qa/{index}.mp3",
                duration=duration,
                cover_url=f"https://qa.local/cover-{index}.jpg",
                source="local",
            )
        )
    return tracks


def _library_entries() -> list[dict]:
    entries = []
    for index, (title, artist, album, duration) in enumerate(SONGS):
        entries.append(
            {
                "path": f"/music/qa/{index}.mp3",
                "filename": f"{index:02d} - {title}.mp3",
                "title": title,
                "artist": artist,
                "album": album,
                "rel_dir": artist,
                "duration": duration,
            }
        )
    return entries


def _load_fonts(app: QApplication) -> None:
    """Carga fuentes del sistema cuando el backend offscreen no tiene ninguna."""
    if QFontDatabase.families():
        return
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        windows_fonts / "segoeui.ttf",
        windows_fonts / "seguiemj.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
    ]
    loaded = []
    for path in candidates:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            loaded.append(families[0])
    if loaded:
        app.setFont(QFont(loaded[0], 10))
        print(f"Fuentes cargadas para las capturas: {', '.join(loaded)}")


def _capture(window: MainWindow, app: QApplication, name: str) -> None:
    app.processEvents()
    QTest.qWait(150)
    app.processEvents()
    pixmap = window.grab()
    path = OUTPUT_DIR / name
    pixmap.save(str(path), "PNG")
    print(f"Captura: {path}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MusicPlayerPro-QA-Capture")
    _load_fonts(app)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    window = MainWindow(player=MusicPlayer(vlc_module=FakeVlcModule()))
    window.lyrics_service.get_lyrics = lambda *a, **k: None
    window.search_controller.search_cover = lambda *a, **k: None
    window.resize(1280, 820)
    window.show()
    QTest.qWait(200)

    tracks = _build_tracks()
    for index, track in enumerate(tracks):
        window.image_provider._memory[track.cover_url] = _cover_pixmap(index)
    window.playlist_controller.add_tracks(tracks)
    window.playback_controller.play_index(0)
    QTest.qWait(200)
    window._on_duration_changed(tracks[0].duration * 1000)
    window._on_position_changed(65_000)
    window.lyrics_panel.set_lyrics(LYRICS)
    window.lyrics_panel.set_position(65_000)

    window.library_controller.set_entries(_library_entries())
    window.library_panel.tree_view.expandAll()
    first_playlist = window.playlist_manager.create("Favoritas")
    window.playlist_manager.add_tracks(first_playlist, tracks[:4])
    second_playlist = window.playlist_manager.create("Para entrenar")
    window.playlist_manager.add_tracks(second_playlist, tracks[4:])

    window.apply_theme("clay_dracula")
    window.sidebar.select("home")
    _capture(window, app, "01_home_clay.png")

    window.stack.setCurrentIndex(VIEW_INDEX["playlist"])
    _capture(window, app, "02_playlist.png")

    window.sidebar.select("library")
    _capture(window, app, "03_library.png")

    window.stack.setCurrentIndex(VIEW_INDEX["lyrics"])
    _capture(window, app, "04_lyrics.png")

    window.sidebar.select("playlists")
    _capture(window, app, "05_playlists.png")

    window.apply_theme("light")
    window.sidebar.select("home")
    _capture(window, app, "06_home_light.png")

    window.close()
    app.processEvents()
    shutil.rmtree(_TEMP_HOME, ignore_errors=True)
    print(f"\nCapturas guardadas en: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
