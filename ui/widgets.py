from PyQt6.QtWidgets import QSlider, QLabel, QStyleOptionSlider
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap
import requests
import os
from pathlib import Path

class ImageLoaderThread(QThread):
    """Hilo encargado de descargar imágenes de internet para no bloquear la UI."""
    image_loaded = pyqtSignal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            # User-Agent para evitar bloqueos de servidores de imágenes
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(self.url, headers=headers, timeout=5)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                if not pixmap.isNull():
                    self.image_loaded.emit(pixmap)
        except Exception as e:
            print(f"[DEBUG] Error cargando imagen web: {e}")

class ClickableSlider(QSlider):
    """Slider personalizado que permite saltar de posición haciendo clic."""
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.pixelPosToRangeValue(event.position())
            self.setValue(int(val))
            self.sliderReleased.emit()

    def pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(
            self.style().ComplexControl.CC_Slider, 
            opt, 
            self.style().SubControl.SC_SliderGroove, 
            self)
        x = pos.x() - rect.x()
        c = rect.width()
        if c == 0: return 0
        min_v, max_v = self.minimum(), self.maximum()
        return min_v + (max_v - min_v) * x / c

class CoverArtLabel(QLabel):
    """Label personalizado para mostrar portadas con carga asíncrona segura."""
    def __init__(self, size: int = 200, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"background-color: #2A2A2A; border-radius: 12px;")
        self.setText("Música")
        self.active_threads = [] # Mantener referencias a hilos en ejecución

    def set_cover(self, image_source: str):
        if not image_source:
            self.set_placeholder()
            return

        # Limpiar hilos finalizados
        self.active_threads = [t for t in self.active_threads if t.isRunning()]

        # Si es una URL, cargar de forma asíncrona
        if image_source.startswith("http"):
            # Opcional: Detener hilos anteriores si queremos solo la última imagen
            for t in self.active_threads:
                t.disconnect() # Desconectar para que no actualicen la UI
            
            thread = ImageLoaderThread(image_source)
            thread.image_loaded.connect(self._apply_pixmap)
            # Eliminar del listado cuando termine
            thread.finished.connect(lambda: self._cleanup_thread(thread))
            self.active_threads.append(thread)
            thread.start()
        
        # Si es local, cargar normalmente
        elif os.path.exists(image_source):
            pixmap = QPixmap(image_source)
            self._apply_pixmap(pixmap)
        else:
            self.set_placeholder()

    def _cleanup_thread(self, thread):
        if thread in self.active_threads:
            self.active_threads.remove(thread)

    def _apply_pixmap(self, pixmap):
        if not pixmap.isNull():
            scaled = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled)
        else:
            self.set_placeholder()

    def set_placeholder(self):
        self.clear()
        self.setStyleSheet("""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1A1A1A, stop:1 #333);
            border-radius: 12px;
            font-size: 14px;
            font-weight: bold;
            color: #555;
            border: 1px solid #444;
        """)
        self.setText("Música 🎵")

class MarqueeLabel(QLabel):
    """Etiqueta que desplaza el texto horizontalmente si no cabe en el ancho disponible."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._offset = 0
        self._scroll_enabled = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_scroll)
        self._timer.start(30) # Un poco más rápido para fluidez
        self.setContentsMargins(5, 0, 5, 0)
        self.setWordWrap(False) # CRÍTICO: No queremos saltos de línea en el Marquee

    def setText(self, text):
        self._text = text
        self._offset = 0
        # Llamamos al padre para que se actualice el tamaño si es necesario (aunque solemos usar fixed width)
        super().setText(text)
        self._check_scroll()

    def _check_scroll(self):
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._text)
        # Solo activamos si el texto es más ancho que el control
        if text_width > self.width() and self.width() > 0:
            self._scroll_enabled = True
        else:
            self._scroll_enabled = False
            self._offset = 0
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll()

    def _update_scroll(self):
        # Asegurar que no hay wordwrap si se activó por error
        if self.wordWrap():
            self.setWordWrap(False)
            
        if self._scroll_enabled and self.isVisible():
            self._offset += 1
            fm = self.fontMetrics()
            text_width = fm.horizontalAdvance(self._text)
            # Loop cuando el texto termina (+ un pequeño margen de 50px)
            if self._offset > text_width + 50:
                self._offset = -50
            self.update()

    def paintEvent(self, event):
        if not self._scroll_enabled:
            super().paintEvent(event)
            return

        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        fm = self.fontMetrics()
        
        # Centrado vertical preciso
        content_rect = self.contentsRect()
        # El fm.ascent() nos da la línea base desde donde se dibuja el texto
        y = (content_rect.height() - fm.height()) / 2 + fm.ascent()
        
        # Dibujar con el desplazamiento actual
        painter.drawText(content_rect.left() - self._offset, int(y), self._text)
        
        # Dibujar una segunda copia para el efecto de loop infinito (si el offset ya avanzó)
        text_width = fm.horizontalAdvance(self._text)
        painter.drawText(content_rect.left() - self._offset + text_width + 60, int(y), self._text)
        
        painter.end()
