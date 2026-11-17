"""Prueba visual: captura pantallazos de las vistas principales del reproductor."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MusicPlayerPro-VisualTest")

    window = MainWindow()
    window.show()

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots"
    )
    os.makedirs(out_dir, exist_ok=True)

    views = ["home", "library", "playlists", "favorites", "history"]

    def capture_all():
        for i, key in enumerate(views):
            window.sidebar.select(key)
            # Procesar eventos para que la vista se renderice
            app.processEvents()
            QTimer.singleShot(200, lambda k=key: None)
            app.processEvents()
            pixmap = window.grab()
            path = os.path.join(out_dir, f"{key}.png")
            pixmap.save(path)
            print(f"Capturado: {path}")

        # También capturar el panel de controles con una pista
        app.processEvents()
        pixmap = window.grab()
        path = os.path.join(out_dir, "final.png")
        pixmap.save(path)
        print(f"Capturado: {path}")

        app.quit()

    QTimer.singleShot(1000, capture_all)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
