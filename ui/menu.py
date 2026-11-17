"""Construcción de la barra de menús y de los atajos de teclado.

Se extrae del ``MainWindow`` para que la ventana quede como orquestador.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QStyleFactory

SHORTCUTS_HELP = (
    "Espacio — reproducir/pausar\n"
    "Ctrl+F — buscar\n"
    "Ctrl+O — abrir archivos\n"
    "Ctrl+L — letras\n"
    "Ctrl+U — cola de reproducción\n"
    "Ctrl+Shift+D — gestor de descargas\n"
    "Ctrl+← / Ctrl+→ — pista anterior/siguiente\n"
    "Ctrl+D — marcar como favorita\n"
    "Ctrl+Q — salir"
)

KEYBOARD_SHORTCUTS = {
    "Ctrl+F": "search",
    "Ctrl+O": "open_files",
    "Ctrl+Q": "quit",
    "Ctrl+U": "toggle_queue",
    "Ctrl+L": "toggle_lyrics",
    "Ctrl+Shift+D": "toggle_downloads",
    "Ctrl+Right": "next",
    "Ctrl+Left": "previous",
    "Ctrl+D": "toggle_favorite",
    "Space": "play_pause",
    "F1": "help",
}


class MenuBuilder:
    """Crea la barra de menús y registra los atajos globales."""

    def __init__(self, window: QMainWindow) -> None:
        self.window = window

    # -- menús ------------------------------------------------------------
    def build(self) -> None:
        window = self.window
        menubar = window.menuBar()

        file_menu = menubar.addMenu("&Archivo")
        self._add(file_menu, "Abrir archivos…", window.open_file_dialog, "Ctrl+O")
        self._add(file_menu, "Añadir carpeta a la biblioteca…", window.add_folder_to_library)
        file_menu.addSeparator()
        self._add(
            file_menu,
            "Gestor de descargas…",
            window.toggle_downloads,
        )
        self._add(file_menu, "Configurar carpeta de descargas…", window.set_download_directory)
        self._add(file_menu, "Ajustes…", window.open_settings)
        file_menu.addSeparator()
        self._add(file_menu, "Salir", window.close, "Ctrl+Q")

        playlist_menu = menubar.addMenu("&Playlist")
        self._add(playlist_menu, "Limpiar playlist", window._clear_playlist)
        self._add(playlist_menu, "Eliminar pista seleccionada", window._remove_selected)
        playlist_menu.addSeparator()
        self._add(playlist_menu, "Guardar playlist", window._save_playlist)
        self._add(playlist_menu, "Cargar playlist", window._load_playlist)
        playlist_menu.addSeparator()
        self._add(playlist_menu, "Buscar duplicados…", window.show_duplicates)
        self._add(playlist_menu, "Editar etiquetas en lote…", window.show_batch_tag_editor)
        playlist_menu.addSeparator()
        self._add(playlist_menu, "Limpiar caché de descargas", window.clear_cache)

        appearance_menu = menubar.addMenu("&Apariencia")
        themes_menu = appearance_menu.addMenu("Temas")
        for theme_name in ("dark", "light", "cyberpunk"):
            self._add(
                themes_menu,
                theme_name.capitalize(),
                lambda checked=False, name=theme_name: window.apply_theme(name),
            )
        styles_menu = appearance_menu.addMenu("Estilos nativos")
        for style in QStyleFactory.keys():
            self._add(
                styles_menu,
                style,
                lambda checked=False, name=style: window.apply_native_style(name),
            )

        view_menu = menubar.addMenu("&Ver")
        self._add(view_menu, "Cola de reproducción", window.toggle_queue, "Ctrl+U")
        self._add(view_menu, "Descargas", window.toggle_downloads, "Ctrl+Shift+D")
        self._add(view_menu, "Letras", window.toggle_lyrics)

        help_menu = menubar.addMenu("A&yuda")
        self._add(help_menu, "Buscar actualizaciones…", window.show_update_dialog)
        self._add(help_menu, "Atajos de teclado", self.show_shortcuts, "F1")

    def _add(self, menu, text: str, slot, shortcut: str = "") -> QAction:
        action = QAction(text, self.window)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # -- atajos -------------------------------------------------------------
    def register_shortcuts(self) -> None:
        window = self.window
        handlers = {
            "search": lambda: window.search_input.setFocus(),
            "open_files": window.open_file_dialog,
            "quit": window.close,
            "toggle_queue": window.toggle_queue,
            "toggle_downloads": window.toggle_downloads,
            "toggle_lyrics": window.toggle_lyrics,
            "next": window.playback_controller.next,
            "previous": window.playback_controller.previous,
            "toggle_favorite": window._toggle_favorite,
            "play_pause": window.playback_controller.toggle_play,
            "help": self.show_shortcuts,
        }
        for key, name in KEYBOARD_SHORTCUTS.items():
            shortcut = QShortcut(QKeySequence(key), window)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(handlers[name])

    @staticmethod
    def show_shortcuts() -> None:
        QMessageBox.information(None, "Atajos de teclado", SHORTCUTS_HELP)
