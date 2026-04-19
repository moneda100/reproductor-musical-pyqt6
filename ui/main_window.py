import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QListWidget, 
                             QListWidgetItem, QLineEdit, QSplitter, QTabWidget,
                             QMessageBox, QApplication, QStyleFactory, QMenu, QSlider,
                             QTreeWidget, QTreeWidgetItem, QComboBox, QDialog,
                             QStackedWidget, QFrame)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QIcon, QFont

from core.player import MusicPlayer, PlayerState
from core.playlist import Playlist, Track, RepeatMode
from ui.widgets import ClickableSlider, CoverArtLabel, MarqueeLabel
from ui.themes import ThemeManager
from ui.tag_editor import TagEditorDialog
from services.metadata_service import MetadataService
from services.youtube_service import YouTubeService

class YouTubeSearchThread(QThread):
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, query, service):
        super().__init__()
        self.query = query
        self.service = service

    def run(self):
        try:
            results = self.service.search_songs(self.query)
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))

class YouTubeDownloadThread(QThread):
    track_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, url, service, permanent=False):
        super().__init__()
        self.url = url
        self.service = service
        self.permanent = permanent

    def run(self):
        try:
            self.status_update.emit("Descargando audio...")
            info = self.service.get_info(self.url, permanent=self.permanent)
            if info and info.get('local_file'):
                track = Track(
                    id=info['id'],
                    title=info['title'],
                    artist=info['artist'],
                    album="YouTube",
                    file_path=info['local_file'],
                    duration=info['duration'],
                    cover_url=info['thumbnail'],
                    source="youtube"
                )
                self.track_ready.emit(track)
            else:
                self.error_occurred.emit("No se pudo descargar el audio.")
        except Exception as e:
            self.error_occurred.emit(str(e))

class YouTubePlaylistThread(QThread):
    """Hilo para cargar todos los videos de una playlist de YouTube."""
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, url, service):
        super().__init__()
        self.url = url
        self.service = service

    def run(self):
        try:
            self.status_update.emit("Obteniendo información de la playlist...")
            results = self.service.get_playlist_info(self.url)
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))

class YouTubeBatchDownloadThread(QThread):
    """Hilo para descargar múltiples canciones secuencialmente."""
    track_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, results, service, permanent=False):
        super().__init__()
        self.results = results
        self.service = service
        self.permanent = permanent
        self._is_running = True

    def run(self):
        total = len(self.results)
        for i, res in enumerate(self.results):
            if not self._is_running: break
            
            self.status_update.emit(f"📥 Descargando {i+1}/{total}: {res['title'][:30]}...")
            try:
                info = self.service.get_info(res['url'], permanent=self.permanent)
                if info and info.get('local_file'):
                    track = Track(
                        id=info['id'],
                        title=info['title'],
                        artist=info['artist'],
                        album="YouTube",
                        file_path=info['local_file'],
                        duration=info['duration'],
                        cover_url=info['thumbnail'],
                        source="youtube"
                    )
                    self.track_ready.emit(track)
                else:
                    print(f"[DEBUG] Error descargando item {i+1}")
            except Exception as e:
                print(f"[DEBUG] Error en batch item {i+1}: {e}")
        
        self.finished_all.emit()

    def stop(self):
        self._is_running = False

class LibraryScanThread(QThread):
    """Hilo para escanear archivos musicales y recolectar metadatos sin bloquear la UI."""
    file_found = pyqtSignal(dict)
    finished_scan = pyqtSignal(int)
    progress_msg = pyqtSignal(str)

    def __init__(self, folder_path, metadata_service):
        super().__init__()
        self.folder_path = folder_path
        self.ms = metadata_service
        self._is_running = True

    def run(self):
        valid_ext = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')
        count = 0
        try:
            for root, _, files in os.walk(self.folder_path):
                if not self._is_running: break
                for file in files:
                    if not self._is_running: break
                    if file.lower().endswith(valid_ext):
                        path = os.path.join(root, file)
                        # Intentar sacar metadatos para la organización
                        meta = self.ms.get_metadata(path)
                        # Añadir info de carpeta relativa
                        rel_path = os.path.relpath(root, self.folder_path)
                        self.file_found.emit({
                            'path': path,
                            'filename': file,
                            'title': meta.get('title', file),
                            'artist': meta.get('artist', 'Desconocido'),
                            'album': meta.get('album', 'Desconocido'),
                            'rel_dir': rel_path,
                            'duration': meta.get('duration', 0)
                        })
                        count += 1
                        if count % 10 == 0:
                            self.progress_msg.emit(f"Escaneando... {count} archivos encontrados")
            
            self.finished_scan.emit(count)
        except Exception as e:
            print(f"[DEBUG] Error en LibraryScanThread: {e}")

    def stop(self):
        self._is_running = False

