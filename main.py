import os
import sys
from pathlib import Path

# Asegurar que el directorio actual está en el path de Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtGui import QIcon  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.logging_setup import setup_logging  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.panels.onboarding_dialog import OnboardingDialog, is_first_run  # noqa: E402

APP_ICON_PATH = Path(__file__).resolve().parent / "resources" / "icons" / "app_icon.png"


def main():
    # Modo de verificación: la app arranca, escribe el testigo y termina.
    # Lo usa el actualizador automático para confirmar que la nueva versión
    # funciona antes de borrar la copia de seguridad (rollback).
    if "--verify-startup" in sys.argv:
        from core.updater import write_startup_witness

        write_startup_witness()
        return 0

    from PyQt6.QtCore import QCoreApplication

    QCoreApplication.setApplicationName("MusicPlayerPro")
    QCoreApplication.setOrganizationName("MusicPlayerPro")

    setup_logging()
    # Crear la aplicación PyQt6
    app = QApplication(sys.argv)
    app.setApplicationName("MusicPlayerPro")
    app.setOrganizationName("MusicPlayerPro")
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    # Crear la ventana principal (pero no mostrarla aún si hay onboarding)
    window = MainWindow()

    # Onboarding en primera ejecución
    if is_first_run():
        onboarding = OnboardingDialog(window)
        onboarding.finished_setup.connect(lambda folder, theme: _apply_onboarding(window, folder, theme))
        if onboarding.exec() == OnboardingDialog.DialogCode.Accepted:
            window.show()
        else:
            # Usuario canceló: mostrar ventana vacía
            window.show()
    else:
        window.show()

    # Iniciar el bucle de eventos
    sys.exit(app.exec())


def _apply_onboarding(window: MainWindow, music_folder: str, theme_name: str) -> None:
    """Aplica los resultados del onboarding a la ventana principal."""
    if music_folder:
        if music_folder not in window.config.library_dirs:
            window.config.library_dirs.append(music_folder)
            from core.config import save_config
            save_config(window.config)
        window.library_controller.scan(music_folder)
    if theme_name and theme_name != window.config.theme:
        window.apply_theme(theme_name)
        window.config.theme = theme_name
        from core.config import save_config
        save_config(window.config)


if __name__ == "__main__":
    main()
