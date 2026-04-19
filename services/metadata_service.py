from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.wave import WAVE
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
import mutagen
import requests
import re
from pathlib import Path
from typing import Optional, Tuple
import uuid

class MetadataService:
    """Extrae metadatos de archivos de audio locales."""
    
    SUPPORTED_FORMATS = {
        '.mp3': MP3,
        '.flac': FLAC,
        '.wav': WAVE,
        '.m4a': MP4,
        '.mp4': MP4
    }

    def get_metadata(self, file_path: str) -> dict:
        """Extrae metadatos básicos y portada si existe."""
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in self.SUPPORTED_FORMATS:
            return self._default_metadata(path.name)
            
        try:
            audio = self.SUPPORTED_FORMATS[path.suffix.lower()](file_path)
            metadata = self._default_metadata(path.name)
            
            # Duración
            metadata['duration'] = audio.info.length
            
            # Extraer tags según el formato
            ext = path.suffix.lower()
            if ext == '.mp3':
                if audio.tags:
                    metadata['title'] = str(audio.tags.get('TIT2', path.name))
                    metadata['artist'] = str(audio.tags.get('TPE1', 'Desconocido'))
                    metadata['album'] = str(audio.tags.get('TALB', 'Desconocido'))
                    
                    # Priorizar Front Cover (tipo 3)
                    for key in audio.tags.keys():
                        if key.startswith('APIC'):
                            tag = audio.tags[key]
                            if tag.type == 3: # Front Cover
                                metadata['cover_data'] = tag.data
                                break
                    # Fallback a cualquier APIC si no hay tipo 3
                    if not metadata['cover_data']:
                        for tag in audio.tags.values():
                            if tag.__class__.__name__ == 'APIC':
                                metadata['cover_data'] = tag.data
                                break
                            
            elif ext == '.flac':
                if audio.tags:
                    metadata['title'] = audio.tags.get('title', [path.name])[0]
                    metadata['artist'] = audio.tags.get('artist', ['Desconocido'])[0]
                    metadata['album'] = audio.tags.get('album', ['Desconocido'])[0]
                    if audio.pictures:
                        metadata['cover_data'] = audio.pictures[0].data

            elif ext in ('.m4a', '.mp4'):
                if audio.tags:
                    metadata['title'] = audio.tags.get('\xa9nam', [path.name])[0]
                    metadata['artist'] = audio.tags.get('\xa9ART', ['Desconocido'])[0]
                    metadata['album'] = audio.tags.get('\xa9alb', ['Desconocido'])[0]
                    if 'covr' in audio.tags:
                        metadata['cover_data'] = audio.tags['covr'][0]

            # --- NUEVO: Búsqueda local si falla la incrustada ---
            if not metadata['cover_data']:
                local_cover = self._find_local_cover_file(path.parent)
                if local_cover:
                    with open(local_cover, "rb") as f:
                        metadata['cover_data'] = f.read()

            return metadata
        except Exception as e:
            print(f"Error extrayendo metadatos de {file_path}: {e}")
            return self._default_metadata(path.name)

    def _default_metadata(self, filename: str) -> dict:
        return {
            'title': filename,
            'artist': 'Desconocido',
            'album': 'Desconocido',
            'duration': 0.0,
            'cover_data': None
        }

    def _find_local_cover_file(self, directory: Path) -> Optional[Path]:
        """Busca archivos de imagen comunes en el directorio con priorización."""
        # Prioridad alta: nombres exactos de carátula
        high_priority = ('front', 'cover', 'folder', 'album')
        low_priority = ('art', 'back', 'disc')
        extensions = ('.jpg', '.jpeg', '.png')
        
        candidates = []
        for p in directory.glob("*"):
            if p.suffix.lower() in extensions:
                name = p.stem.lower()
                # Si coincide exactamente con alta prioridad, devolver ya
                if name in high_priority:
                    return p
                # Si contiene alta prioridad, añadir a candidatos
                for hp in high_priority:
                    if hp in name:
                        candidates.append((1, p))
                        break
                # Si contiene baja prioridad
                for lp in low_priority:
                    if lp in name:
                        candidates.append((2, p))
                        break
                # Añadir como genérico
                candidates.append((3, p))

        if candidates:
            # Ordenar por prioridad (menor número es mejor)
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        
        return None

    def _clean_text(self, text: str) -> str:
        """Limpia el texto de ruidos comunes (Official Video, prod by, etc.) para mejorar la búsqueda."""
        if not text: return ""
        # Eliminar contenido entre paréntesis o corchetes
        text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
        # Eliminar palabras clave de ruido
        noise = r'\b(official|video|audio|lyrics?|prod|produced|feat|ft|explicit|hd|4k|hq|remix)\b'
        text = re.sub(noise, '', text, flags=re.IGNORECASE)
        # Eliminar guiones, guiones bajos y símbolos raros (manteniendo $ si es parte del nombre)
        text = re.sub(r'[-_]', ' ', text)
        # Limpiar espacios extra
        return ' '.join(text.split()).strip()

    def fetch_online_cover(self, artist: str, album: str) -> Optional[str]:
        """Busca la URL de la portada con reintentos de limpieza."""
        # Intento 1: Tal cual
        url = self._do_itunes_cover_search(artist, album)
        if url: return url
        
        # Intento 2: Solo álbum limpio
        if album != "Desconocido":
            url = self._do_itunes_cover_search("", self._clean_text(album))
            if url: return url
            
        return None

    def _do_itunes_cover_search(self, artist: str, album: str) -> Optional[str]:
        try:
            query = f"{artist} {album}".strip()
            params = {'term': query, 'entity': 'album', 'limit': 1}
            url = "https://itunes.apple.com/search"
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                results = response.json().get('results', [])
                if results:
                    return results[0].get('artworkUrl100', '').replace('100x100', '600x600')
        except Exception: pass
        return None

    def is_generic_cover(self, url: str) -> bool:
        """Determina si un URL de imagen es un logo genérico o de baja calidad."""
        if not url or not isinstance(url, str): return True
        
        generic_patterns = [
            'ytimg.com',              # Todas las miniaturas base de YT
            'googleusercontent.com',  # A veces usado para miniaturas / logos
            'yt3.ggpht.com',          # Avatares de canal a veces genéricos
            'youtube.com/img',
            'static/images/playlist',
            'vi/',                    # Identificador común de thumbnails en URLs
            'default.jpg',
            'mqdefault.jpg',
            'hqdefault.jpg',
            'sddefault.jpg',
            'maxresdefault.jpg',
            'logo_youtube',
            'yt_logo'
        ]
        
        url_lower = url.lower()
        for pattern in generic_patterns:
            if pattern in url_lower:
                print(f"[DEBUG] Logo genérico/YouTube detectado: {url[:50]}...")
                return True
        return False

    def search_metadata_suggestions(self, query: str) -> list:
        """Busca múltiples sugerencias con lógica de multi-pasada y limpieza."""
        all_results = []
        
        # Pasada 1: Búsqueda original
        all_results.extend(self._do_itunes_suggestion_search(query, 8))
        
        # Pasada 2: Si hay pocos resultados, probar con búsqueda limpia
        clean_q = self._clean_text(query)
        if len(all_results) < 3 and clean_q != query:
            all_results.extend(self._do_itunes_suggestion_search(clean_q, 8))
            
        # Eliminar duplicados por ID de iTunes si estuviera disponible, o por Título+Artista
        seen = set()
        unique_results = []
        for res in all_results:
            key = f"{res['title']}|{res['artist']}".lower()
            if key not in seen:
                seen.add(key)
                unique_results.append(res)
                
        return unique_results[:15] # Retornar hasta 15 mejores opciones

    def _do_itunes_suggestion_search(self, query: str, limit: int) -> list:
        try:
            url = "https://itunes.apple.com/search"
            params = {'term': query, 'entity': 'song', 'limit': limit}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                results = response.json().get('results', [])
                suggestions = []
                for res in results:
                    suggestions.append({
                        'title': res.get('trackName', 'Desconocido'),
                        'artist': res.get('artistName', 'Desconocido'),
                        'album': res.get('collectionName', 'Desconocido'),
                        'genre': res.get('primaryGenreName', ''),
                        'year': res.get('releaseDate', '')[:4] if res.get('releaseDate') else '',
                        'cover_url': res.get('artworkUrl100', '').replace('100x100', '600x600')
                    })
                return suggestions
        except Exception: pass
        return []

    def update_metadata(self, file_path: str, new_meta: dict, cover_data: bytes = None) -> bool:
        """Escribe los nuevos metadatos y carátula directamente en el archivo."""
        path = Path(file_path)
        if not path.exists(): return False
        
        ext = path.suffix.lower()
        try:
            if ext == '.mp3':
                # Usar ID3 para MP3
                try:
                    tags = ID3(file_path)
                except Exception:
                    # Crear tags si no existen
                    tags = ID3()
                
                tags["TIT2"] = TIT2(encoding=3, text=new_meta.get('title', ''))
                tags["TPE1"] = TPE1(encoding=3, text=new_meta.get('artist', ''))
                tags["TALB"] = TALB(encoding=3, text=new_meta.get('album', ''))
                
                if cover_data:
                    tags.delall("APIC")
                    tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3,
                        desc='Cover', data=cover_data
                    ))
                tags.save(file_path)
                
            elif ext == '.flac':
                audio = FLAC(file_path)
                audio["title"] = new_meta.get('title', '')
                audio["artist"] = new_meta.get('artist', '')
                audio["album"] = new_meta.get('album', '')
                if cover_data:
                    audio.clear_pictures()
                    picture = Picture()
                    picture.data = cover_data
                    picture.type = 3
                    picture.mime = "image/jpeg"
                    audio.add_picture(picture)
                audio.save()

            elif ext in ('.m4a', '.mp4'):
                audio = MP4(file_path)
                audio.tags["\xa9nam"] = new_meta.get('title', '')
                audio.tags["\xa9ART"] = new_meta.get('artist', '')
                audio.tags["\xa9alb"] = new_meta.get('album', '')
                if cover_data:
                    audio.tags["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()
            
            return True
        except Exception as e:
            print(f"[DEBUG] Error actualizando archivo {file_path}: {e}")
            return False

    def save_cover(self, cover_data: bytes, output_dir: str = "./cache/covers") -> Optional[str]:
        """Guarda la portada extraída y retorna la ruta."""
        if not cover_data:
            return None
            
        try:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            
            file_name = f"{uuid.uuid4().hex}.jpg"
            file_path = out_path / file_name
            
            with open(file_path, "wb") as f:
                f.write(cover_data)
                
            return str(file_path)
        except Exception as e:
            print(f"Error guardando portada: {e}")
            return None
