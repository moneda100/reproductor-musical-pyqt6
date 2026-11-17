"""Comprobación de arranque: lanza la app en modo 'offscreen' y verifica que
no se rompe. Uso: python scripts/smoke_start.py [segundos]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0

    from core.logging_setup import setup_logging
    from ui.main_window import MainWindow

    setup_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    state = {"ok": False}

    def finish():
        state["ok"] = True
        app.quit()

    QTimer.singleShot(int(seconds * 1000), finish)
    app.exec()

    print(f"Arranque correcto: {state['ok']}")
    print(f"Playlist inicial: {window.playlist_controller.count} pistas")
    print(f"Tema: {window.config.theme}")
    print(f"Vista activa: {window.sidebar.current_key()}")
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
