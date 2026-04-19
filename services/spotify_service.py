import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Optional

class SpotifyService:
    """Búsqueda de artistas/álbumes similares vía Spotify."""
    
    def __init__(self, client_id: str = "", client_secret: str = ""):
        """
        Obtén credenciales gratis en: https://developer.spotify.com/
        """
        if client_id and client_secret:
            auth_manager = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
        else:
            self.sp = None
    
    def search_artist(self, artist_name: str) -> Optional[dict]:
        """Busca un artista."""
        if not self.sp:
            return None
        
        try:
            results = self.sp.search(q=f"artist:{artist_name}", type='artist', limit=1)
            artists = results.get('artists', {}).get('items', [])
            if artists:
                artist = artists[0]
                return {
                    'name': artist['name'],
                    'genres': artist.get('genres', []),
                    'popularity': artist.get('popularity', 0),
                    'image': artist['images'][0]['url'] if artist['images'] else None,
                    'external_url': artist['external_urls']['spotify']
                }
        except Exception as e:
            print(f"Error buscando artista: {e}")
        return None
    
    def get_similar_artists(self, artist_name: str, limit: int = 5) -> List[dict]:
        """Obtiene artistas similares."""
        if not self.sp:
            return []
        
        try:
            # Primero buscar el artista
            artist_info = self.search_artist(artist_name)
            if not artist_info:
                return []
            
            # Obtener artistas similares
            results = self.sp.search(q=f"artist:{artist_name}", type='artist', limit=1)
            if not results['artists']['items']:
                 return []
            artist_id = results['artists']['items'][0]['id']
            
            similar = self.sp.artist_related_artists(artist_id)
            return [
                {
                    'name': a['name'],
                    'genres': a.get('genres', []),
                    'image': a['images'][0]['url'] if a['images'] else None
                }
                for a in similar['artists'][:limit]
            ]
        except Exception as e:
            print(f"Error obteniendo similares: {e}")
            return []
    
    def get_album_info(self, artist_name: str, album_name: str) -> Optional[dict]:
        """Obtiene información del álbum."""
        if not self.sp:
            return None
        
        try:
            query = f'artist:{artist_name} album:{album_name}'
            results = self.sp.search(q=query, type='album', limit=1)
            albums = results.get('albums', {}).get('items', [])
            
            if albums:
                album = albums[0]
                return {
                    'name': album['name'],
                    'artist': album['artists'][0]['name'],
                    'release_date': album['release_date'],
                    'total_tracks': album['total_tracks'],
                    'image': album['images'][0]['url'] if album['images'] else None
                }
        except Exception as e:
            print(f"Error obteniendo álbum: {e}")
        return None
