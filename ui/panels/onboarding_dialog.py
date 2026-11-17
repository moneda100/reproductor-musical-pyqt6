"""Diálogo de bienvenida (onboarding) para la primera ejecución."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.themes import ThemeManager
from ui.widgets import load_icon


class OnboardingDialog(QDialog):
    """Wizard de 3 pasos para la primera ejecución:
    1. Bienvenida + atajos
    2. Añadir carpeta musical
    3. Tema preferido + opciones
    """

    finished_setup = pyqtSignal(str, str)  # music_folder, theme_name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bienvenido a Music Player Pro")
        self.setModal(True)
        self.setFixedSize(560, 420)
        self._music_folder = ""
        self._theme_name = "dark"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, stretch=1)

        # Paso 1: Bienvenida
        self.page_welcome = self._create_welcome_page()
        self.stack.addWidget(self.page_welcome)

        # Paso 2: Carpeta musical
        self.page_folder = self._create_folder_page()
        self.stack.addWidget(self.page_folder)

        # Paso 3: Tema y opciones
        self.page_theme = self._create_theme_page()
        self.stack.addWidget(self.page_theme)

        # Navegación inferior
        nav_bar = QWidget(self)
        nav_bar.setFixedHeight(60)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 12, 24, 12)
        nav_layout.setSpacing(12)

        self.back_btn = QPushButton("← Atrás")
        self.back_btn.setObjectName("SecondaryBtn")
        self.back_btn.setMinimumHeight(36)
        self.back_btn.clicked.connect(self._go_back)
        nav_layout.addWidget(self.back_btn)

        nav_layout.addStretch()

        self.next_btn = QPushButton("Siguiente →")
        self.next_btn.setObjectName("PrimaryBtn")
        self.next_btn.setMinimumHeight(36)
        self.next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self.next_btn)

        self.finish_btn = QPushButton("Comenzar")
        self.finish_btn.setObjectName("PrimaryBtn")
        self.finish_btn.setMinimumHeight(36)
        self.finish_btn.clicked.connect(self._finish)
        self.finish_btn.hide()
        nav_layout.addWidget(self.finish_btn)

        layout.addWidget(nav_bar)

        self._update_nav_buttons()

    def _create_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icono de la app
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_pixmap = load_icon("music", 96).pixmap(96, 96)
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap)
        else:
            icon_label.setText("♪")
            icon_label.setStyleSheet("font-size: 72px; color: #1DB954;")
        layout.addWidget(icon_label)

        title = QLabel("Music Player Pro")
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Tu música local y de YouTube en un solo lugar, con sincronización entre dispositivos.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setMaximumWidth(400)
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Atajos principales
        shortcuts = QLabel(
            "Atajos principales:\n"
            "Espacio — Reproducir/Pausar\n"
            "Ctrl+F — Buscar (yt: para YouTube)\n"
            "Ctrl+←/→ — Pista anterior/siguiente\n"
            "Ctrl+U — Cola de reproducción\n"
            "F1 — Ver todos los atajos"
        )
        shortcuts.setObjectName("HintLabel")
        shortcuts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcuts.setStyleSheet("background: #1E1E1E; border-radius: 12px; padding: 16px;")
        layout.addWidget(shortcuts)

        layout.addStretch()
        return page

    def _create_folder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("¿Dónde está tu música?")
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Selecciona la carpeta donde guardas tus archivos de música (MP3, FLAC, WAV, M4A, OGG, OPUS…). "
            "La app la escaneará automáticamente y mostrará carátulas, artistas y álbumes."
        )
        desc.setObjectName("MutedLabel")
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        self.folder_label = QLabel("Ninguna carpeta seleccionada")
        self.folder_label.setObjectName("HintLabel")
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_label.setStyleSheet("background: #1E1E1E; border-radius: 8px; padding: 12px; min-height: 40px;")
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.choose_folder_btn = QPushButton("📁  Elegir carpeta")
        self.choose_folder_btn.setObjectName("PrimaryBtn")
        self.choose_folder_btn.setMinimumHeight(44)
        self.choose_folder_btn.setMinimumWidth(180)
        self.choose_folder_btn.clicked.connect(self._choose_folder)
        btn_row.addWidget(self.choose_folder_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.skip_folder_btn = QPushButton("Saltar (añadiré música luego)")
        self.skip_folder_btn.setObjectName("GhostBtn")
        self.skip_folder_btn.setMinimumHeight(44)
        self.skip_folder_btn.clicked.connect(lambda: self._go_next())
        btn_row.addWidget(self.skip_folder_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(btn_row)
        layout.addStretch()
        return page

    def _create_theme_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Elige tu tema")
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("Selecciona un tema visual. Puedes cambiarlo después en Ajustes.")
        desc.setObjectName("MutedLabel")
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        # Grid de temas
        from PyQt6.QtWidgets import QButtonGroup, QGridLayout

        themes_grid = QGridLayout()
        themes_grid.setSpacing(12)
        self.theme_btns = {}
        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)

        theme_names = ThemeManager.theme_names()
        # Ordenar: clásicos primero, luego clay
        classic = [t for t in theme_names if not t.startswith("clay_")]
        clay = [t for t in theme_names if t.startswith("clay_")]
        ordered = classic + clay

        for idx, name in enumerate(ordered):
            row, col = divmod(idx, 4)
            btn = QPushButton(name.capitalize().replace("_", " "))
            btn.setCheckable(True)
            btn.setObjectName("ThemeOptionBtn")
            btn.setMinimumSize(110, 80)
            btn.setToolTip(f"Tema {name}")
            btn.clicked.connect(lambda checked, n=name: self._on_theme_selected(n))
            self.theme_btns[name] = btn
            self.theme_group.addButton(btn)
            themes_grid.addWidget(btn, row, col)

        layout.addLayout(themes_grid)

        # Opciones adicionales
        from PyQt6.QtWidgets import QCheckBox

        options_layout = QVBoxLayout()
        options_layout.setSpacing(8)

        self.tray_check = QCheckBox("Mostrar en bandeja del sistema")
        self.tray_check.setChecked(True)
        options_layout.addWidget(self.tray_check)

        self.mini_check = QCheckBox("Activar mini reproductor flotante")
        self.mini_check.setChecked(True)
        options_layout.addWidget(self.mini_check)

        layout.addLayout(options_layout)
        layout.addStretch()
        return page

    def _on_theme_selected(self, name: str) -> None:
        self._theme_name = name
        # Actualizar estilos visuales de los botones
        for n, btn in self.theme_btns.items():
            btn.setProperty("selected", n == name)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecciona tu carpeta de música")
        if folder:
            self._music_folder = folder
            self.folder_label.setText(folder)
            self.folder_label.setToolTip(folder)

    def _go_back(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_nav_buttons()

    def _go_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 1 and not self._music_folder:
            # Permitir saltar carpeta
            pass
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        idx = self.stack.currentIndex()
        self.back_btn.setVisible(idx > 0)
        is_last = idx == self.stack.count() - 1
        self.next_btn.setVisible(not is_last)
        self.finish_btn.setVisible(is_last)

    def _finish(self) -> None:
        self.finished_setup.emit(self._music_folder, self._theme_name)
        self.accept()

    def get_results(self) -> tuple[str, str]:
        return self._music_folder, self._theme_name


def is_first_run() -> bool:
    """Verifica si es la primera ejecución comprobando si existe state.db."""
    from core.paths import get_paths
    return not get_paths().state_db.exists()