class CoverSearchThread(QThread):
    """Hilo para buscar portadas online sin bloquear la UI."""
    cover_found = pyqtSignal(str)

    def __init__(self, artist, album, metadata_service):
        super().__init__()
        self.artist = artist
        self.album = album
        self.ms = metadata_service

    def run(self):
        try:
            url = self.ms.fetch_online_cover(self.artist, self.album)
            if url:
                self.cover_found.emit(url)
        except Exception as e:
            print(f"[DEBUG] Error en CoverSearchThread: {e}")

class VideoStreamFetchThread(QThread):
    """Hilo para extraer la URL del stream de video de YouTube sin descargar."""
    stream_found = pyqtSignal(str)
    
    def __init__(self, youtube_url, yt_service):
        super().__init__()
        self.url = youtube_url
        self.yt_service = yt_service
        
    def run(self):
        try:
            stream_url = self.yt_service.get_stream_url(self.url)
            if stream_url:
                self.stream_found.emit(stream_url)
        except Exception as e:
            print(f"[DEBUG] Error en VideoStreamFetchThread: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Player Pro")
        self.setMinimumSize(950, 680)
        
        self.player = MusicPlayer()
        self.playlist = Playlist("Mi Lista")
        self.metadata = MetadataService()
        self.yt_service = YouTubeService()
        self.active_threads = []
        self.search_results_cache = []  # Guardar resultados de búsqueda
        self.library_data = []          # Cache de archivos escaneados para re-organizar
        
        self.player.register_callback('state_changed', self.on_state_changed)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(500)
        
        self.setup_ui()
        self.create_menu_bar()
        self.apply_theme("dark")

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # -- Menú Archivo --
        file_menu = menubar.addMenu("&Archivo")
        open_action = QAction("Abrir Archivos...", self)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)
        
        config_dl_action = QAction("⚙️ Configurar Descargas...", self)
        config_dl_action.triggered.connect(self.set_download_directory)
        file_menu.addAction(config_dl_action)
        
        file_menu.addSeparator()
        
        # -- Menú Playlist --
        playlist_menu = menubar.addMenu("&Playlist")
        
        clear_playlist_action = QAction("Limpiar Playlist", self)
        clear_playlist_action.triggered.connect(self.clear_playlist)
        playlist_menu.addAction(clear_playlist_action)
        
        remove_selected_action = QAction("Eliminar Pista Seleccionada", self)
        remove_selected_action.triggered.connect(self.remove_selected_track)
        playlist_menu.addAction(remove_selected_action)
        
        playlist_menu.addSeparator()
        
        clear_cache_action = QAction("Limpiar Caché de Descargas", self)
        clear_cache_action.triggered.connect(self.clear_cache)
        playlist_menu.addAction(clear_cache_action)
        
        clear_results_action = QAction("Limpiar Resultados de Búsqueda", self)
        clear_results_action.triggered.connect(self.clear_search_results)
        playlist_menu.addAction(clear_results_action)
        
        # -- Menú Apariencia --
        appearance_menu = menubar.addMenu("&Apariencia")
        
        qss_menu = appearance_menu.addMenu("Temas Personalizados")
        for theme_name in ["Dark", "Light", "Cyberpunk"]:
            action = QAction(theme_name, self)
            action.triggered.connect(lambda checked, t=theme_name.lower(): self.apply_theme(t))
            qss_menu.addAction(action)
        
        native_menu = appearance_menu.addMenu("Estilos Nativos (PyQt6)")
        for style in QStyleFactory.keys():
            action = QAction(style, self)
            action.triggered.connect(lambda checked, s=style: self.apply_native_style(s))
            native_menu.addAction(action)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- PANEL IZQUIERDO (Carátula/Video + Info) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.stacked_visuals = QStackedWidget()
        self.cover_label = CoverArtLabel(300)
        self.video_frame = QFrame()
        self.video_frame.setFixedSize(300, 300)
        self.video_frame.setStyleSheet("background-color: black; border-radius: 12px;")
        
        self.stacked_visuals.addWidget(self.cover_label)
        self.stacked_visuals.addWidget(self.video_frame)
        self.stacked_visuals.setFixedSize(300, 300)
        
        # Vincular reproductor a este frame de video permanentemente
        # (al estar oculto en modo Off, VLC no lanzará ventanas popup extrañas)
        self.player.set_video_widget(int(self.video_frame.winId()))
        
        self.video_toggle_btn = QPushButton("📺 Ver Video (Off)")
        self.video_toggle_btn.setCheckable(True)
        self.video_toggle_btn.clicked.connect(self.toggle_video_mode)
        self.video_toggle_btn.setObjectName("SecondaryBtn")
        
        self.title_label = MarqueeLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setText("Bienvenido")
        self.title_label.setFixedWidth(300)
        self.artist_label = MarqueeLabel()
        self.artist_label.setObjectName("MutedLabel")
        self.artist_label.setText("Selecciona una pista")
        self.artist_label.setFixedWidth(300)
        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        
        left_layout.addWidget(self.stacked_visuals, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.video_toggle_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addSpacing(10) # Espacio bajo la carátula/botón
        left_layout.addWidget(self.title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.artist_label, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addStretch()
        
        splitter.addWidget(left_panel)
        
        # --- PANEL DERECHO (Búsqueda + Tabs) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Barra de búsqueda
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Busca en YouTube o pega un link...")
        self.search_input.returnPressed.connect(self.handle_search)
        
        self.search_btn = QPushButton("Buscar")
        self.search_btn.clicked.connect(self.handle_search)
        
        self.download_all_btn = QPushButton("⬇️ Descargar Todo")
        self.download_all_btn.setObjectName("SecondaryBtn")
        self.download_all_btn.clicked.connect(self.download_all_results)
        self.download_all_btn.setEnabled(False)
        
        from PyQt6.QtWidgets import QCheckBox
        self.permanent_mode_cb = QCheckBox("📥 Guardar como MP3 permanente")
        self.permanent_mode_cb.setStyleSheet("font-size: 11px; color: #aaa;")
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.download_all_btn)
        right_layout.addLayout(search_layout)
        right_layout.addWidget(self.permanent_mode_cb)
        
        # Tabs: Resultados / Mi Playlist
        self.tabs = QTabWidget()
        
        # Tab 1: Resultados de YouTube
        self.results_widget = QListWidget()
        self.results_widget.setObjectName("ResultsList")
        self.results_widget.doubleClicked.connect(self.download_selected_result)
        self.results_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_widget.customContextMenuRequested.connect(self.results_context_menu)
        self.tabs.addTab(self.results_widget, "🔍 Resultados")
        
        # Tab 2: Playlist principal
        self.playlist_widget = QListWidget()
        self.playlist_widget.setObjectName("PlaylistList")
        self.playlist_widget.doubleClicked.connect(self.play_selected_track)
        self.playlist_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.playlist_context_menu)
        self.tabs.addTab(self.playlist_widget, f"🎵 Playlist (0)")
        
        # Tab 3: Biblioteca
        self.library_panel = QWidget()
        lib_layout = QVBoxLayout(self.library_panel)
        
        # Barra de herramientas de biblioteca
        lib_tools = QHBoxLayout()
        self.add_folder_btn = QPushButton("📁 Añadir")
        self.add_folder_btn.clicked.connect(self.add_folder_to_library)
        
        self.clear_lib_btn = QPushButton("🧹 Limpiar")
        self.clear_lib_btn.setObjectName("SecondaryBtn")
        self.clear_lib_btn.clicked.connect(self.clear_library)
        
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["📂 Carpetas", "🎤 Artistas", "💿 Álbumes"])
        self.view_mode_combo.currentIndexChanged.connect(self.reorganize_library)
        
        lib_tools.addWidget(self.add_folder_btn)
        lib_tools.addWidget(self.clear_lib_btn)
        lib_tools.addStretch()
        lib_tools.addWidget(QLabel("Vista:"))
        lib_tools.addWidget(self.view_mode_combo)
        lib_layout.addLayout(lib_tools)
        
        self.library_widget = QTreeWidget()
        self.library_widget.setHeaderHidden(True)
        self.library_widget.setIndentation(15)
        self.library_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.library_widget.customContextMenuRequested.connect(self.library_context_menu)
        self.library_widget.doubleClicked.connect(self.library_item_double_clicked)
        lib_layout.addWidget(self.library_widget)
        self.tabs.addTab(self.library_panel, "📚 Biblioteca")
        
        right_layout.addWidget(self.tabs)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 500])
        main_layout.addWidget(splitter)
        
        # --- CONTROLES DE REPRODUCCIÓN ---
        control_panel = QWidget()
        control_panel.setObjectName("ControlPanel")
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(30, 10, 30, 20) # Más aire a los lados
        control_layout.setSpacing(10)
        
        # Progreso
        prog_layout = QHBoxLayout()
        self.time_label = QLabel("0:00")
        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.sliderReleased.connect(self.seek_position)
        self.duration_label = QLabel("0:00")
        prog_layout.addWidget(self.time_label)
        prog_layout.addWidget(self.slider)
        prog_layout.addWidget(self.duration_label)
        control_layout.addLayout(prog_layout)
        
        # Botones
        playback_layout = QHBoxLayout()
        playback_layout.setSpacing(15) # Más espacio entre botones
        playback_layout.addStretch()
        
        self.shuffle_btn = QPushButton("🔀")
        self.shuffle_btn.setFixedSize(50, 50)
        self.shuffle_btn.setObjectName("ToggleBtn") # Cambiado a ToggleBtn
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        
        prev_btn = QPushButton("⏮")
        prev_btn.setFixedSize(50, 50)
        prev_btn.setObjectName("ControlBtn") # Cambiado a ControlBtn
        prev_btn.clicked.connect(self.play_previous)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(70, 70)
        self.play_btn.setObjectName("PlayBtn") # Cambiado a PlayBtn
        self.play_btn.clicked.connect(self.toggle_play)
        
        next_btn = QPushButton("⏭")
        next_btn.setFixedSize(50, 50)
        next_btn.setObjectName("ControlBtn")
        next_btn.clicked.connect(self.play_next)
        
        self.repeat_btn = QPushButton("➡️") # ➡️ Ninguno, 🔁 Todo, 🔂 Uno
        self.repeat_btn.setFixedSize(50, 50)
        self.repeat_btn.setObjectName("ControlBtn")
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        
        playback_layout.addWidget(self.shuffle_btn)
        playback_layout.addWidget(prev_btn)
        playback_layout.addWidget(self.play_btn)
        playback_layout.addWidget(next_btn)
        playback_layout.addWidget(self.repeat_btn)
        playback_layout.addStretch()
        
        # Volumen
        vol_layout = QVBoxLayout()
        vol_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        vol_label = QLabel("🔊")
        v_h_layout = QHBoxLayout()
        v_h_layout.addWidget(vol_label)
        v_h_layout.addWidget(self.volume_slider)
        vol_layout.addLayout(v_h_layout)
        playback_layout.addLayout(vol_layout)
        
        control_layout.addLayout(playback_layout)
        
        main_layout.addWidget(control_panel)

    # ==========================================
    # BÚSQUEDA Y RESULTADOS
    # ==========================================

    def handle_search(self):
        query = self.search_input.text().strip()
        if not query: return
        
        if "list=" in query:
            self.load_youtube_playlist(query)
        elif "youtube.com" in query or "youtu.be" in query:
            self.download_youtube(query)
        else:
            self.search_youtube(query)

    def load_youtube_playlist(self, url):
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Cargando...")
        self.status_label.setText("Cargando playlist...")
        
        self._cleanup_threads()
        thread = YouTubePlaylistThread(url, self.yt_service)
        thread.results_ready.connect(self.on_search_results)
        thread.error_occurred.connect(self.on_search_error)
        thread.status_update.connect(lambda msg: self.status_label.setText(msg))
        thread.finished.connect(lambda: self._remove_thread(thread))
        self.active_threads.append(thread)
        thread.start()

    def search_youtube(self, query):
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Buscando...")
        self.status_label.setText("Buscando en YouTube...")
        
        self._cleanup_threads()
        thread = YouTubeSearchThread(query, self.yt_service)
        thread.results_ready.connect(self.on_search_results)
        thread.error_occurred.connect(self.on_search_error)
        thread.finished.connect(lambda: self._remove_thread(thread))
        self.active_threads.append(thread)
        thread.start()

    def on_search_results(self, results):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Buscar")
        
        if not results:
            self.status_label.setText("Sin resultados")
            return
        
        # Guardar y mostrar TODOS los resultados
        self.search_results_cache = results
        self.results_widget.clear()
        
        # Detectar si es una playlist para el título de la pestaña
        tab_title = "🔍 Resultados"
        if results and results[0].get('playlist'):
            tab_title = f"📜 {results[0]['playlist']}"
        
        for i, r in enumerate(results):
            duration_str = self.format_time(r.get('duration', 0)) if r.get('duration') else "?"
            text = f"  {r['title']}\n  {r.get('artist', '?')}  •  {duration_str}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(0, 50))
            self.results_widget.addItem(item)
        
        self.tabs.setTabText(0, f"{tab_title} ({len(results)})")
        self.tabs.setCurrentIndex(0)  # Mostrar pestaña de resultados
        self.status_label.setText(f"{len(results)} resultados encontrados. Doble clic para descargar.")
        self.download_all_btn.setEnabled(True)
        self.download_all_btn.setText(f"⬇️ Descargar {len(results)} canciones")

    def on_search_error(self, error):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Buscar")
        self.status_label.setText("Error en búsqueda")
        QMessageBox.warning(self, "Error", f"Error en búsqueda: {error}")

    def download_selected_result(self):
        """Descarga el resultado seleccionado al hacer doble clic."""
        item = self.results_widget.currentItem()
        if not item: return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and idx < len(self.search_results_cache):
            result = self.search_results_cache[idx]
            self.download_youtube(result['url'])

    def download_all_results(self):
        """Descarga todos los resultados actuales de forma secuencial."""
        if not self.search_results_cache: return
        
        permanent = self.permanent_mode_cb.isChecked()
        mode_text = "como MP3 permanentes" if permanent else "a la caché temporal"
        
        reply = QMessageBox.question(self, "Confirmar Descarga Masiva", 
            f"¿Deseas descargar las {len(self.search_results_cache)} canciones {mode_text}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Si es modo permanente y no hay carpeta, pedirla
            if permanent and (not hasattr(self.yt_service, 'download_dir') or self.yt_service.download_dir == self.yt_service.cache_dir):
                self.set_download_directory()

            self.status_label.setText("🚀 Iniciando descarga masiva...")
            self.search_btn.setEnabled(False)
            self.download_all_btn.setEnabled(False)
            
            self._cleanup_threads()
            thread = YouTubeBatchDownloadThread(self.search_results_cache, self.yt_service, permanent=permanent)
            thread.track_ready.connect(self._on_download_complete)
            thread.status_update.connect(lambda msg: self.status_label.setText(msg))
            thread.finished_all.connect(self._on_batch_complete)
            thread.finished.connect(lambda: self._remove_thread(thread))
            self.active_threads.append(thread)
            thread.start()

    def _on_batch_complete(self):
        self.search_btn.setEnabled(True)
        self.download_all_btn.setEnabled(True)
        self.status_label.setText("✅ Descarga masiva finalizada")
        QMessageBox.information(self, "Finalizado", "Se han procesado todos los resultados.")

    def results_context_menu(self, pos):
        """Menú contextual para los resultados de búsqueda."""
        menu = QMenu(self)
        
        item = self.results_widget.itemAt(pos)
        if item:
            download_action = menu.addAction("⬇️ Descargar y Reproducir")
            download_action.triggered.connect(self.download_selected_result)
            menu.addSeparator()
        
        download_all_action = menu.addAction("⬇️ Descargar TODOS los resultados")
        download_all_action.triggered.connect(self.download_all_results)
        menu.addSeparator()
        
        clear_action = menu.addAction("🗑️ Limpiar Resultados")
        clear_action.triggered.connect(self.clear_search_results)
        
        menu.exec(self.results_widget.mapToGlobal(pos))

    # ==========================================
    # DESCARGA DE YOUTUBE
    # ==========================================

    def download_youtube(self, url):
        permanent = self.permanent_mode_cb.isChecked()
        
        # Si es modo permanente y no hay carpeta, pedirla
        if permanent and (not hasattr(self.yt_service, 'download_dir') or self.yt_service.download_dir == self.yt_service.cache_dir):
            reply = QMessageBox.question(self, "Carpeta de Descarga", 
                "¿Deseas seleccionar una carpeta específica para guardar los MP3 permanentemente?\n(Si cancelas, se guardarán en la carpeta predeterminada)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.set_download_directory()

        self.status_label.setText(f"⏳ {'Descargando MP3' if permanent else 'Cargando caché'}...")
        self.search_btn.setEnabled(False)
        self.search_btn.setText("⏳...")
        
        self._cleanup_threads()
        thread = YouTubeDownloadThread(url, self.yt_service, permanent=permanent)
        thread.track_ready.connect(self._on_download_complete)
        thread.error_occurred.connect(self._on_download_error)
        thread.status_update.connect(lambda msg: self.status_label.setText(msg))
        thread.finished.connect(lambda: self._remove_thread(thread))
        self.active_threads.append(thread)
        thread.start()

    def _on_download_complete(self, track):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Buscar")
        self.status_label.setText("✅ ¡Listo para reproducir!")
        self._add_track_to_ui(track)
        self.tabs.setCurrentIndex(1)  # Cambiar a pestaña de playlist
        
        if self.player.state != PlayerState.PLAYING:
            self.load_track_into_ui(len(self.playlist.tracks) - 1)
            self.player.play()

    def _on_download_error(self, error):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Buscar")
        self.status_label.setText("❌ Error al descargar")
        QMessageBox.warning(self, "Error", f"Error al descargar: {error}")

    # ==========================================
    # GESTIÓN DE PLAYLIST
    # ==========================================

    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Música", "", "Audio (*.mp3 *.flac *.wav *.webm *.m4a *.ogg *.mp4)")
        for f in files:
            meta = self.metadata.get_metadata(f)
            cover = self.metadata.save_cover(meta['cover_data']) if meta['cover_data'] else None
            track = Track(
                id=Path(f).name, title=meta['title'], artist=meta['artist'],
                album=meta['album'], file_path=f, duration=meta['duration'],
                cover_url=cover, source="local"
            )
            self._add_track_to_ui(track)

    def _add_track_to_ui(self, track):
        self.playlist.add_track(track)
        
        # Formato visual mejorado
        duration_str = self.format_time(track.duration) if track.duration > 0 else "?"
        source_icon = "🌐" if track.source == "youtube" else "📁"
        text = f"  {source_icon}  {track.title}\n       {track.artist}  •  {duration_str}"
        
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, len(self.playlist.tracks) - 1)
        item.setSizeHint(QSize(0, 50))
        self.playlist_widget.addItem(item)
        
        # Actualizar título de la pestaña
        self.tabs.setTabText(1, f"🎵 Playlist ({len(self.playlist.tracks)})")

    def playlist_context_menu(self, pos):
        """Menú contextual para la playlist."""
        menu = QMenu(self)
        
        item = self.playlist_widget.itemAt(pos)
        if item:
            play_action = menu.addAction("▶️ Reproducir")
            play_action.triggered.connect(self.play_selected_track)
            
            remove_action = menu.addAction("❌ Eliminar de la Playlist")
            remove_action.triggered.connect(self.remove_selected_track)
            
            edit_action = menu.addAction("📝 Editar Etiquetas")
            edit_action.triggered.connect(lambda: self.open_tag_editor(item))
            menu.addSeparator()
        
        clear_action = menu.addAction("🗑️ Limpiar Toda la Playlist")
        clear_action.triggered.connect(self.clear_playlist)
        
        clear_cache_action = menu.addAction("🧹 Limpiar Caché de Descargas")
        clear_cache_action.triggered.connect(self.clear_cache)
        
        menu.exec(self.playlist_widget.mapToGlobal(pos))

    def remove_selected_track(self):
        """Elimina la pista seleccionada de la playlist."""
        item = self.playlist_widget.currentItem()
        if not item: return
        
        idx = item.data(Qt.ItemDataRole.UserRole)
        row = self.playlist_widget.row(item)
        
        self.playlist.remove_track(idx)
        self.playlist_widget.takeItem(row)
        
        # Reindexar items restantes
        for i in range(self.playlist_widget.count()):
            self.playlist_widget.item(i).setData(Qt.ItemDataRole.UserRole, i)
        
        self.tabs.setTabText(1, f"🎵 Playlist ({len(self.playlist.tracks)})")
        self.status_label.setText("Pista eliminada")

    def clear_playlist(self):
        """Limpia toda la playlist y detiene la reproducción."""
        if self.playlist_widget.count() == 0: return
        
        reply = QMessageBox.question(self, "Confirmar", 
            "¿Limpiar toda la playlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.player.stop()
            self.playlist = Playlist("Mi Lista")
            self.playlist_widget.clear()
            self.tabs.setTabText(1, "🎵 Playlist (0)")
            self.title_label.setText("Bienvenido")
            self.artist_label.setText("Selecciona una pista")
            self.cover_label.set_placeholder()
            self.slider.setValue(0)
            self.time_label.setText("0:00")
            self.duration_label.setText("0:00")
            self.status_label.setText("Playlist limpiada")

    def clear_search_results(self):
        """Limpia los resultados de búsqueda."""
        self.results_widget.clear()
        self.search_results_cache = []
        self.tabs.setTabText(0, "🔍 Resultados")
        self.status_label.setText("Resultados limpiados")

    def clear_cache(self):
        """Limpia los archivos descargados del caché."""
        reply = QMessageBox.question(self, "Confirmar",
            "¿Eliminar todos los archivos descargados del caché?\n(Las pistas de YouTube en la playlist dejarán de funcionar)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.yt_service.cleanup()
            self.status_label.setText("Caché limpiado")

    def load_track_into_ui(self, index):
        self.playlist.current_index = index
        track = self.playlist.get_current_track()
        if track:
            self.title_label.setText(track.title)
            self.artist_label.setText(track.artist)
            is_generic = self.metadata.is_generic_cover(track.cover_url)
            is_local_missing = not str(track.cover_url).startswith('http') and not os.path.exists(str(track.cover_url))
            needs_search = not track.cover_url or is_local_missing or is_generic
            
            if needs_search:
                self.cover_label.set_placeholder()
                self._search_missing_cover(track)
            else:
                self.cover_label.set_cover(track.cover_url)
                
            self.slider.setMaximum(int(track.duration))
            self.duration_label.setText(self.format_time(track.duration))
            
            # Cargar siempre el archivo de caché primero (instantáneo)
            self.player.load(track.file_path)
            
            # Si el video está activo, cargar en segundo plano el streaming y engancharlo suavemente luego
            if self.video_toggle_btn.isChecked() and track.source == "youtube":
                self.fetch_and_play_stream(track)
                
            self.playlist_widget.setCurrentRow(index)

    def _search_missing_cover(self, track):
        """Lanza búsqueda online si la pista no tiene carátula o es genérica."""
        self._cleanup_threads()
        
        # Guardar si la portada original era "inservible" (genérica)
        original_was_generic = self.metadata.is_generic_cover(track.cover_url)
        
        thread = CoverSearchThread(track.artist, track.album, self.metadata)
        
        def on_found(url):
            track.cover_url = url
            # Actualizar UI solo si seguimos en la misma canción
            if self.playlist.get_current_track() == track:
                self.cover_label.set_cover(url)
        
        def on_finished():
            # Si terminó y la portada sigue siendo genérica, forzamos placeholder
            if original_was_generic and self.playlist.get_current_track() == track:
                # Volver a comprobar si sigue siendo genérica (por si on_found cambió algo)
                if self.metadata.is_generic_cover(track.cover_url):
                    print("[DEBUG] No se encontró portada mejor, forzando placeholder.")
                    self.cover_label.set_placeholder()
            self._remove_thread(thread)

        thread.cover_found.connect(on_found)
        thread.finished.connect(on_finished)
        self.active_threads.append(thread)
        thread.start()

    def toggle_video_mode(self):
        is_video = self.video_toggle_btn.isChecked()
        self.video_toggle_btn.setText("📺 Ver Video (On)" if is_video else "📺 Ver Video (Off)")
        
        if is_video:
            self.stacked_visuals.setCurrentIndex(1)
            # En Windows necesitamos usar int(winId())
            win_id = int(self.video_frame.winId())
            self.player.set_video_widget(win_id)
            
            # Si ya hay una pista y es de YouTube, intentar cargar el stream
            track = self.playlist.get_current_track()
            if track and track.source == "youtube":
                self.fetch_and_play_stream(track)
        else:
            self.stacked_visuals.setCurrentIndex(0)
            track = self.playlist.get_current_track()
            if track:
                pos = self.player.get_position()
                self.player.load(track.file_path) # Carga local (solo mp3/mp4 audio)
                self.player.set_position(pos)
                if self.player.state == PlayerState.PLAYING:
                    self.player.play()

    def fetch_and_play_stream(self, track):
        self.status_label.setText("Cargando stream de video...")
        
        # Encontrar el URL web original desde el cache de búsqueda
        # (Aquí track.id o extraer el URL completo)
        # Normalmente guardamos una url cruda o reconstruimos:
        yt_url = f"https://www.youtube.com/watch?v={track.id}" if track.id else track.file_path
        
        self._cleanup_threads()
        thread = VideoStreamFetchThread(yt_url, self.yt_service)
        
        def on_stream_found(stream_url):
            if self.playlist.get_current_track() == track and self.video_toggle_btn.isChecked():
                pos = self.player.get_position()
                self.player.load(stream_url)
                self.player.set_position(max(0, pos))
                self.player.play()
                self.status_label.setText("Modo Video Activo")
                
        thread.stream_found.connect(on_stream_found)
        thread.finished.connect(lambda: self._remove_thread(thread))
        self.active_threads.append(thread)
        thread.start()

    # ==========================================
    # CONTROLES DE REPRODUCCIÓN
    # ==========================================

    def apply_theme(self, name):
        self.setStyleSheet(ThemeManager.get_theme(name))

    def apply_native_style(self, style_name):
        QApplication.setStyle(style_name)
        self.setStyleSheet("")

    def toggle_play(self):
        if self.player.state == PlayerState.PLAYING:
            self.player.pause()
        else:
            self.player.play()

    def play_next(self):
        if self.playlist.next():
            self.load_track_into_ui(self.playlist.current_index)
            self.player.play()

    def play_previous(self):
        if self.playlist.previous():
            self.load_track_into_ui(self.playlist.current_index)
            self.player.play()


    def on_state_changed(self):
        self.play_btn.setText("⏸" if self.player.state == PlayerState.PLAYING else "▶")

    def update_progress(self):
        if self.player.state == PlayerState.PLAYING:
            pos = self.player.get_position()
            self.slider.setValue(int(pos))
            self.time_label.setText(self.format_time(pos))
            track = self.playlist.get_current_track()
            if track and track.duration > 0 and pos >= track.duration - 1:
                self.play_next()

    def seek_position(self):
        self.player.set_position(self.slider.value())

    def play_selected_track(self):
        item = self.playlist_widget.currentItem()
        if item:
            idx = item.data(Qt.ItemDataRole.UserRole)
            self.load_track_into_ui(idx)
            self.player.play()

    def change_volume(self, value):
        self.player.set_volume(value / 100.0)

    def toggle_shuffle(self):
        self.playlist.shuffle = self.shuffle_btn.isChecked()

    def toggle_repeat(self):
        if self.playlist.repeat_mode == RepeatMode.NONE:
            self.playlist.repeat_mode = RepeatMode.ALL
            self.repeat_btn.setText("🔁")
        elif self.playlist.repeat_mode == RepeatMode.ALL:
            self.playlist.repeat_mode = RepeatMode.ONE
            self.repeat_btn.setText("🔂")
        else:
            self.playlist.repeat_mode = RepeatMode.NONE
            self.repeat_btn.setText("➡️")

    @staticmethod
    def format_time(seconds):
        return f"{int(seconds//60)}:{int(seconds%60):02d}"

    def _cleanup_threads(self):
        self.active_threads = [t for t in self.active_threads if t.isRunning()]

    def _remove_thread(self, thread):
        if thread in self.active_threads:
            self.active_threads.remove(thread)

    def closeEvent(self, event):
        for t in self.active_threads:
            t.quit()
            t.wait(2000)
        event.accept()

    # ==========================================
    # DESCARGAS PERSONALIZADAS Y BIBLIOTECA
    # ==========================================

    def set_download_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta para Descargas MP3")
        if folder:
            self.yt_service.set_download_dir(folder)
            self.status_label.setText(f"Descargas fijadas en: {Path(folder).name}")
            
    def add_folder_to_library(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Musical")
        if folder:
            self._cleanup_threads()
            self.status_label.setText(f"Escaneando {os.path.basename(folder)}...")
            self.add_folder_btn.setEnabled(False)
            
            thread = LibraryScanThread(folder, self.metadata)
            thread.file_found.connect(self._on_lib_file_found)
            thread.progress_msg.connect(lambda m: self.status_label.setText(m))
            thread.finished_scan.connect(self._on_lib_scan_finished)
            self.active_threads.append(thread)
            thread.start()

    def _on_lib_file_found(self, data):
        self.library_data.append(data)
        self._add_to_tree(data)

    def _on_lib_scan_finished(self, count):
        self.status_label.setText(f"Escaneo finalizado: {count} archivos.")
        self.add_folder_btn.setEnabled(True)

    def _add_to_tree(self, data):
        mode = self.view_mode_combo.currentText()
        
        if "Carpetas" in mode:
            # Organizar por estructura de carpetas relativas
            parent = self.library_widget.invisibleRootItem()
            parts = data['rel_dir'].split(os.sep) if data['rel_dir'] != "." else []
            
            curr = parent
            for part in parts:
                found = False
                for i in range(curr.childCount()):
                    if curr.child(i).text(0) == f"📁 {part}":
                        curr = curr.child(i)
                        found = True
                        break
                if not found:
                    new_node = QTreeWidgetItem([f"📁 {part}"])
                    curr.addChild(new_node)
                    curr = new_node
            
            item = QTreeWidgetItem([f"🎵 {data['filename']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, data['path'])
            curr.addChild(item)
            
        elif "Artistas" in mode:
            # Artista -> Álbum -> Canción
            artist = data['artist']
            album = data['album']
            
            # Buscar/Crear Artista
            artist_node = self._find_or_create_node(self.library_widget.invisibleRootItem(), f"🎤 {artist}")
            # Buscar/Crear Álbum
            album_node = self._find_or_create_node(artist_node, f"💿 {album}")
            
            item = QTreeWidgetItem([f"🎵 {data['title']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, data['path'])
            album_node.addChild(item)

        elif "Álbumes" in mode:
            # Álbum -> Canción
            album = data['album']
            album_node = self._find_or_create_node(self.library_widget.invisibleRootItem(), f"💿 {album}")
            item = QTreeWidgetItem([f"🎵 {data['title']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, data['path'])
            album_node.addChild(item)

    def _find_or_create_node(self, parent, text):
        for i in range(parent.childCount()):
            if parent.child(i).text(0) == text:
                return parent.child(i)
        new_node = QTreeWidgetItem([text])
        parent.addChild(new_node)
        return new_node

    def reorganize_library(self):
        self.library_widget.clear()
        for data in self.library_data:
            self._add_to_tree(data)

    def clear_library(self):
        self.library_data = []
        self.library_widget.clear()
        self.status_label.setText("Biblioteca despejada.")

    def library_item_double_clicked(self, index):
        item = self.library_widget.itemFromIndex(index)
        path = item.data(0, Qt.ItemDataRole.UserRole)
        
        if path and os.path.exists(path):
            # Si el item tiene path, es una canción
            data = next((d for d in self.library_data if d['path'] == path), None)
            if data:
                track = Track(
                    id=data['filename'], title=data['title'], artist=data['artist'],
                    album=data['album'], file_path=path, duration=data['duration'],
                    source="local"
                )
                self._add_track_to_ui(track)
                self.tabs.setCurrentIndex(1)
                if self.player.state != PlayerState.PLAYING:
                    self.load_track_into_ui(len(self.playlist.tracks) - 1)
                    self.player.play()

    def library_context_menu(self, pos):
        """Menú contextual para la biblioteca."""
        menu = QMenu(self)
        item = self.library_widget.itemAt(pos)
        
        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path: # Es una canción
                play_action = menu.addAction("▶️ Añadir y Reproducir")
                play_action.triggered.connect(lambda: self.library_item_double_clicked(self.library_widget.indexAt(pos)))
                
                edit_action = menu.addAction("📝 Editar Etiquetas")
                edit_action.triggered.connect(lambda: self.open_tag_editor(item))
                menu.addSeparator()
        
        add_folder_action = menu.addAction("📁 Añadir Carpeta...")
        add_folder_action.triggered.connect(self.add_folder_to_library)
        
        menu.exec(self.library_widget.mapToGlobal(pos))

    def open_tag_editor(self, list_item):
        """Abre el diálogo de edición de etiquetas para el item seleccionado."""
        # Obtener el path del archivo diferenciando entre QTreeWidget (Biblioteca) y QListWidget (Playlist)
        if hasattr(list_item, "childCount"): # Es un QTreeWidgetItem (Biblioteca)
            path = list_item.data(0, Qt.ItemDataRole.UserRole)
        else: # Es un QListWidgetItem (Playlist)
            path = list_item.data(Qt.ItemDataRole.UserRole)
        
        # Si el path es un índice (en la playlist guardamos el índice en UserRole)
        if not isinstance(path, str) and path is not None:
            try:
                idx = int(path)
                if 0 <= idx < len(self.playlist.tracks):
                    track = self.playlist.tracks[idx]
                    path = track.file_path
                else:
                    return
            except (ValueError, TypeError):
                return
        
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "No se puede editar: archivo no encontrado.")
            return

        # Sacar metadatos actuales para el editor
        meta = self.metadata.get_metadata(path)
        
        # Abrir diálogo
        dialog = TagEditorDialog(path, meta, self.metadata, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Si se guardó, refrescar la UI
            self.status_label.setText("Metadatos actualizados en el archivo.")
            self.reorganize_library()
