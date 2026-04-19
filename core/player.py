import vlc
from typing import Optional, Callable, List
from enum import Enum
import os

class PlayerState(Enum):
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2

class MusicPlayer:
    """Motor de reproducción con VLC. Reproduce archivos locales (incluidos los descargados de YouTube)."""
    
    def __init__(self):
        self.instance = vlc.Instance('--quiet')
        if not self.instance:
            raise Exception("No se pudo inicializar VLC. ¿Está instalado?")
        self.player = self.instance.media_player_new()
        self.current_media = None
        self.current_track: Optional[str] = None
        self.state = PlayerState.STOPPED
        self.volume = 0.7
        self.callbacks = {}
        self.player.audio_set_volume(int(self.volume * 100))
        
    def set_video_widget(self, win_id: int):
        """Vincula el reproductor de video a un frame de la interfaz de usuario."""
        import sys
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(win_id)
        elif sys.platform == "win32":
            self.player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(win_id)
        
    def load(self, source: str) -> bool:
        """Carga un archivo local o una URL de stream."""
        try:
            if source.startswith("http://") or source.startswith("https://"):
                print(f"[DEBUG] VLC cargando stream: {source[:50]}...")
                self.current_media = self.instance.media_new(source)
            else:
                path = os.path.abspath(source)
                print(f"[DEBUG] VLC cargando archivo local: {path}")
                self.current_media = self.instance.media_new_path(path)
                
            self.player.set_media(self.current_media)
            self.current_track = source
            return True
        except Exception as e:
            print(f"[DEBUG] Error al cargar: {e}")
            return False
    
    def play(self) -> None:
        if not self.current_media: return
        res = self.player.play()
        if res == -1:
            print("[DEBUG] VLC fallo al iniciar reproducción")
        else:
            self.state = PlayerState.PLAYING
            self._trigger_callback('state_changed')
    
    def pause(self) -> None:
        self.player.pause()
        self.state = PlayerState.PAUSED
        self._trigger_callback('state_changed')
    
    def stop(self) -> None:
        self.player.stop()
        self.state = PlayerState.STOPPED
        self._trigger_callback('state_changed')
    
    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        self.player.audio_set_volume(int(self.volume * 100))
    
    def get_position(self) -> float:
        t = self.player.get_time()
        return t / 1000.0 if t > 0 else 0.0
    
    def set_position(self, seconds: float) -> None:
        if self.current_media:
            self.player.set_time(int(seconds * 1000))
    
    def register_callback(self, event: str, callback: Callable) -> None:
        if event not in self.callbacks: self.callbacks[event] = []
        self.callbacks[event].append(callback)
    
    def _trigger_callback(self, event: str) -> None:
        for cb in self.callbacks.get(event, []): cb()
