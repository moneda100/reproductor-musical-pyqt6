from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QLabel, QListWidget, QListWidgetItem,
                             QMessageBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap
import requests
import os

class TagEditorDialog(QDialog):
    def __init__(self, file_path, metadata, metadata_service, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.metadata = metadata
        self.ms = metadata_service
        self.temp_cover_data = None
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.setWindowTitle("Editor de Metadatos")
        self.resize(500, 600)
        self.setStyleSheet("""
            QDialog { background-color: #1A1A1A; color: white; }
            QLineEdit { 
                background-color: #2A2A2A; 
                border: 1px solid #333; 
                border-radius: 5px; 
                padding: 8px; 
                color: white; 
            }
            QLabel { color: #BBB; font-weight: bold; }
            QPushButton { 
                padding: 8px 15px; 
                border-radius: 5px; 
                font-weight: bold; 
            }
            #SaveBtn { background-color: #E63946; color: white; }
            #SearchBtn { background-color: #333; color: white; border: 1px solid #444; }
            QListWidget { background-color: #222; border: none; border-radius: 5px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #333; color: #EEE; }
            QListWidget::item:selected { background-color: #333; color: #E63946; }
        """)

        layout = QVBoxLayout(self)

        # Portada Previa
        top_layout = QHBoxLayout()
        self.cover_prev = QLabel()
        self.cover_prev.setFixedSize(120, 120)
        self.cover_prev.setStyleSheet("background-color: #222; border-radius: 10px;")
        self.cover_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.cover_prev)

        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("Ruta del archivo:"))
        self.path_label = QLabel(os.path.basename(self.file_path))
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("font-size: 10px; color: #888;")
        info_layout.addWidget(self.path_label)
        top_layout.addLayout(info_layout)
        layout.addLayout(top_layout)

        # Campos
        self.title_input = QLineEdit()
        self.artist_input = QLineEdit()
        self.album_input = QLineEdit()
        
        layout.addWidget(QLabel("Título"))
        layout.addWidget(self.title_input)
        layout.addWidget(QLabel("Artista"))
        layout.addWidget(self.artist_input)
        layout.addWidget(QLabel("Álbum"))
        layout.addWidget(self.album_input)

        # Botón Buscar
        self.search_btn = QPushButton("🔍 Buscar Sugerencias Online")
        self.search_btn.setObjectName("SearchBtn")
        self.search_btn.clicked.connect(self.search_suggestions)
        layout.addWidget(self.search_btn)

        # Lista de Sugerencias
        layout.addWidget(QLabel("Sugerencias similares:"))
        self.suggest_list = QListWidget()
        self.suggest_list.itemClicked.connect(self.apply_suggestion)
        layout.addWidget(self.suggest_list)

        # Acciones
        btns = QHBoxLayout()
        self.save_btn = QPushButton("💾 Guardar en Archivo")
        self.save_btn.setObjectName("SaveBtn")
        self.save_btn.clicked.connect(self.save_tags)
        
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        layout.addLayout(btns)

    def load_data(self):
        self.title_input.setText(self.metadata.get('title', ''))
        self.artist_input.setText(self.metadata.get('artist', ''))
        self.album_input.setText(self.metadata.get('album', ''))
        
        if self.metadata.get('cover_data'):
            pixmap = QPixmap()
            pixmap.loadFromData(self.metadata['cover_data'])
            self.update_cover_preview(pixmap)
        else:
            self.cover_prev.setText("Sin Portada")

    def update_cover_preview(self, pixmap):
        if not pixmap.isNull():
            scaled = pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_prev.setPixmap(scaled)
        else:
            self.cover_prev.setText("Error")

    def search_suggestions(self):
        query = f"{self.title_input.text()} {self.artist_input.text()}"
        self.search_btn.setEnabled(False)
        self.search_btn.setText("⏳ Buscando...")
        
        # En una app real usaríamos un hilo, aquí para simplicidad directo con QApplication.processEvents
        suggestions = self.ms.search_metadata_suggestions(query)
        self.suggest_list.clear()
        
        for s in suggestions:
            detail = f"🎵 {s['title']}\n🎤 {s['artist']} - {s['album']}"
            if s.get('year') or s.get('genre'):
                detail += f"\n📅 {s['year']}  •  🏷️ {s['genre']}"
            
            item = QListWidgetItem(detail)
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.suggest_list.addItem(item)
        
        if not suggestions:
            QMessageBox.information(self, "Info", "No se encontraron sugerencias.")
            
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 Buscar Sugerencias Online")

    def apply_suggestion(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.title_input.setText(data['title'])
        self.artist_input.setText(data['artist'])
        self.album_input.setText(data['album'])
        
        # Descargar carátula de sugerencia
        if data['cover_url']:
            try:
                res = requests.get(data['cover_url'], timeout=5)
                if res.status_code == 200:
                    self.temp_cover_data = res.content
                    pixmap = QPixmap()
                    pixmap.loadFromData(res.content)
                    self.update_cover_preview(pixmap)
            except Exception as e:
                print(f"Error cargando portada de sugerencia: {e}")

    def save_tags(self):
        new_meta = {
            'title': self.title_input.text(),
            'artist': self.artist_input.text(),
            'album': self.album_input.text()
        }
        
        success = self.ms.update_metadata(self.file_path, new_meta, self.temp_cover_data)
        if success:
            QMessageBox.information(self, "Éxito", "Metadatos actualizados correctamente.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "No se pudieron guardar los cambios en el archivo.")
