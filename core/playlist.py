from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import json
import random
from enum import Enum

class RepeatMode(Enum):
    NONE = 0
    ALL = 1
    ONE = 2

@dataclass
class Track:
    """Representa una canción."""
    id: str
    title: str
    artist: str
    album: str
    file_path: str
    duration: float
    cover_url: Optional[str] = None
    source: str = "local"  # 'local' o 'youtube'
    headers: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist,
            'album': self.album,
            'file_path': self.file_path,
            'duration': self.duration,
            'cover_url': self.cover_url,
            'source': self.source,
            'headers': self.headers
        }

class Playlist:
    """Gestiona una lista de reproducción."""
    
    def __init__(self, name: str):
        self.name = name
        self.tracks: List[Track] = []
        self.current_index = 0
        self.shuffle = False
        self.repeat_mode = RepeatMode.NONE
        self._history = []  # Para navegar hacia atrás en modo shuffle
    
    def add_track(self, track: Track) -> None:
        """Agrega una canción."""
        self.tracks.append(track)
    
    def remove_track(self, index: int) -> None:
        """Elimina una canción por índice."""
        if 0 <= index < len(self.tracks):
            self.tracks.pop(index)
            if index < self.current_index:
                self.current_index -= 1
            if self.current_index >= len(self.tracks):
                self.current_index = max(0, len(self.tracks) - 1)
    
    def get_current_track(self) -> Optional[Track]:
        """Retorna la canción actual."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None
    
    def next(self) -> Optional[Track]:
        """Avanza a la siguiente canción."""
        if not self.tracks: 
            return None
            
        if self.repeat_mode == RepeatMode.ONE:
            return self.get_current_track()
            
        self._history.append(self.current_index)
        
        if self.shuffle:
            self.current_index = random.randint(0, len(self.tracks) - 1)
        else:
            if self.current_index < len(self.tracks) - 1:
                self.current_index += 1
            elif self.repeat_mode == RepeatMode.ALL:
                self.current_index = 0
            else:
                return None
                
        return self.get_current_track()
    
    def previous(self) -> Optional[Track]:
        """Retrocede a la canción anterior."""
        if not self.tracks:
            return None
            
        if self.repeat_mode == RepeatMode.ONE:
            return self.get_current_track()
            
        if self._history:
            self.current_index = self._history.pop()
        else:
            if self.current_index > 0:
                self.current_index -= 1
            elif self.repeat_mode == RepeatMode.ALL:
                self.current_index = len(self.tracks) - 1
                
        return self.get_current_track()
    
    def save_to_file(self, file_path: str) -> None:
        """Guarda playlist en JSON."""
        data = {
            'name': self.name,
            'tracks': [t.to_dict() for t in self.tracks]
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> 'Playlist':
        """Carga playlist desde JSON."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        playlist = cls(data['name'])
        for track_data in data['tracks']:
            track = Track(**track_data)
            playlist.add_track(track)
        return playlist
