"""Ventana principal: orquestador de paneles, modelos y controladores.

La ventana solo coordina: la lógica de reproducción vive en
``ui.controllers``, los datos en ``ui.models`` y las vistas en ``ui.panels``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QByteArray, QSize, Qt, QThreadPool, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, load_config, save_config
from core.lyrics import LyricsService
from core.paths import get_paths
from core.player import PlayerState
from core.playlist import RepeatMode, Track
from core.playlist_manager import PlaylistManager
from core.store import LocalStore
from core.tasks.worker import TaskGroup, Worker
from services.audio_detector import AudioDetector, AudioSessionInfo
from services.lastfm_service import LastFmService
from services.media_keys import MediaKeyService
from services.metadata_service import MetadataService
from services.smtc_service import MediaSessionInfo, SMTCService, SMTCStatus
from services.youtube_service import YouTubeService
from ui.components.toast import ToastOverlay
from ui.controllers.files_controller import FilesController
from ui.controllers.library_controller import LibraryController
from ui.controllers.playback_controller import PlaybackController
from ui.controllers.playlist_controller import PlaylistController
from ui.controllers.search_controller import SearchController
from ui.image_provider import ImageProvider
from ui.menu import MenuBuilder
from ui.models.results_model import ResultsModel
from ui.models.track_list_model import TrackListModel
from ui.panels.controls_panel import ControlsPanel
from ui.panels.download_manager import DownloadManagerDialog
from ui.panels.library_panel import LibraryPanel
from ui.panels.lyrics_panel import LyricsPanel
from ui.panels.now_playing import VIDEO_MIN_SIZE, NowPlayingPanel, VideoSizeMode
from ui.panels.playlist_panel import PlaylistPanel
from ui.panels.playlists_panel import PlaylistsPanel
from ui.panels.queue_panel import QueuePanel
from ui.panels.results_panel import ResultsPanel
from ui.panels.settings_dialog import SettingsDialog
from ui.panels.sidebar import Sidebar
from ui.themes import ThemeManager, is_clay_theme
from ui.tray import TrayIcon
from ui.widgets import MiniPlayerWindow

logger = logging.getLogger(__name__)

SEARCH_PAGE_SIZE = 20

VIEW_INDEX = {
    "home": 0,
    "results": 1,
    "playlist": 2,
    "library": 3,
    "favorites": 4,
    "history": 5,
    "lyrics": 6,
    "playlists": 7,
}


class MainWindow(QMainWindow):
    """Ventana principal de Music Player Pro."""

    def __init__(self, player=None) -> None:
        super().__init__()
        self.setWindowTitle("Music Player Pro")
        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icons" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(980, 680)
        self.setAcceptDrops(True)

        self.config: AppConfig = load_config()
        self.paths = get_paths()
        self._unmuted_volume = max(1, int(self.config.volume or 70))
        self._closing = False
        self._last_publish = 0.0
        self._scrobbled_key: Optional[str] = None
        self._video_pending_position: Optional[float] = None
        self._video_pending_was_playing: Optional[bool] = None
        self._restore_position_ms: Optional[int] = None
        self._search_query = ""
        self._search_offset = 0
        self._video_output = "now"
        self._video_track_id = ""
        self._stream_request_position: Optional[float] = None
        self._stream_request_play = True
        self._pending_youtube_query = ""
        self._yt_search_timer = QTimer(self)
        self._yt_search_timer.setSingleShot(True)
        self._yt_search_timer.setInterval(450)
        self._yt_search_timer.timeout.connect(self._run_pending_youtube_search)
        # Guardado diferido del modo/tamaño de vídeo: durante el redimensionado
        # con el ratón no escribimos en disco en cada evento.
        self._video_cfg_timer = QTimer(self)
        self._video_cfg_timer.setSingleShot(True)
        self._video_cfg_timer.setInterval(350)
        self._video_cfg_timer.timeout.connect(self._persist_video_settings)

        # -- servicios --
        self.metadata_service = MetadataService()
        self.youtube_service = YouTubeService()
        self.lyrics_service = LyricsService()
        self.lastfm = LastFmService(
            api_key=self.config.lastfm_api_key,
            username=self.config.lastfm_username,
            session_key=self.config.lastfm_session_key,
        )
        self.store = LocalStore()
        self.playlist_manager = PlaylistManager(self.store, self.paths.playlists_dir)
        self.image_provider = ImageProvider(self)
        self.media_keys = MediaKeyService(self)
        self.smtc = SMTCService(self.config, parent=self)
        self.audio_detector = AudioDetector(self.config, parent=self)

        # -- infraestructura de hilos --
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.tasks = TaskGroup()

        # -- modelos --
        self.track_model = TrackListModel(self)
        self.results_model = ResultsModel(self)
        self.favorites_model = TrackListModel(self)
        self.history_model = TrackListModel(self)

        # -- controladores --
        self.playlist_controller = PlaylistController(model=self.track_model, parent=self)
        self.playback_controller = PlaybackController(
            self.playlist_controller, player=player, parent=self
        )
        self.search_controller = SearchController(
            self.youtube_service, self.metadata_service, self.pool, self.tasks, self
        )
        self.library_controller = LibraryController(
            self.metadata_service, self.pool, self.tasks, self
        )
        self.files_controller = FilesController(self.metadata_service, self, self.pool)

        self._build_ui()
        self._connect_signals()
        self._build_menu()
        self.apply_theme(self.config.theme)
        self._restore_session()
        self._start_integrations()

        # Escuchar cambios de tema del sistema si el tema está en "auto"
        if self.config.theme == "auto":
            try:
                from PyQt6.QtGui import QGuiApplication
                QGuiApplication.styleHints().changed.connect(self._on_system_theme_changed)
            except Exception:
                pass

    # ==================================================================
    # Construcción de la interfaz
    # ==================================================================
    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.splitter.setChildrenCollapsible(False)

        self.sidebar = Sidebar(self.splitter)
        self.splitter.addWidget(self.sidebar)

        content = QWidget(self.splitter)
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 0, 8, 8)
        content_layout.setSpacing(0)

        search_bar = QWidget(content)
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(16, 12, 16, 8)
        self.search_input = QLineEdit(search_bar)
        self.search_input.setPlaceholderText(
            "🔍 Buscar en la biblioteca…  (usa 'yt:' para buscar en YouTube)"
        )
        self.search_input.setAccessibleName("Búsqueda global")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._on_search_submitted)
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input, stretch=1)

        # Búsqueda desactivada por defecto: se habilita con el botón de la derecha.
        self.search_toggle_btn = QPushButton("🔍", search_bar)
        self.search_toggle_btn.setCheckable(True)
        self.search_toggle_btn.setAccessibleName("Activar búsqueda")
        self.search_toggle_btn.setToolTip("Activar búsqueda (Ctrl+F)")
        self.search_toggle_btn.setFixedWidth(38)
        self.search_toggle_btn.toggled.connect(self._on_search_toggled)
        search_layout.addWidget(self.search_toggle_btn)
        self._search_enabled = False
        self._update_search_input_state()

        self.search_hint = QLabel("")
        self.search_hint.setObjectName("StatusLabel")
        self.search_hint.setText(" ")
        search_layout.addWidget(self.search_hint)
        self.smtc_status_label = QLabel("Medios del sistema: --")
        self.smtc_status_label.setObjectName("StatusLabel")
        self.smtc_status_label.setToolTip("Estado de detección de medios del sistema")
        self.smtc_status_label.setAccessibleName("Estado de medios del sistema")
        search_layout.addWidget(self.smtc_status_label)
        content_layout.addWidget(search_bar)

        self.stack = QStackedWidget(content)
        self.now_playing_panel = NowPlayingPanel(self.stack)
        self.results_panel = ResultsPanel(self.results_model, self.stack)
        self.playlist_panel = PlaylistPanel(self.track_model, self.image_provider, self.stack)
        self.library_panel = LibraryPanel(self.stack)
        self.favorites_panel = PlaylistPanel(self.favorites_model, self.image_provider, self.stack)
        self.history_panel = PlaylistPanel(
            self.history_model, self.image_provider, self.stack, title="Historial"
        )
        self.lyrics_panel = LyricsPanel(self.stack)
        self.playlists_panel = PlaylistsPanel(self.stack)

        for panel in (
            self.now_playing_panel,
            self.results_panel,
            self.playlist_panel,
            self.library_panel,
            self.favorites_panel,
            self.history_panel,
            self.lyrics_panel,
            self.playlists_panel,
        ):
            self.stack.addWidget(panel)
        content_layout.addWidget(self.stack, stretch=1)
        self.splitter.addWidget(content)
        self.splitter.setSizes([190, 760])

        self.controls_panel = ControlsPanel(central)
        layout.addWidget(self.splitter, stretch=1)
        layout.addWidget(self.controls_panel)
        self.setCentralWidget(central)

        self.queue_dock = QDockWidget("Cola de reproducción", self)
        self.queue_dock.setObjectName("QueueDock")
        self.queue_panel = QueuePanel(self.track_model, self.image_provider, self.queue_dock)
        self.queue_dock.setWidget(self.queue_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
        self.queue_dock.hide()

        # Gestor de descargas: ventana independiente, no modal y sin mezclarse
        # con la interfaz principal. La ventana solo conserva una referencia.
        self.download_manager = DownloadManagerDialog(
            self,
            destination=self.config.download_dir,
            audio_format=self.config.download_format,
            mode=self.config.download_mode,
        )
        self.downloads_panel = self.download_manager.panel

        # Mini reproductor flotante (comparte el mismo MusicPlayer).
        self.mini_player = MiniPlayerWindow(self, stay_on_top=self.config.mini_stay_on_top)
        self.mini_player.play_toggled.connect(self.playback_controller.toggle_play)
        self.mini_player.next_requested.connect(self.playback_controller.next)
        self.mini_player.previous_requested.connect(self.playback_controller.previous)
        self.mini_player.seek_requested.connect(self._on_mini_seek)
        self.mini_player.volume_changed.connect(self._on_mini_volume_changed)
        self.mini_player.video_toggled.connect(self._on_mini_video_toggled)
        self.mini_player.close_requested.connect(self._on_mini_close)
        self.mini_player.show_requested.connect(self._on_mini_show_main)
        self.mini_player.stay_on_top_changed.connect(self._on_mini_stay_on_top_changed)
        self.mini_player.undock_requested.connect(self._on_mini_undock)
        self.mini_player.dock_requested.connect(self._on_mini_dock)
        self.mini_player.set_volume(self.config.volume)

        self.toasts = ToastOverlay(self)

        # Vincular la superficie de vídeo embebida a VLC para que los vídeos de YouTube
        # permanezcan siempre dentro de la interfaz y no en una ventana externa
        if hasattr(self.now_playing_panel, "video_widget"):
            self.now_playing_panel.video_widget.winId()
            self.playback_controller.player.set_video_widget(
                int(self.now_playing_panel.video_widget.winId())
            )

        # Restaurar el modo y tamaño de vídeo guardados en la configuración.
        # Blindado ante valores corruptos (p. ej. tamaño 0×0 de versiones
        # anteriores): nunca se arranca en pantalla completa ni con tamaños
        # negativos.
        try:
            mode = VideoSizeMode(self.config.video_size_mode)
        except ValueError:
            mode = VideoSizeMode.STANDARD
        if mode == VideoSizeMode.FULLSCREEN:
            mode = VideoSizeMode.STANDARD
        width = max(VIDEO_MIN_SIZE.width(), int(self.config.video_width or 0))
        height = max(VIDEO_MIN_SIZE.height(), int(self.config.video_height or 0))
        self.now_playing_panel.set_video_size_mode(mode)
        self.now_playing_panel.set_video_size(width, height)

    # ==================================================================
    # Señales
    # ==================================================================
    def _connect_signals(self) -> None:
        self.sidebar.navigated.connect(self._on_navigate)

        self.playback_controller.state_changed.connect(self._on_state_changed)
        self.playback_controller.track_changed.connect(self._on_track_changed)
        self.playback_controller.position_changed.connect(self._on_position_changed)
        self.playback_controller.duration_changed.connect(self._on_duration_changed)
        self.playback_controller.error_occurred.connect(self._on_error)
        self.playback_controller.playlist_finished.connect(
            lambda: self._toast("Fin de la lista de reproducción", "info")
        )
        self.playback_controller.stream_required.connect(self._on_stream_required)

        self.controls_panel.play_toggled.connect(self.playback_controller.toggle_play)
        self.controls_panel.next_requested.connect(self.playback_controller.next)
        self.controls_panel.previous_requested.connect(self.playback_controller.previous)
        self.controls_panel.shuffle_toggled.connect(self._on_shuffle_toggled)
        self.controls_panel.repeat_toggled.connect(self._on_repeat_toggled)
        self.controls_panel.seek_requested.connect(self._on_seek_requested)
        self.controls_panel.volume_changed.connect(self._on_volume_changed)
        self.controls_panel.mute_toggled.connect(self._on_mute_toggled)
        self.controls_panel.lyrics_toggled.connect(self.toggle_lyrics)
        self.controls_panel.queue_toggled.connect(self.toggle_queue)

        self.now_playing_panel.video_toggled.connect(self._on_video_toggled)
        self.now_playing_panel.video_size_mode_changed.connect(self._on_video_size_mode_changed)
        self.now_playing_panel.video_fullscreen_requested.connect(
            self._on_video_fullscreen_requested
        )
        self.now_playing_panel.mini_toggled.connect(self._on_mini_toggled)
        self.now_playing_panel.open_folder_requested.connect(self._open_track_folder)
        self.now_playing_panel.favorite_requested.connect(self._toggle_favorite)
        self.now_playing_panel.show_lyrics_requested.connect(self.toggle_lyrics)
        # Atajos de teclado del panel de inicio: todos tienen efecto real.
        self.now_playing_panel.play_toggle_requested.connect(self.playback_controller.toggle_play)
        self.now_playing_panel.seek_relative_requested.connect(self._on_seek_relative)
        self.now_playing_panel.volume_relative_requested.connect(self._on_volume_relative)
        self.now_playing_panel.mute_requested.connect(self._toggle_mute_from_keyboard)
        self.now_playing_panel.fullscreen_toggle_requested.connect(self._toggle_video_fullscreen)

        self.results_panel.download_requested.connect(self._on_download_result)
        self.results_panel.download_selected_requested.connect(self._on_download_selected_results)
        self.results_panel.download_all_requested.connect(self._on_download_all)
        self.results_panel.play_requested.connect(self._on_play_result)
        self.results_panel.play_selected_requested.connect(self._on_play_selected_results)
        self.results_panel.play_all_requested.connect(self._on_play_all_results)
        self.results_panel.play_video_requested.connect(self._on_play_video_result)
        self.results_panel.open_folder_requested.connect(self._on_open_result_folder)
        self.results_panel.add_to_queue_requested.connect(self._on_add_results_to_queue)
        self.results_panel.add_to_favorites_requested.connect(self._on_add_results_to_favorites)
        self.results_panel.add_to_playlist_requested.connect(self._on_add_to_playlist)
        self.results_panel.create_playlist_requested.connect(self._on_create_playlist_with)
        self.results_panel.clear_requested.connect(self._clear_results)
        self.results_panel.load_more_requested.connect(self._on_load_more)
        self.results_panel.status_message.connect(self._toast)

        self.downloads_panel.start_requested.connect(self._start_downloads)
        self.downloads_panel.cancel_requested.connect(self.search_controller.cancel_download)
        self.downloads_panel.open_folder_requested.connect(self._open_download_folder)
        self.downloads_panel.destination_changed.connect(self._on_download_destination_changed)
        self.downloads_panel.format_changed.connect(self._on_download_format_changed)
        self.downloads_panel.mode_changed.connect(self._on_download_mode_changed)
        self.downloads_panel.validation_failed.connect(lambda msg: self._toast(msg, "warning"))

        self.playlist_panel.play_requested.connect(self.playback_controller.play_index)
        self.playlist_panel.play_next_requested.connect(self._play_next_row)
        self.playlist_panel.remove_requested.connect(self.playlist_controller.remove_index)
        self.playlist_panel.clear_requested.connect(self._clear_playlist)
        self.playlist_panel.favorite_requested.connect(self._toggle_favorite_at)
        self.playlist_panel.move_requested.connect(self.playlist_controller.move)
        self.playlist_panel.edit_tags_requested.connect(self._edit_tags_at)
        self.playlist_panel.open_folder_requested.connect(self._open_folder_at)

        self.favorites_panel.play_requested.connect(self._play_favorite)
        self.favorites_panel.favorite_requested.connect(self._remove_favorite_at)
        self.favorites_panel.remove_requested.connect(self._remove_favorite_at)
        self.favorites_panel.clear_requested.connect(self._clear_favorites)

        self.queue_panel.play_requested.connect(self.playback_controller.play_index)
        self.queue_panel.remove_requested.connect(self.playlist_controller.remove_index)
        self.queue_panel.clear_requested.connect(self._clear_playlist)
        self.queue_panel.move_requested.connect(self.playlist_controller.move)
        self.queue_panel.save_as_playlist_requested.connect(self._save_queue_as_playlist)
        self.queue_panel.clear_played_requested.connect(self._clear_played_from_queue)
        self.queue_panel.shuffle_queue_requested.connect(self._shuffle_queue)

        self.history_panel.play_requested.connect(self._play_history_row)
        self.history_panel.remove_requested.connect(self._remove_history_row)
        self.history_panel.clear_requested.connect(self._clear_history)
        self.history_panel.favorite_requested.connect(self._toggle_favorite_history)
        self.history_panel.open_folder_requested.connect(self._open_history_folder)
        self.history_panel.edit_tags_requested.connect(self._edit_tags_history)

        self.library_panel.add_folder_requested.connect(self.add_folder_to_library)
        self.library_panel.clear_requested.connect(self._clear_library)
        self.library_panel.play_requested.connect(self._play_library_path)
        self.library_panel.edit_tags_requested.connect(self._edit_tags_path)
        self.library_panel.view_mode_changed.connect(lambda _: self.library_panel.rebuild())

        self.playlists_panel.create_requested.connect(self._create_playlist)
        self.playlists_panel.rename_requested.connect(self._rename_playlist)
        self.playlists_panel.delete_requested.connect(self._delete_playlist)
        self.playlists_panel.duplicate_requested.connect(self._duplicate_playlist)
        self.playlists_panel.import_requested.connect(self._import_playlist)
        self.playlists_panel.export_requested.connect(self._export_playlist)
        self.playlists_panel.playlist_opened.connect(self._open_playlist)

        self.smtc.status_changed.connect(self._on_smtc_status)
        self.smtc.session_changed.connect(self._on_smtc_session)
        self.audio_detector.status_changed.connect(self._on_audio_detector_status)
        self.audio_detector.session_changed.connect(self._on_audio_detector_session)

        self.search_controller.results_ready.connect(self._on_results_ready)
        self.search_controller.results_appended.connect(self._on_results_appended)
        self.search_controller.error_occurred.connect(self._on_error)
        self.search_controller.download_started.connect(self.downloads_panel.mark_started)
        self.search_controller.download_progress.connect(self._on_download_progress)
        self.search_controller.download_item_started.connect(
            self.downloads_panel.update_item_started
        )
        self.search_controller.download_item_progress.connect(
            self.downloads_panel.update_item_progress
        )
        self.search_controller.download_item_finished.connect(
            self.downloads_panel.update_item_finished
        )
        self.search_controller.download_item_failed.connect(self.downloads_panel.update_item_failed)
        self.search_controller.download_item_ready.connect(self._on_download_item)
        self.search_controller.download_finished.connect(self._on_download_finished)
        self.search_controller.download_cancelled.connect(self._on_download_cancelled)
        self.search_controller.cover_found.connect(self._on_cover_found)
        self.search_controller.stream_found.connect(self._on_stream_found)
        self.search_controller.stream_resolved.connect(self._on_stream_resolved)

        self.library_controller.entries_added.connect(self._on_library_entries)
        self.library_controller.batch_added.connect(self.library_panel.append_entries)
        self.library_controller.scan_finished.connect(self._on_scan_finished)
        self.library_controller.error_occurred.connect(self._on_error)

        self.files_controller.tracks_added.connect(self.playlist_controller.add_tracks)
        self.files_controller.message.connect(self._toast)

    def _build_menu(self) -> None:
        self.menu_builder = MenuBuilder(self)
        self.menu_builder.build()
        self.menu_builder.register_shortcuts()

        # Atajo global para activar/desactivar la búsqueda (Ctrl+F).
        self._search_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._search_shortcut.activated.connect(self._toggle_search_shortcut)

        # Escape sale de la pantalla completa de vídeo.
        self._fullscreen_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._fullscreen_shortcut.activated.connect(self._exit_video_fullscreen)

    def _toggle_search_shortcut(self) -> None:
        self._search_enabled = not self._search_enabled
        self.search_toggle_btn.setChecked(self._search_enabled)
        self._update_search_input_state()

    # ==================================================================
    # Integraciones del sistema (bandeja, teclas multimedia)
    # ==================================================================
    def _start_integrations(self) -> None:
        if self.config.features_tray:
            self.tray = TrayIcon(self)
            self.tray.play_pause_requested.connect(self.playback_controller.toggle_play)
            self.tray.next_requested.connect(self.playback_controller.next)
            self.tray.previous_requested.connect(self.playback_controller.previous)
            self.tray.show_requested.connect(self._show_from_tray)
            self.tray.quit_requested.connect(self.close)
            self.tray.show()

        for action in ("play_pause", "next", "prev", "stop"):
            self.media_keys.register(
                action,
                {
                    "play_pause": self.playback_controller.toggle_play,
                    "next": self.playback_controller.next,
                    "prev": self.playback_controller.previous,
                    "stop": self.playback_controller.stop,
                }[action],
            )
        self.media_keys.start()

        # Barra de medios del sistema (SMTC): detecta qué aplicación reproduce.
        if self.config.features_smtc:
            self.smtc.start()
        # Detector de audio (alternativa a SMTC cuando WinRT no está disponible).
        if self.config.features_audio_detection:
            self.audio_detector.start()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # -- barra de medios del sistema (SMTC) -----------------------------
    def _on_smtc_status(self, status: str) -> None:
        if status == SMTCStatus.UNAVAILABLE:
            self.smtc_status_label.setText("Medios del sistema: no disponible")
        elif status == SMTCStatus.ACTIVE:
            self.smtc_status_label.setText("Medios del sistema: reproduciendo")
        elif status == SMTCStatus.PAUSED:
            self.smtc_status_label.setText("Medios del sistema: en pausa")
        else:
            self.smtc_status_label.setText("Medios del sistema: disponible")

    def _on_smtc_session(self, info: MediaSessionInfo) -> None:
        """Otra aplicación del sistema empezó/detuvo la reproducción."""
        if not isinstance(info, MediaSessionInfo) or not info.title:
            return
        app = info.source_app or info.app_user_model_id or "otra aplicación"
        state = "reproduciendo" if info.is_playing else "en pausa"
        self._toast(
            f"🎵 {app} {state}: «{info.title}»",
            "info",
            4000,
        )
        self._notify_tray(
            f"Otro reproductor: {app}",
            f"{state}: «{info.title}»",
            icon="info",
        )

    def _on_audio_detector_status(self, status: str) -> None:
        """Estado del detector de audio (alternativa a SMTC)."""
        if status == "unavailable":
            self.smtc_status_label.setText("Detector de audio: no disponible")
        elif status == "active":
            self.smtc_status_label.setText("Detector de audio: reproduciendo")
        else:
            self.smtc_status_label.setText("Detector de audio: disponible")

    def _on_audio_detector_session(self, info: AudioSessionInfo) -> None:
        """Se detectó otra aplicación reproduciendo audio (vía Core Audio)."""
        if not info.is_playing:
            return
        name = info.display_name or info.process_name or f"PID {info.process_id}"
        self._toast(
            f"🔊 {name} está reproduciendo audio",
            "info",
            4000,
        )
        self._notify_tray(
            "Audio detectado en otra aplicación",
            f"{name} está reproduciendo audio",
            icon="info",
        )

    def _notify_tray(self, title: str, message: str, icon: str = "info") -> None:
        """Muestra una notificación en la bandeja del sistema si está disponible."""
        if not hasattr(self, "tray") or self.tray is None:
            return
        try:
            qicon = self.tray.icon()
            self.tray.showMessage(title, message, qicon, 5000)
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # Navegación y búsqueda
    # ==================================================================
    def _on_navigate(self, key: str) -> None:
        if (
            key != "home"
            and self._video_output == "now"
            and self.now_playing_panel.video_toggle_btn.isChecked()
        ):
            # Si el usuario navega fuera de la vista principal con vídeo activo,
            # lo pasamos al mini reproductor para mantener el vídeo incrustado
            # en la aplicación y evitar que VLC abra una ventana flotante.
            self._video_output = "mini"
            self.mini_player.show()
            self.mini_player.raise_()
            self._prepare_video_output()
        elif key == "home" and self._video_output == "mini" and self.mini_player.isVisible():
            self._video_output = "now"
            self.mini_player.set_video_enabled(False)
            self._prepare_video_output()

        self.stack.setCurrentIndex(VIEW_INDEX.get(key, 0))
        if key == "favorites":
            self.favorites_model.set_tracks(self._tracks_from_rows(self.store.favorites()))
        elif key == "history":
            self.history_model.set_tracks(self._tracks_from_rows(self.store.history()))
        elif key == "playlists":
            self.playlists_panel.set_playlists(self.playlist_manager.list_playlists())

    def _on_search_changed(self, text: str) -> None:
        if not self._search_enabled:
            return
        query = text.strip()
        if query.lower().startswith("yt:"):
            self.library_panel.proxy.set_filter_text("")
            self._pending_youtube_query = query[3:].strip()
            if self._pending_youtube_query:
                self.search_hint.setText("Escribiendo búsqueda de YouTube…")
                self._yt_search_timer.start()
            return
        self._yt_search_timer.stop()
        self.search_hint.setText("")
        self.library_panel.proxy.set_filter_text(query)
        if query:
            self._show_local_results(query)

    def _run_pending_youtube_search(self) -> None:
        query = self._pending_youtube_query
        if query:
            self._start_youtube_search(query)

    def _start_youtube_search(self, query: str) -> None:
        """Lanza una búsqueda nueva (página 1) y reinicia la paginación."""
        query = query.strip()
        if not query:
            return
        self._yt_search_timer.stop()
        self._search_query = query
        self._search_offset = 0
        self.results_panel.show_load_more(False)
        self.search_hint.setText("Buscando en YouTube…")
        self.search_controller.search(query, max_results=SEARCH_PAGE_SIZE, offset=0)

    def _on_load_more(self) -> None:
        """Pide la siguiente página de la búsqueda activa."""
        if not self._search_query or self.results_panel.is_loading_more():
            return
        self.results_panel.set_loading_more(True)
        self.search_hint.setText("Cargando más resultados…")
        self.search_controller.search(
            self._search_query,
            max_results=SEARCH_PAGE_SIZE,
            offset=self._search_offset,
        )

    def _on_search_toggled(self) -> None:
        self._search_enabled = self.search_toggle_btn.isChecked()
        self._update_search_input_state()

    def _update_search_input_state(self) -> None:
        if self._search_enabled:
            self.search_input.setEnabled(True)
            self.search_input.setFocus()
            self.search_toggle_btn.setText("\U0001f50d")
            self.search_toggle_btn.setToolTip("Desactivar búsqueda (Ctrl+F)")
        else:
            self.search_input.setEnabled(False)
            self.search_input.clear()
            if hasattr(self, "library_panel"):
                self.library_panel.proxy.set_filter_text("")
            self.search_toggle_btn.setText("\U0001f50d")
            self.search_toggle_btn.setToolTip("Activar búsqueda (Ctrl+F)")

    def _on_search_submitted(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        if query.lower().startswith("yt:"):
            self._start_youtube_search(query[3:].strip())
            return
        if "youtube.com" in query or "youtu.be" in query:
            if "list=" in query:
                self.search_controller.load_playlist(query)
            else:
                self._choose_url_action(query)
            return
        self._show_local_results(query)

    def _choose_url_action(self, url: str) -> None:
        """Pregunta si el enlace pegado debe reproducirse o descargarse."""
        box = QMessageBox(self)
        box.setWindowTitle("Enlace de YouTube")
        box.setText("¿Qué quieres hacer con este vídeo?")
        box.setIcon(QMessageBox.Icon.Question)
        stream_btn = box.addButton("▶ Reproducir en streaming", QMessageBox.ButtonRole.AcceptRole)
        download_btn = box.addButton("⬇️ Descargar", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is stream_btn:
            self._on_play_result(self._result_from_url(url))
        elif clicked is download_btn:
            self._download_url_now(url)

    def _show_local_results(self, query: str) -> None:
        needle = query.casefold()
        matches = []
        for entry in self.library_controller.entries():
            haystack = (
                f"{entry.get('title', '')} {entry.get('artist', '')} {entry.get('album', '')}"
            )
            if needle in haystack.casefold():
                matches.append(
                    {
                        "title": entry.get("title", ""),
                        "artist": entry.get("artist", ""),
                        "duration": entry.get("duration", 0),
                        "path": entry.get("path", ""),
                        "cover_url": "",
                        "source": "local",
                    }
                )
        self._search_query = ""
        self.results_panel.set_playlists(self.playlist_manager.list_playlists())
        self.results_panel.set_results(matches, "Biblioteca local")
        self.results_panel.show_load_more(False)
        self.stack.setCurrentIndex(VIEW_INDEX["results"])

    def _clear_results(self) -> None:
        self._search_query = ""
        self._search_offset = 0
        self.results_model.clear()
        self.results_panel.set_results([], "Resultados")
        self.results_panel.show_load_more(False)

    # ==================================================================
    # Descargas
    # ==================================================================
    def _youtube_results(self) -> list[dict]:
        return [
            result
            for result in self.results_model.results()
            if result.get("source") != "local" and result.get("url")
        ]

    def _on_download_result(self, result: dict) -> None:
        if result.get("source") == "local":
            self.files_controller.add_files([result.get("path", "")])
            return
        results = self._youtube_results()
        if result not in results:
            results.append(result)
        self._prepare_downloads(
            results,
            mode="individual",
            selected_urls=[result.get("url", "")],
        )

    def _on_download_all(self) -> None:
        results = self._youtube_results()
        if results:
            self._prepare_downloads(results, mode="playlist", selected_urls=None)
        else:
            self._toast("No hay canciones de YouTube para descargar", "warning")

    def _prepare_downloads(
        self,
        results: list[dict],
        mode: str,
        selected_urls: list[str] | None,
    ) -> None:
        results = [r for r in results if r.get("url") and r.get("source") != "local"]
        if not results:
            self._toast("No hay canciones de YouTube para descargar", "warning")
            return
        self.downloads_panel.set_items(results, mode=mode, selected_urls=selected_urls)
        self.download_manager.show_and_raise()

    def _start_downloads(self, items: list) -> None:
        if not items:
            self._toast("Selecciona al menos una canción", "warning")
            return
        destination = self.downloads_panel.destination()
        if not destination:
            self._toast("Elige una carpeta de destino", "warning")
            return
        try:
            self.youtube_service.set_download_dir(destination)
        except OSError as exc:
            self._toast(f"No se puede usar esa carpeta: {exc}", "error")
            return

        self.config.download_dir = destination
        self.config.download_format = self.downloads_panel.audio_format()
        self.config.download_mode = self.downloads_panel.mode()
        save_config(self.config)

        self.download_manager.show_and_raise()
        self.search_controller.download_all(
            items,
            permanent=True,
            audio_format=self.config.download_format,
        )

    def _open_download_folder(self) -> None:
        folder = self.downloads_panel.destination()
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            self._toast("La carpeta de destino no existe todavía", "warning")

    def _on_download_destination_changed(self, folder: str) -> None:
        if not folder:
            return
        try:
            self.youtube_service.set_download_dir(folder)
        except OSError as exc:
            self._toast(f"No se puede usar esa carpeta: {exc}", "error")
            return
        self.config.download_dir = folder
        save_config(self.config)

    def _on_download_format_changed(self, audio_format: str) -> None:
        self.config.download_format = audio_format
        save_config(self.config)

    def _on_download_mode_changed(self, mode: str) -> None:
        self.config.download_mode = mode
        save_config(self.config)

    def _on_download_progress(self, index: int, total: int, item: dict) -> None:
        title = str(item.get("title", ""))[:30]
        self._toast(f"📥 Descargando {index + 1}/{total}: {title}", "progress", 2000)

    def _on_download_item(self, track: Track) -> None:
        self.playlist_controller.add_track(track)
        self._toast(f"✅ «{track.title}» lista para reproducir", "success")
        self.stack.setCurrentIndex(VIEW_INDEX["playlist"])
        if not self.playback_controller.is_playing():
            self.playback_controller.play_index(self.playlist_controller.count - 1)

    def _on_download_finished(self, tracks: list) -> None:
        self.downloads_panel.finish_batch()
        if tracks:
            self.playlist_controller.add_tracks(tracks)
        self._toast(f"✅ Descarga finalizada: {len(tracks)} pistas", "success")
        self._notify_tray(
            "Descarga finalizada",
            f"{len(tracks)} pista(s) descargada(s)",
            icon="info",
        )

    def _on_download_cancelled(self) -> None:
        self.downloads_panel.mark_cancelled()
        self._toast("Descarga cancelada", "info")
        self._notify_tray(
            "Descarga cancelada",
            "La descarga se ha cancelado",
            icon="warning",
        )

    def _download_url_now(self, url: str) -> None:
        """Descarga directa de una URL: abre el gestor y empieza de inmediato."""
        item = {"url": url, "title": url, "artist": "YouTube", "source": "youtube"}
        self._prepare_downloads([item], mode="individual", selected_urls=[url])
        self.downloads_panel.start()

    # ==================================================================
    # Reproducción de resultados (streaming) y playlists
    # ==================================================================
    def _track_from_result(self, result: dict) -> Track:
        source = result.get("source", "youtube")
        is_youtube = source != "local"
        
        # Para YouTube, usar el uploader (canal) como artista si está disponible
        artist = result.get("artist")
        if is_youtube and not artist:
            # Fallback: el uploader ya debería venir en "artist" desde el servicio
            artist = "YouTube"
        elif not artist:
            artist = "Desconocido"
        
        # Para YouTube, usar la playlist como álbum si está disponible
        album = result.get("album")
        if is_youtube and not album:
            album = result.get("playlist", "YouTube")
        elif not album:
            album = "Desconocido"
        
        return Track(
            id=str(result.get("id") or result.get("url") or result.get("path") or ""),
            title=str(result.get("title", "")),
            artist=str(artist),
            album=str(album),
            file_path=str(result.get("path", "") or ""),
            duration=float(result.get("duration", 0) or 0),
            cover_url=result.get("thumbnail") or result.get("cover_url"),
            source=source,
        )

    def _result_from_url(self, url: str) -> dict:
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/").split("/")[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        return {
            "id": video_id or url,
            "title": "Vídeo de YouTube",
            "artist": "YouTube",
            "url": url,
            "duration": 0,
            "source": "youtube",
        }

    def _on_play_result(self, result: dict) -> None:
        """Reproduce un resultado: local al instante o YouTube en streaming."""
        if not result:
            return
        track = self._track_from_result(result)
        if result.get("source") == "local" and not track.file_path:
            self._toast("El archivo local no está disponible", "warning")
            return
        existing = self.playlist_controller.index_of(track)
        if existing < 0:
            self.playlist_controller.add_track(track)
            existing = self.playlist_controller.count - 1
        self.playback_controller.play_index(existing)

    def _on_play_video_result(self, result: dict) -> None:
        """Reproduce un vídeo de YouTube forzando el modo vídeo incrustado en la interfaz."""
        if not result or result.get("source") == "local":
            self._on_play_result(result)
            return
        track = self._track_from_result(result)
        existing = self.playlist_controller.index_of(track)
        if existing < 0:
            self.playlist_controller.add_track(track)
            existing = self.playlist_controller.count - 1
        self._video_output = "now"
        self.mini_player.set_video_enabled(False)
        self.now_playing_panel.set_video_enabled(True)
        self.sidebar.select("home")
        self.playback_controller.play_index(existing)

    def _on_play_all_results(self, results: list[dict]) -> None:
        if not results:
            self._toast("No hay resultados para reproducir", "warning")
            return
        tracks = [self._track_from_result(r) for r in results]
        self.playlist_controller.clear()
        self.playlist_controller.add_tracks(tracks)
        self.playback_controller.play_index(0)
        self._toast(f"▶ Reproduciendo todos los resultados ({len(tracks)} canciones)", "success")

    def _on_play_selected_results(self, results: list[dict]) -> None:
        if not results:
            return
        if len(results) == 1:
            self._on_play_result(results[0])
            return
        tracks = [self._track_from_result(r) for r in results]
        start_idx = self.playlist_controller.count
        self.playlist_controller.add_tracks(tracks)
        self.playback_controller.play_index(start_idx)
        self._toast(f"▶ Reproduciendo {len(tracks)} canciones seleccionadas", "success")

    def _on_add_results_to_queue(self, results: list[dict]) -> None:
        if not results:
            return
        tracks = [self._track_from_result(r) for r in results]
        self.playlist_controller.add_tracks(tracks)
        self._toast(f"➕ {len(tracks)} canción(es) añadida(s) a la cola", "success")

    def _on_add_results_to_favorites(self, results: list[dict]) -> None:
        if not results:
            return
        for r in results:
            track = self._track_from_result(r)
            if not self.store.is_favorite(track.track_key):
                self.store.add_favorite(track)
        self.favorites_model.set_tracks(self._tracks_from_rows(self.store.favorites()))
        self._toast(f"⭐ {len(results)} canción(es) añadida(s) a favoritos", "success")

    def _on_download_selected_results(self, results: list[dict]) -> None:
        yt_results = [r for r in results if r.get("source") != "local" and r.get("url")]
        if not yt_results:
            self._toast("No hay canciones de YouTube seleccionadas para descargar", "warning")
            return
        self._prepare_downloads(
            yt_results,
            mode="playlist" if len(yt_results) > 1 else "individual",
            selected_urls=[r.get("url") for r in yt_results],
        )

    def _on_open_result_folder(self, result: dict) -> None:
        path = str(result.get("path", "") or "")
        if not path or not os.path.exists(path):
            self._toast("No se encontró el archivo", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(path))))

    def _on_add_to_playlist(self, result_or_results: dict | list, playlist_id: str) -> None:
        if not result_or_results or not playlist_id:
            return
        results = (
            [result_or_results] if isinstance(result_or_results, dict) else list(result_or_results)
        )
        tracks = []
        for r in results:
            track = self._track_from_result(r)
            if track.is_youtube:
                # Sin archivo local: se resolverá el stream al reproducirla.
                track.file_path = ""
            tracks.append(track)
        self.playlist_manager.add_tracks(playlist_id, tracks)
        playlist = self.playlist_manager.get(playlist_id) or {}
        self._refresh_playlists()
        name = playlist.get("name", "la playlist")
        if len(tracks) == 1:
            self._toast(f"«{tracks[0].title}» añadida a {name}", "success")
        else:
            self._toast(f"{len(tracks)} canciones añadidas a {name}", "success")

    def _on_create_playlist_with(self, result_or_results: dict | list) -> None:
        if not result_or_results:
            return
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Nueva playlist", "Nombre de la playlist:")
        if not ok or not name.strip():
            return
        playlist_id = self.playlist_manager.create(name.strip())
        self._on_add_to_playlist(result_or_results, playlist_id)

    def _on_results_ready(self, results: list, title: str) -> None:
        query = self.search_controller.last_query
        is_search = bool(query)
        self._search_query = query if is_search else ""
        self._search_offset = len(results) if is_search else 0
        self.results_panel.set_playlists(self.playlist_manager.list_playlists())
        self.results_panel.set_results(results, title)
        self.results_panel.show_load_more(is_search and len(results) >= SEARCH_PAGE_SIZE)
        self.search_hint.setText("")
        self.stack.setCurrentIndex(VIEW_INDEX["results"])
        if not results:
            self._toast("Sin resultados", "info")

    def _on_results_appended(self, results: list, query: str) -> None:
        if query.strip() != self._search_query:
            return
        self.results_panel.set_loading_more(False)
        self.search_hint.setText("")
        if not results:
            self.results_panel.show_load_more(False)
            self._toast("No hay más resultados", "info")
            return
        self.results_panel.append_results(results)
        self._search_offset = self.results_model.rowCount()
        self.results_panel.show_load_more(len(results) >= SEARCH_PAGE_SIZE)

    # ==================================================================
    # Reproducción
    # ==================================================================
    def _on_state_changed(self, state: PlayerState) -> None:
        self.controls_panel.set_playing(state == PlayerState.PLAYING)
        self.mini_player.set_playing(state == PlayerState.PLAYING)
        if hasattr(self, "tray"):
            self.tray.set_playing(state == PlayerState.PLAYING)
        if state == PlayerState.PLAYING:
            track = self.playback_controller.playlist.current_track()
            if track:
                self._notify_tray(
                    "Reproduciendo",
                    f"«{track.title}» — {track.artist or 'Desconocido'}",
                    icon="info",
                )
        elif state == PlayerState.PAUSED:
            self._notify_tray(
                "Reproducción pausada",
                "El reproductor está en pausa",
                icon="info",
            )

    def _on_track_changed(self, track: Track) -> None:
        if track is None:
            return
        if self._restore_position_ms is not None:
            pos = self._restore_position_ms
            self._restore_position_ms = None
            # Esperar a que VLC reporte la duración antes de hacer seek
            QTimer.singleShot(100, lambda: self.playback_controller.seek(pos / 1000.0))
        # Inicializar inmediatamente el rango de tiempo y slider con la duración conocida
        if track.duration and track.duration > 0:
            self._on_duration_changed(int(track.duration * 1000))
        self.controls_panel.set_position(0.0, track.duration or 0.0)
        self.mini_player.set_position(0.0, track.duration or 0.0)

        self.now_playing_panel.set_track_info(track.title, track.artist, track.album)
        self.mini_player.set_track_info(track.title, track.artist, track.album)
        self.mini_player.set_video_available(track.is_youtube)
        is_fav = self.store.is_favorite(track.track_key)
        self.now_playing_panel.set_favorite_state(is_fav)
        self.playlist_controller.model.set_current_index(self.playlist_controller.index_of(track))
        self.store.add_history(track)
        self._remember_binding(track)
        if hasattr(self, "tray"):
            self.tray.set_track(track.title, track.artist)
        self._update_cover(track)
        self._load_lyrics(track)
        self.now_playing_panel.set_media_info(self.playback_controller.current_media_info())
        self._scrobble_now_playing(track)

        # Mostrar los controles de vídeo solo cuando la pista tiene vídeo.
        self.now_playing_panel.set_video_available(track.is_youtube)

        # Configurar modo de vídeo si es una pista de YouTube
        if track.is_youtube:
            wants_video = self._wants_video()
            if wants_video and self._video_track_id != track.youtube_id:
                # La pista acaba de cargarse en audio y el usuario quiere vídeo.
                self._prepare_video_output()
                self._request_stream(track, video=True, keep_position=True)
            elif not wants_video:
                if self._video_output == "now":
                    self.now_playing_panel.set_video_enabled(False)
                self._video_track_id = ""
        else:
            self._video_track_id = ""
            self.now_playing_panel.set_video_enabled(False)
            self.mini_player.set_video_enabled(False)
            self.mini_player.set_video_available(False)
            if self._video_output == "mini":
                self._video_output = "now"

    def _remember_binding(self, track: Track) -> None:
        """Guarda la ruta local de la pista (nunca para streams remotos)."""
        path = track.file_path or ""
        if path and not str(path).startswith("http"):
            self.store.set_binding(track.track_key, path)

    def _on_position_changed(self, position_ms: int) -> None:
        duration = self.controls_panel.slider.maximum()
        if duration <= 0:
            current = self.playlist_controller.current_track()
            if current and current.duration:
                duration = int(current.duration)
            else:
                player_duration = self.playback_controller.player.get_duration()
                if player_duration > 0:
                    duration = int(player_duration)
        self.controls_panel.set_position(position_ms / 1000.0, duration)
        self.mini_player.set_position(position_ms / 1000.0, duration)
        self.lyrics_panel.set_position(position_ms)
        self._maybe_scrobble(position_ms / 1000.0)

    def _on_duration_changed(self, duration_ms: int) -> None:
        if duration_ms > 0:
            # El slider trabaja en segundos para que coincida con position_ms/1000.
            max_seconds = max(0, int(duration_ms / 1000))
            self.controls_panel.slider.setRange(0, max_seconds)
            from ui.panels.controls_panel import format_time

            self.controls_panel.duration_label.setText(format_time(max_seconds))
            min_w = 60 if max_seconds >= 3600 else 45
            self.controls_panel.duration_label.setMinimumWidth(min_w)
            self.controls_panel.time_label.setMinimumWidth(min_w)
            self.mini_player.set_position(self.controls_panel.slider.value(), max_seconds)

    def _on_error(self, message: str) -> None:
        logger.warning("Error reported by the player: %s", message)
        if self.results_panel.is_loading_more():
            self.results_panel.set_loading_more(False)
        self._toast(f"❌ {message}", "error", 6000)

    def _on_seek_requested(self, seconds: int) -> None:
        self.playback_controller.seek(float(seconds))

    def _on_seek_relative(self, delta: int) -> None:
        """Atajo ←/→: adelanta o retrocede sin salir del rango válido."""
        maximum = self.controls_panel.slider.maximum()
        if maximum <= 0:
            return
        target = self.controls_panel.slider.value() + int(delta)
        target = max(0, min(maximum, target))
        self.playback_controller.seek(float(target))

    def _on_volume_relative(self, delta: int) -> None:
        """Atajo ↑/↓: sube o baja el volumen en pasos del 5 %."""
        value = self.controls_panel.volume_slider.value() + int(delta)
        self.controls_panel.volume_slider.setValue(max(0, min(100, value)))

    def _on_volume_changed(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if value > 0:
            self._unmuted_volume = value
            if self.controls_panel.mute_btn.isChecked():
                self.controls_panel.set_muted(False)
        self.playback_controller.set_volume(value)
        self.config.volume = value
        self.mini_player.set_volume(value)

    def _on_mute_toggled(self, muted: bool) -> None:
        """Silencia restaurando después el volumen previo."""
        self.controls_panel.set_muted(bool(muted))
        if muted:
            current = int(self.controls_panel.volume_slider.value())
            if current > 0:
                self._unmuted_volume = current
            self.controls_panel.volume_slider.blockSignals(True)
            self.controls_panel.volume_slider.setValue(0)
            self.controls_panel.volume_slider.blockSignals(False)
            self.playback_controller.set_volume(0)
            self.mini_player.set_volume(0)
        else:
            self.controls_panel.volume_slider.setValue(max(1, self._unmuted_volume))

    def _toggle_mute_from_keyboard(self) -> None:
        self.controls_panel.mute_btn.toggle()

    def _toggle_video_fullscreen(self) -> None:
        """Doble clic en el vídeo o tecla F: entrar/salir de pantalla completa."""
        if self.isFullScreen():
            self._exit_video_fullscreen()
            return
        if self.now_playing_panel.content_stack.currentWidget() is (
            self.now_playing_panel.video_stage
        ):
            self._on_video_fullscreen_requested(True)

    def _on_shuffle_toggled(self, enabled: bool) -> None:
        self.playlist_controller.playlist.shuffle = enabled
        self.config.shuffle = enabled

    def _on_repeat_toggled(self) -> None:
        current = self.playlist_controller.playlist.repeat_mode
        mapping = {
            RepeatMode.NONE: (RepeatMode.ALL, "all"),
            RepeatMode.ALL: (RepeatMode.ONE, "one"),
            RepeatMode.ONE: (RepeatMode.NONE, "none"),
        }
        new_mode, key = mapping[current]
        self.playlist_controller.playlist.repeat_mode = new_mode
        self.controls_panel.set_repeat_mode(key)
        self.config.repeat_mode = key

    # -- scrobbling ------------------------------------------------------
    def _scrobble_now_playing(self, track: Track) -> None:
        if not self.config.features_lastfm or not self.lastfm.configured:
            return
        worker = Worker(self.lastfm.now_playing, track)
        self.tasks.add(worker)
        self.pool.start(worker)

    def _maybe_scrobble(self, position_seconds: float) -> None:
        if not self.config.features_lastfm or not self.lastfm.configured:
            return
        track = self.playlist_controller.current_track()
        if track is None or not self.lastfm.should_scrobble(position_seconds, track.duration or 0):
            return
        if self._scrobbled_key == track.track_key:
            return
        self._scrobbled_key = track.track_key
        worker = Worker(self.lastfm.scrobble, track)
        self.tasks.add(worker)
        self.pool.start(worker)

    # -- carátulas --------------------------------------------------------
    def _update_cover(self, track: Track) -> None:
        cover = track.cover_url
        needs_search = False
        if not cover:
            needs_search = True
        elif not str(cover).startswith("http"):
            needs_search = not os.path.exists(str(cover))
        elif self.metadata_service.is_generic_cover(str(cover)):
            needs_search = True

        if needs_search:
            # --- Nuevo: intentar extraer la portada del archivo local primero ---
            file_path = getattr(track, "file_path", "") or ""
            if file_path and os.path.exists(file_path):
                meta = self.metadata_service.get_metadata(file_path, with_cover=True)
                cover_data = meta.get("cover_data")
                if cover_data:
                    saved = self.metadata_service.save_cover(cover_data)
                    if saved:
                        track.cover_url = saved
                        self.now_playing_panel.cover_label.set_cover(saved, self.image_provider)
                        self.mini_player.set_cover(saved, self.image_provider)
                        return

            self.now_playing_panel.cover_label.set_cover("")
            self.mini_player.set_cover("", self.image_provider)
            self.search_controller.search_cover(track.artist, track.album)
        else:
            self.now_playing_panel.cover_label.set_cover(str(cover), self.image_provider)
            self.mini_player.set_cover(str(cover), self.image_provider)

    def _current_cover_source(self) -> str:
        track = self.playlist_controller.current_track()
        if track is None:
            return ""
        cover = track.cover_url or ""
        if str(cover).startswith("http"):
            return str(cover)
        if cover and os.path.exists(str(cover)):
            return str(cover)
        return ""

    def _on_cover_found(self, url: str) -> None:
        if not url:
            return
        track = self.playlist_controller.current_track()
        if track is None:
            return
        track.cover_url = url
        self.now_playing_panel.cover_label.set_cover(url, self.image_provider)
        self.mini_player.set_cover(url, self.image_provider)

    # -- letras ------------------------------------------------------------
    def toggle_lyrics(self) -> None:
        if self.stack.currentIndex() == VIEW_INDEX["lyrics"]:
            self.stack.setCurrentIndex(VIEW_INDEX["home"])
            return
        self.stack.setCurrentIndex(VIEW_INDEX["lyrics"])
        track = self.playlist_controller.current_track()
        if track is not None and not self.lyrics_panel._lines:
            self._load_lyrics(track)

    def _load_lyrics(self, track: Track) -> None:
        if not self.config.features_lyrics:
            return
        self.lyrics_panel.set_loading(True)

        def task(cancel_event=None):
            return self.lyrics_service.get_lyrics(
                track.track_key,
                track.title,
                track.artist,
                track.album,
                track.duration,
                is_youtube=track.is_youtube,
                video_id=track.youtube_id if track.is_youtube else None,
                file_path=track.file_path if not track.is_youtube else None,
            )

        worker = Worker(task)
        worker.signals.result.connect(self._on_lyrics_loaded)
        self.tasks.add(worker)
        self.pool.start(worker)

    def _on_lyrics_loaded(self, payload) -> None:
        if not payload:
            self.lyrics_panel.set_no_lyrics()
            return
        self.lyrics_panel.set_lyrics(payload.get("synced", []), payload.get("plain", ""))

    # -- vídeo y streaming -------------------------------------------------
    def _wants_video(self) -> bool:
        """¿El usuario quiere ver vídeo en la superficie activa?"""
        if self._video_output == "mini":
            return self.mini_player.video_enabled()
        return self.now_playing_panel.video_toggle_btn.isChecked()

    def _active_video_widget(self):
        if self._video_output == "mini":
            return self.mini_player.video_widget
        return self.now_playing_panel.video_widget

    def _prepare_video_output(self) -> None:
        """Muestra solo la superficie de vídeo activa y la vincula a VLC."""
        widget = self._active_video_widget()
        if self._video_output == "mini":
            self.now_playing_panel.set_video_enabled(False)
            self.mini_player.set_video_enabled(True)
        else:
            self.mini_player.set_video_enabled(False)
            self.now_playing_panel.set_video_enabled(True)
        self.playback_controller.player.set_video_widget(int(widget.winId()))

    def _hide_video_output(self) -> None:
        self.now_playing_panel.set_video_enabled(False)
        self.mini_player.set_video_enabled(False)

    def _request_stream(
        self,
        track: Track,
        *,
        video: bool,
        keep_position: bool = False,
    ) -> None:
        """Resuelve un stream y recuerda cómo reanudarlo al llegar."""
        if keep_position:
            self._stream_request_position = self.playback_controller.player.get_position()
            self._stream_request_play = self.playback_controller.is_playing()
        else:
            self._stream_request_position = None
            self._stream_request_play = True
        self.search_controller.resolve_stream(track, video=video)

    def _on_stream_required(self, track: Track) -> None:
        """Pista de YouTube sin archivo local: resolver audio (o vídeo)."""
        if track is None:
            return
        wants_video = self._wants_video()
        self._toast("Cargando vídeo…" if wants_video else "Cargando stream…", "info", 2000)
        self._request_stream(track, video=wants_video)

    def _on_stream_resolved(self, track: Track, url: str, is_video: bool = False) -> None:
        if track is None:
            return
        if not url:
            self._toast(f"No se pudo obtener el stream de «{track.title}»", "warning")
            self._stream_request_position = None
            # Intentar la siguiente pista automáticamente
            self.playback_controller.next(auto=True)
            return
        position = self._stream_request_position
        autoplay = self._stream_request_play
        self._stream_request_position = None
        if is_video:
            if self._video_output == "mini":
                self.mini_player.show()
                self.mini_player.set_video_enabled(True)
            else:
                self.sidebar.select("home")
                self.now_playing_panel.set_video_enabled(True)
            self._prepare_video_output()
            self._video_track_id = track.youtube_id
            self.playback_controller.player.enable_video()
        else:
            self._video_track_id = ""
            self._hide_video_output()
            self.playback_controller.player.disable_video()
        self.playback_controller.play_stream(
            track,
            url,
            position=position,
            autoplay=autoplay,
            is_video=is_video,
        )

    def _on_video_toggled(self, enabled: bool) -> None:
        track = self.playlist_controller.current_track()
        if track is None:
            self.now_playing_panel.set_video_enabled(False)
            return
        self._video_output = "now"
        if not enabled:
            self.now_playing_panel.set_video_enabled(False)
            self._video_track_id = ""
            if track.is_youtube:
                # Volver al audio del mismo punto del vídeo.
                self._request_stream(track, video=False, keep_position=True)
            elif track.file_path:
                self._video_pending_position = self.playback_controller.player.get_position()
                self._video_pending_was_playing = self.playback_controller.is_playing()
                self._switch_to_audio(track.file_path)
            return
        if not track.is_youtube:
            self.now_playing_panel.set_video_enabled(False)
            return
        self.mini_player.set_video_enabled(False)
        self._prepare_video_output()
        self._request_stream(track, video=True, keep_position=True)

    def _on_video_size_mode_changed(self, mode: VideoSizeMode, size: QSize) -> None:
        """Actualiza el modo/tamaño de vídeo y programa el guardado en disco."""
        self.config.video_size_mode = mode.value
        if size.isValid() and size.width() > 0 and size.height() > 0:
            self.config.video_width = int(size.width())
            self.config.video_height = int(size.height())
        self._video_cfg_timer.start()

    def _persist_video_settings(self) -> None:
        """Guarda la configuración una sola vez tras el último cambio."""
        save_config(self.config)

    def _on_video_fullscreen_requested(self, enabled: bool) -> None:
        """Pone la ventana en pantalla completa (o la restaura) para el vídeo."""
        if enabled:
            # Si aún no se está mostrando el vídeo, activarlo (pista de YouTube).
            track = self.playlist_controller.current_track()
            if track is not None and track.is_youtube and not self._wants_video():
                self.now_playing_panel.video_toggle_btn.setChecked(True)
                self._on_video_toggled(True)
            self.showFullScreen()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_video_fullscreen(self) -> None:
        """Sale de la pantalla completa de vídeo (atajo Esc)."""
        if not self.isFullScreen():
            return
        self.showNormal()
        self.now_playing_panel.exit_fullscreen()
        self.raise_()
        self.activateWindow()

    def _switch_to_audio(self, file_path: str) -> None:
        """Vuelve al archivo local preservando la posición exacta."""
        position = float(getattr(self, "_video_pending_position", 0.0) or 0.0)
        was_playing = bool(getattr(self, "_video_pending_was_playing", False))
        self.playback_controller.player.load(file_path)
        self.playback_controller.player.set_position(position)
        if was_playing:
            self.playback_controller.player.play()
        self._video_pending_position = None
        self._video_pending_was_playing = None

    def _fetch_video_stream(self, track: Track) -> None:
        """Compatibilidad: fuerza la resolución del stream en modo vídeo."""
        if not track.is_youtube:
            return
        self._request_stream(track, video=True, keep_position=True)

    def _on_stream_found(self, url: str) -> None:
        """Señal heredada de ``fetch_stream``; delega en el flujo actual."""
        track = self.playlist_controller.current_track()
        if track is None:
            return
        if not url:
            self._toast("No se pudo cargar el stream de vídeo", "warning")
            return
        self._prepare_video_output()
        self._video_track_id = track.youtube_id
        self.playback_controller.play_stream(
            track,
            url,
            position=self._stream_request_position,
            autoplay=self._stream_request_play,
        )
        self._stream_request_position = None

    # ==================================================================
    # Biblioteca
    # ==================================================================
    def add_folder_to_library(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta musical")
        if not folder:
            return
        if folder not in self.config.library_dirs:
            self.config.library_dirs.append(folder)
        self._toast(f"Escaneando {os.path.basename(folder)}…", "info", 2000)
        self.library_controller.scan(folder)

    def _on_library_entries(self, entries: list) -> None:
        self.library_panel.set_entries(entries)

    def _on_scan_finished(self, count: int) -> None:
        self._toast(f"Escaneo finalizado: {count} archivos", "success")

    def _clear_library(self) -> None:
        self.library_controller.clear()
        self.library_panel.clear()

    def _play_library_path(self, path: str) -> None:
        entry = self.library_controller.find_by_path(path)
        if entry is None:
            return
        track = Track(
            id=Path(path).name,
            title=entry.get("title", ""),
            artist=entry.get("artist", "Desconocido"),
            album=entry.get("album", "Desconocido"),
            file_path=path,
            duration=entry.get("duration", 0) or 0,
            source="local",
        )
        self.playlist_controller.add_track(track)
        self.stack.setCurrentIndex(VIEW_INDEX["playlist"])
        if not self.playback_controller.is_playing():
            self.playback_controller.play_index(self.playlist_controller.count - 1)

    # ==================================================================
    # Ficheros y etiquetas
    # ==================================================================
    def open_file_dialog(self) -> None:
        paths = self.files_controller.choose_files(self)
        if paths:
            self.files_controller.add_files(paths)
            self.stack.setCurrentIndex(VIEW_INDEX["playlist"])

    def _edit_tags_at(self, index: int) -> None:
        track = self.playlist_controller.track_at(index)
        if track is not None and self.files_controller.edit_tags(track.file_path, self):
            self.library_panel.rebuild()

    def _edit_tags_path(self, path: str) -> None:
        if self.files_controller.edit_tags(path, self):
            self.library_panel.rebuild()

    def show_batch_tag_editor(self) -> None:
        paths = [
            track.file_path
            for track in self.playlist_controller.tracks()
            if track.file_path and os.path.exists(track.file_path)
        ]
        if not paths:
            self._toast("No hay ficheros locales en la playlist", "warning")
            return
        self.files_controller.edit_tags_batch(paths, self)

    def show_duplicates(self) -> None:
        from ui.panels.duplicates_dialog import DuplicatesDialog

        tracks = self.playlist_controller.tracks()
        groups = self.files_controller.find_duplicates(tracks)
        if not groups:
            self._toast("No se encontraron duplicados", "info")
            return
        dialog = DuplicatesDialog(groups, self)
        dialog.purge_requested.connect(
            lambda paths: self.files_controller.purge_duplicates(paths, self)
        )
        dialog.show()

    def _remove_selected(self) -> None:
        row = self.playlist_panel.current_row()
        if row >= 0:
            self.playlist_controller.remove_index(row)

    def _play_next_row(self, index: int) -> None:
        """Mueve la pista elegida justo detrás de la que suena ahora."""
        if self.playlist_controller.track_at(index) is None:
            return
        current = self.playlist_controller.playlist.current_index
        target = current + 1
        if index == current or index == target:
            return
        if index < target:
            target -= 1
        if self.playlist_controller.move(index, target):
            self._toast("Se reproducirá a continuación", "success")

    def _open_folder_at(self, index: int) -> None:
        """Abre la carpeta de la pista indicada (solo archivos locales)."""
        track = self.playlist_controller.track_at(index)
        if track is None or not track.file_path:
            return
        path = str(track.file_path)
        if path.startswith("http"):
            return
        folder = os.path.dirname(os.path.abspath(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _clear_playlist(self) -> None:
        if self.playlist_controller.count == 0:
            return
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "¿Limpiar toda la playlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.playback_controller.stop()
            self.playlist_controller.clear()
            self.now_playing_panel.reset()
            self.controls_panel.set_position(0, 0)

    def _save_queue_as_playlist(self) -> None:
        """Guarda la cola actual como una nueva playlist."""
        if self.playlist_controller.count == 0:
            self._toast("La cola está vacía", "warning")
            return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Guardar cola como playlist", "Nombre de la playlist:")
        if not ok or not name.strip():
            return
        playlist_id = self.playlist_manager.create(name.strip())
        tracks = self.playlist_controller.tracks()
        self.playlist_manager.add_tracks(playlist_id, tracks)
        self._refresh_playlists()
        self._toast(f"Cola guardada como playlist «{name.strip()}»", "success")

    def _clear_played_from_queue(self) -> None:
        """Elimina de la cola las pistas que ya se han reproducido (índice < current)."""
        current = self.playlist_controller.playlist.current_index
        if current <= 0:
            self._toast("No hay pistas reproducidas para limpiar", "info")
            return
        # Eliminar en orden inverso para no afectar los índices
        for i in range(current - 1, -1, -1):
            self.playlist_controller.remove_index(i)
        self._toast(f"Eliminadas {current} pista(s) reproducida(s)", "success")

    def _shuffle_queue(self) -> None:
        """Mezcla el orden de la cola manteniendo la pista actual."""
        if self.playlist_controller.count <= 1:
            return
        current_track = self.playlist_controller.current_track()
        tracks = self.playlist_controller.tracks()
        # Separar pista actual del resto
        others = [t for t in tracks if t is not current_track]
        import random
        random.shuffle(others)
        # Reconstruir: pista actual + resto mezclado
        new_tracks = [current_track] + others if current_track else others
        self.playlist_controller.clear()
        self.playlist_controller.add_tracks(new_tracks)
        self.playlist_controller.set_current(0)
        self._toast("Cola mezclada", "success")

    # ==================================================================
    # Favoritos, historial y playlists
    # ==================================================================
    def _toggle_favorite(self) -> None:
        track = self.playlist_controller.current_track()
        if track is not None:
            self._toggle_favorite_at(self.playlist_controller.index_of(track))

    def _toggle_favorite_at(self, index: int) -> None:
        track = self.playlist_controller.track_at(index)
        if track is None:
            return
        if self.store.is_favorite(track.track_key):
            self.store.remove_favorite(track.track_key)
            self._toast("Quitada de favoritos", "info")
            self.now_playing_panel.set_favorite_state(False)
        else:
            self.store.add_favorite(track)
            self._toast("Añadida a favoritos", "success")
            self.now_playing_panel.set_favorite_state(True)
        self.favorites_model.set_tracks(self._tracks_from_rows(self.store.favorites()))

    def _play_favorite(self, index: int) -> None:
        """Reproduce una pista de la lista de favoritos."""
        track = self.favorites_model.track_at(index)
        if track is None:
            return
        existing = self.playlist_controller.index_of(track)
        if existing >= 0:
            self.playback_controller.play_index(existing)
        else:
            self.playlist_controller.add_tracks([track])
            idx = self.playlist_controller.count - 1
            self.playback_controller.play_index(idx)

    def _remove_favorite_at(self, index: int) -> None:
        track = (
            self.favorites_model.track_at(index)
            if hasattr(self.favorites_model, "track_at")
            else None
        )
        if track is None:
            return
        self.store.remove_favorite(track.track_key)
        self.favorites_model.set_tracks(self._tracks_from_rows(self.store.favorites()))
        self._toast("Quitada de favoritos", "info")

    def _clear_favorites(self) -> None:
        for row in self.store.favorites():
            self.store.remove_favorite(row.get("track_key", ""))
        self.favorites_model.set_tracks([])
        self._toast("Favoritos vaciados", "info")

    # ==================================================================
    # Historial (funcional: reproducir, quitar, limpiar, favorita, carpeta, etiquetas)
    # ==================================================================
    def _history_track_at(self, row: int) -> Track | None:
        track = self.history_model.track_at(row)
        if track is None:
            return None
        return track

    def _play_history_row(self, row: int) -> None:
        """Reproduce una pista del historial (la añade a la cola si no está)."""
        track = self._history_track_at(row)
        if track is None:
            return
        existing = self.playlist_controller.index_of(track)
        if existing >= 0:
            self.playback_controller.play_index(existing)
        else:
            self.playlist_controller.add_tracks([track])
            idx = self.playlist_controller.count - 1
            self.playback_controller.play_index(idx)
        self._toast(f"Reproduciendo: {track.title}", "success")

    def _remove_history_row(self, row: int) -> None:
        """Elimina una entrada del historial y del modelo de la vista."""
        track = self._history_track_at(row)
        if track is None:
            return
        self.store.remove_history(track.track_key)
        self.history_model.remove_row(row)
        self._toast("Eliminada del historial", "info")

    def _clear_history(self) -> None:
        """Vacía todo el historial tras confirmar."""
        if self.history_model.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "Â¿Vaciar todo el historial de reproducciÃ³n?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.clear_history()
            self.history_model.set_tracks([])
            self._toast("Historial vaciado", "info")

    def _toggle_favorite_history(self, row: int) -> None:
        """Alterna favorita de una pista del historial."""
        track = self._history_track_at(row)
        if track is None:
            return
        if self.store.is_favorite(track.track_key):
            self.store.remove_favorite(track.track_key)
            self._toast("Quitada de favoritos", "info")
        else:
            self.store.add_favorite(track)
            self._toast("AÃ±adida a favoritos", "success")

    def _open_history_folder(self, row: int) -> None:
        """Abre la carpeta de la pista del historial (solo archivos locales)."""
        track = self._history_track_at(row)
        if track is None or not track.file_path or str(track.file_path).startswith("http"):
            return
        folder = os.path.dirname(os.path.abspath(str(track.file_path)))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _edit_tags_history(self, row: int) -> None:
        """Abre el editor de etiquetas de una pista del historial."""
        track = self._history_track_at(row)
        if track is None or not track.file_path:
            return
        if self.files_controller.edit_tags(track.file_path, self):
            self.library_panel.rebuild()

    def _tracks_from_rows(self, rows: list[dict]) -> list[Track]:
        return [
            Track(
                id=row.get("track_key", ""),
                title=row.get("title", ""),
                artist=row.get("artist", ""),
                album=row.get("album", ""),
                file_path=row.get("file_path", ""),
                duration=row.get("duration", 0) or 0,
                cover_url=row.get("cover_url"),
                source=row.get("source", "local"),
            )
            for row in rows
        ]

    def _refresh_playlists(self) -> None:
        self.playlists_panel.set_playlists(self.playlist_manager.list_playlists())

    def _create_playlist(self) -> None:
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Nueva playlist", "Nombre:")
        if ok and name.strip():
            self.playlist_manager.create(name.strip())
            self._refresh_playlists()

    def _rename_playlist(self, playlist_id: str) -> None:
        from PyQt6.QtWidgets import QInputDialog

        playlist = self.playlist_manager.get(playlist_id)
        if playlist is None:
            return
        name, ok = QInputDialog.getText(
            self, "Renombrar playlist", "Nombre:", text=playlist.get("name", "")
        )
        if ok and name.strip():
            self.playlist_manager.rename(playlist_id, name.strip())
            self._refresh_playlists()

    def _delete_playlist(self, playlist_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "¿Eliminar esta playlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.playlist_manager.delete(playlist_id)
            self._refresh_playlists()

    def _duplicate_playlist(self, playlist_id: str) -> None:
        self.playlist_manager.duplicate(playlist_id)
        self._refresh_playlists()

    def _open_playlist(self, playlist_id: str) -> None:
        tracks = self.playlist_manager.tracks(playlist_id)
        if not tracks:
            self._toast("La playlist está vacía", "info")
            return
        self.playlist_controller.add_tracks(tracks)
        self.stack.setCurrentIndex(VIEW_INDEX["playlist"])
        self._toast(f"{len(tracks)} pistas añadidas a la lista", "success")

    def _import_playlist(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar playlist",
            str(self.paths.playlists_dir),
            "Playlists (*.json *.m3u *.m3u8);;JSON (*.json);;M3U (*.m3u *.m3u8)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                playlist_id, tracks = self.playlist_manager.import_json(path)
            else:
                playlist_id, tracks = self.playlist_manager.import_m3u(path)
        except (OSError, ValueError) as exc:
            self._toast(f"No se pudo importar: {exc}", "error")
            return
        self._refresh_playlists()
        self._toast(f"Importadas {len(tracks)} pistas", "success")

    def _export_playlist(self, playlist_id: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar playlist",
            str(self.paths.playlists_dir / "playlist.m3u"),
            "M3U (*.m3u);;JSON (*.json)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                self.playlist_manager.export_json(playlist_id, path)
            else:
                self.playlist_manager.export_m3u(playlist_id, path)
        except OSError as exc:
            self._toast(f"No se pudo exportar: {exc}", "error")
            return
        self._toast("Playlist exportada", "success")

    def _open_track_folder(self) -> None:
        track = self.playlist_controller.current_track()
        if track is None or not track.file_path:
            return
        folder = os.path.dirname(os.path.abspath(track.file_path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_mini_toggled(self, enabled: bool) -> None:
        """Activa/desactiva el mini reproductor flotante."""
        self.now_playing_panel.set_mini_enabled(enabled)
        if not enabled:
            self._on_mini_close()
            return
        track = self.playlist_controller.current_track()
        if track is not None:
            self.mini_player.set_track_info(track.title, track.artist, track.album)
            self.mini_player.set_cover(self._current_cover_source(), self.image_provider)
            self.mini_player.set_video_available(track.is_youtube)
        self.mini_player.set_playing(self.playback_controller.is_playing())
        self.mini_player.set_volume(self.config.volume)
        self.mini_player.set_position(
            self.playback_controller.player.get_position(),
            self.controls_panel.slider.maximum(),
        )
        self.mini_player.show()
        self.mini_player.raise_()

    def _on_mini_close(self) -> None:
        """El mini reproductor pide cerrarse -> desactivamos el modo."""
        was_video = self.mini_player.video_enabled()
        self.now_playing_panel.set_mini_enabled(False)
        self.mini_player.set_video_enabled(False)
        self.mini_player.hide()
        if was_video:
            self._video_output = "now"
            track = self.playlist_controller.current_track()
            if track is not None and track.is_youtube:
                self._request_stream(track, video=False, keep_position=True)
            elif track is not None and track.file_path:
                self._video_pending_position = self.playback_controller.player.get_position()
                self._video_pending_was_playing = self.playback_controller.is_playing()
                self._switch_to_audio(track.file_path)

    def _on_mini_seek(self, seconds: int) -> None:
        self.playback_controller.seek(float(seconds))

    def _on_mini_volume_changed(self, value: int) -> None:
        self.controls_panel.set_volume(value)
        self.playback_controller.set_volume(value)
        self.config.volume = int(value)

    def _on_mini_show_main(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_mini_stay_on_top_changed(self, stay_on_top: bool) -> None:
        """Guarda la preferencia 'siempre encima' del mini reproductor."""
        self.config.mini_stay_on_top = stay_on_top
        self._video_cfg_timer.start()

    def _on_mini_undock(self) -> None:
        """Desacopla el mini reproductor: lo convierte en ventana independiente."""
        if self.mini_player._is_docked:
            # Quitar del layout actual
            layout = self.now_playing_panel.video_stage.layout()
            if layout:
                layout.removeWidget(self.mini_player)
            # Reparentar a None (ventana de nivel superior)
            self.mini_player.setParent(None)
            self.mini_player.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.mini_player.show()
            self.mini_player.raise_()
            self.mini_player.activateWindow()

    def _on_mini_dock(self) -> None:
        """Acopla el mini reproductor de vuelta a la interfaz principal."""
        if not self.mini_player._is_docked:
            self.mini_player.hide()
            # Reparentar al widget contenedor
            self.mini_player.setParent(self.now_playing_panel.video_stage)
            self.mini_player.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.now_playing_panel.video_stage.layout().addWidget(
                self.mini_player, alignment=Qt.AlignmentFlag.AlignCenter
            )
            self.mini_player.show()
            self.mini_player.raise_()

    def _on_mini_video_toggled(self, enabled: bool) -> None:
        """Cambia la salida de vídeo del mini reproductor."""
        track = self.playlist_controller.current_track()
        if enabled:
            if track is None or not track.is_youtube:
                self.mini_player.set_video_enabled(False)
                return
            self._video_output = "mini"
            self._prepare_video_output()
            self._request_stream(track, video=True, keep_position=True)
        else:
            self._video_output = "now"
            self.mini_player.set_video_enabled(False)
            self._video_track_id = ""
            if track is not None and track.is_youtube:
                self._request_stream(track, video=False, keep_position=True)
            elif track is not None and track.file_path:
                self._video_pending_position = self.playback_controller.player.get_position()
                self._video_pending_was_playing = self.playback_controller.is_playing()
                self._switch_to_audio(track.file_path)

    # ==================================================================
    # Ajustes, caché y persistencia
    # ==================================================================
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.config = dialog.result_config()
        save_config(self.config)
        self.apply_theme(self.config.theme)
        if self.config.download_dir:
            self.youtube_service.set_download_dir(self.config.download_dir)
        self.downloads_panel.set_destination(self.config.download_dir)
        self.downloads_panel.set_format(self.config.download_format)
        self.downloads_panel.set_mode(self.config.download_mode)
        self.lastfm.configure(
            self.config.lastfm_api_key,
            self.config.lastfm_username,
            self.config.lastfm_session_key,
        )
        self.smtc.stop()
        if self.config.features_smtc:
            self.smtc.start()
        self.audio_detector.stop()
        if self.config.features_audio_detection:
            self.audio_detector.start()
        self._toast("Ajustes guardados", "success")

    def show_update_dialog(self) -> None:
        """Comprueba si hay una versión nueva disponible."""
        from ui.panels.update_dialog import UpdateDialog

        dialog = UpdateDialog(self, self.pool)
        dialog.show()

    def set_download_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para las descargas")
        if folder:
            self.youtube_service.set_download_dir(folder)
            self.config.download_dir = folder
            self.downloads_panel.set_destination(folder)
            save_config(self.config)
            self._toast(f"Descargas fijadas en: {Path(folder).name}", "success")

    def clear_cache(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "¿Eliminar todos los archivos descargados del caché?\n"
            "(Las pistas de YouTube de la playlist dejarán de funcionar)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            removed = self.youtube_service.cleanup()
            self._toast(f"Caché limpiado ({removed} archivos)", "success")

    def _save_playlist(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar playlist", str(self.paths.playlists_dir), "Playlist (*.json)"
        )
        if not path:
            return
        try:
            self.playlist_controller.save_to(path)
            self._toast("Playlist guardada", "success")
        except OSError as exc:
            self._toast(f"No se pudo guardar: {exc}", "error")

    def _load_playlist(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Cargar playlist", str(self.paths.playlists_dir), "Playlist (*.json)"
        )
        if not path:
            return
        try:
            self.playlist_controller.load_from(path)
            self._toast("Playlist cargada", "success")
        except (OSError, ValueError) as exc:
            self._toast(f"No se pudo cargar: {exc}", "error")

    def apply_theme(self, name: str) -> None:
        """Aplica el tema indicado. Si name="auto", detecta el tema del sistema."""
        from ui.themes import ThemeManager
        if name == "auto":
            name = ThemeManager.get_system_theme()
        self.config.theme = name
        self.setStyleSheet(ThemeManager.get_theme(name))
        if is_clay_theme(name):
            self._apply_clay_effects()
        else:
            self._clear_clay_effects()

    def _on_system_theme_changed(self) -> None:
        """Reacciona al cambio de tema del sistema cuando el tema está en 'auto'."""
        if self.config.theme == "auto":
            self.apply_theme("auto")

    def _apply_clay_effects(self) -> None:
        """Sombras elevadas solo en paneles sin superficie nativa de VLC.

        Aplicar ``QGraphicsEffect`` sobre un contenedor que aloja el HWND de
        VLC provoca avisos de ``paintEngine`` y tirones; por eso el área de
        contenido y el frame de vídeo quedan fuera.
        """
        ThemeManager.apply_clay_shadow(self.sidebar, blur=24, dy=8, alpha=0.5)
        ThemeManager.apply_clay_shadow(self.controls_panel, blur=22, dy=8, alpha=0.45)

    def _clear_clay_effects(self) -> None:
        """Elimina los efectos de sombra al salir de un tema clay."""
        for widget in (
            self.sidebar,
            self.findChild(QWidget, "ContentArea"),
            self.controls_panel,
            getattr(self.now_playing_panel, "video_frame", None),
        ):
            if widget is not None:
                widget.setGraphicsEffect(None)

    def apply_native_style(self, style_name: str) -> None:
        QApplication.setStyle(style_name)
        self.setStyleSheet("")

    def toggle_queue(self) -> None:
        self.queue_dock.setVisible(not self.queue_dock.isVisible())

    def toggle_downloads(self) -> None:
        """Muestra u oculta el gestor de descargas independiente."""
        if self.download_manager.isVisible():
            self.download_manager.hide()
        else:
            self.download_manager.show_and_raise()

    def _restore_session(self) -> None:
        """Restaura geometría, tema, volumen, playlist y posición."""
        if self.config.window_geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.config.window_geometry.encode()))
            except (ValueError, TypeError):
                logger.debug("Geometría de ventana inválida")
        self.controls_panel.set_volume(self.config.volume)
        self.controls_panel.shuffle_btn.setChecked(self.config.shuffle)
        self.controls_panel.set_repeat_mode(self.config.repeat_mode)
        self.playlist_controller.playlist.shuffle = self.config.shuffle
        self.playlist_controller.playlist.repeat_mode = RepeatMode.from_name(
            self.config.repeat_mode.upper()
        )
        if self.config.download_dir:
            self.youtube_service.set_download_dir(self.config.download_dir)

        main_playlist = self.paths.main_playlist
        if main_playlist.exists():
            try:
                self.playlist_controller.load_from(str(main_playlist))
            except (OSError, ValueError) as exc:
                logger.warning("No se pudo restaurar la playlist: %s", exc)

        session = self.store.get_session()
        index = int(session.get("current_index", 0) or 0)
        position_ms = int(session.get("position", 0) or 0)
        if 0 <= index < self.playlist_controller.count:
            self.playlist_controller.set_current(index)
            if position_ms > 0:
                self._restore_position_ms = position_ms
        self.sidebar.select(self.config.last_view or "home")
        self._scrobbled_key = None

    def _save_session(self) -> None:
        # Guarda el volumen real (aunque la sesión termine silenciada).
        self.config.volume = int(self._unmuted_volume)
        self.config.shuffle = self.playlist_controller.playlist.shuffle
        self.config.last_view = self.sidebar.current_key()
        self.config.window_geometry = self.saveGeometry().toBase64().data().decode("ascii")
        self.config.window_state = self.saveState().toBase64().data().decode("ascii")
        save_config(self.config)
        try:
            self.playlist_controller.save_to(str(self.paths.main_playlist))
        except OSError as exc:
            logger.warning("No se pudo guardar la playlist: %s", exc)
        self.store.set_session(
            {
                "current_index": self.playlist_controller.playlist.current_index,
                "position": self.playback_controller.player.get_position(),
            }
        )

    # ==================================================================
    # Feedback
    # ==================================================================
    def _toast(self, message: str, toast_type: str = "info", duration_ms: int = 3500) -> None:
        self.toasts.show_toast(message, toast_type, duration_ms)
        self.toasts._reposition()

    # ==================================================================
    # Arrastrar y soltar
    # ==================================================================
    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        files = [path for path in paths if os.path.isfile(path)]
        folders = [path for path in paths if os.path.isdir(path)]
        if files:
            self.files_controller.add_files(files)
        for folder in folders:
            self.library_controller.scan(folder)
        event.acceptProposedAction()

    # ==================================================================
    # Cierre
    # ==================================================================
    def closeEvent(self, event) -> None:  # noqa: N802  # type: ignore[override]
        if self._closing:
            event.accept()
            return
        self._closing = True
        self._save_session()
        # Cancelar cooperativamente y esperar: nunca "QThread destroyed while running".
        self.tasks.cancel_all()
        self.pool.waitForDone(5000)
        # Detener la reproducción antes de cerrar
        try:
            self.playback_controller.player.stop()
        except Exception:  # noqa: BLE001
            pass
        self.now_playing_panel.set_video_enabled(False)
        self.mini_player.set_video_enabled(False)
        self.mini_player.hide()
        self.download_manager.hide()
        self.media_keys.stop()
        self.smtc.stop()
        self.audio_detector.stop()
        if hasattr(self, "tray"):
            self.tray.hide()
        self.store.close()
        event.accept()
