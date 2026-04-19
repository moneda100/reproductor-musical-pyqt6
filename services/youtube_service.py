import yt_dlp
import os
from pathlib import Path
from typing import Optional, List

class YouTubeService:
    """Servicio de YouTube con descarga a caché local y soporte de playlists."""
    
    def __init__(self, cache_dir: str = None):
        # Usar ruta absoluta para evitar problemas de CWD
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.download_dir = self.cache_dir  # Por defecto descarga en caché
        
    def set_download_dir(self, new_dir: str):
        self.download_dir = Path(new_dir)
        self.download_dir.mkdir(exist_ok=True, parents=True)
    
    def get_info(self, url: str, permanent: bool = False) -> Optional[dict]:
        """
        Descarga audio de YouTube.
        Si permanent=False: Guarda en cache/ sin conversión (rápido).
        Si permanent=True: Guarda en download_dir como MP3 con metadatos.
        """
        try:
            if permanent:
                # Modo MP3 con Metadatos
                output_template = str(self.download_dir / "%(title)s - %(uploader)s.%(ext)s")
                postprocessors = [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    },
                    {
                        'key': 'FFmpegMetadata',
                        'add_metadata': True,
                    },
                    {
                        'key': 'EmbedThumbnail',
                        'already_have_thumbnail': False,
                    }
                ]
            else:
                # Modo Caché (Rápido)
                output_template = str(self.cache_dir / "%(id)s.%(ext)s")
                postprocessors = []

            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'outtmpl': output_template,
                'extractor_args': {'youtube': {'player_client': ['android_music', 'android']}},
            }

            if permanent:
                ydl_opts['writethumbnail'] = True
                ydl_opts['postprocessors'] = postprocessors

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                
                base_file = ydl.prepare_filename(info)
                if permanent:
                    local_file = os.path.abspath(os.path.splitext(base_file)[0] + ".mp3")
                else:
                    local_file = os.path.abspath(base_file)
                
                if not os.path.exists(local_file):
                    print(f"[DEBUG] Archivo no encontrado: {local_file}")
                    return None
                
                print(f"[DEBUG] Audio {'permanente' if permanent else 'temporal'} descargado: {local_file}")
                
                return {
                    'id': info.get('id'),
                    'title': info.get('title', 'Sin título'),
                    'artist': info.get('uploader', 'Desconocido'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'local_file': local_file,
                    'webpage_url': info.get('webpage_url')
                }
        except Exception as e:
            print(f"[DEBUG] Error en get_info: {e}")
            return None

    def get_playlist_info(self, url: str) -> List[dict]:
        """Extrae metadatos de todos los videos de una playlist de YouTube (sin descargar)."""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Solo metadatos, no descargar
                'noplaylist': False,   # Permitir playlists
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                entries = info.get('entries', [])
                if not entries:
                    return []
                
                playlist_title = info.get('title', 'Playlist')
                print(f"[DEBUG] Playlist: {playlist_title} ({len(entries)} videos)")
                
                return [
                    {
                        'id': entry.get('id'),
                        'title': entry.get('title', 'Sin título'),
                        'artist': entry.get('uploader', 'Desconocido'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'duration': entry.get('duration', 0),
                        'thumbnail': entry.get('thumbnail'),
                        'playlist': playlist_title
                    }
                    for entry in entries if entry.get('id')
                ]
        except Exception as e:
            print(f"[DEBUG] Error en get_playlist_info: {e}")
            return []
    
    def search_songs(self, query: str, max_results: int = 5) -> List[dict]:
        """Busca canciones (rápido, sin descargar)."""
        try:
            search_url = f"ytsearch{max_results}:{query}"
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True, 
                'no_warnings': True, 
                'extract_flat': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(search_url, download=False)
                return [
                    {
                        'id': entry.get('id'),
                        'title': entry.get('title', 'Sin título'),
                        'artist': entry.get('uploader', 'Desconocido'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'duration': entry.get('duration', 0),
                        'thumbnail': entry.get('thumbnail')
                    }
                    for entry in results.get('entries', [])
                ]
        except Exception as e:
            print(f"[DEBUG] Error en search_songs: {e}")
            return []

    def get_stream_url(self, url: str) -> Optional[str]:
        """Extrae la URL directa del stream con mejor calidad (Video + Audio) sin descargar."""
        try:
            ydl_opts = {
                'format': 'best', # Intenta obtener un formato que contenga ambos combinados, ideal para VLC
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'url' in info:
                    return info['url']
                elif 'entries' in info and len(info['entries']) > 0:
                    return info['entries'][0].get('url')
        except Exception as e:
            print(f"[DEBUG] Error extrayendo stream_url: {e}")
        return None
    
    def cleanup(self):
        """Limpia archivos del caché."""
        count = 0
        for f in self.cache_dir.glob("*"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        print(f"[DEBUG] Caché limpiado: {count} archivos eliminados")
