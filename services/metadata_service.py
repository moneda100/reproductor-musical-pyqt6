"""Servicio de metadatos: extracción local (mutagen) y búsqueda online (iTunes)."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Optional

import requests
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from core.paths import get_paths

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
REQUEST_TIMEOUT = 8


class MetadataService:
    """Extrae metadatos de archivos de audio locales."""

    SUPPORTED_FORMATS = {
        ".mp3": MP3,
        ".flac": FLAC,
        ".wav": WAVE,
        ".m4a": MP4,
        ".mp4": MP4,
    }

    def get_metadata(self, file_path: str, with_cover: bool = True) -> dict:
        """Extrae metadatos básicos y, opcionalmente, la portada incrustada.

        ``with_cover=False`` evita decodificar la imagen en cada llamada: es el
        modo que usa el escaneo de biblioteca (la carátula se resuelve bajo
        demanda y se cachea por hash de URL).
        """
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in self.SUPPORTED_FORMATS:
            return self._default_metadata(path.name)

        try:
            audio = self.SUPPORTED_FORMATS[path.suffix.lower()](file_path)
            metadata = self._default_metadata(path.name)

            metadata["duration"] = audio.info.length

            ext = path.suffix.lower()
            if ext == ".mp3":
                self._read_mp3(audio, metadata, path)
            elif ext == ".flac":
                self._read_flac(audio, metadata, path)
            elif ext in (".m4a", ".mp4"):
                self._read_mp4(audio, metadata, path)

            if not metadata["cover_data"] and with_cover:
                local_cover = self._find_local_cover_file(path.parent)
                if local_cover:
                    with open(local_cover, "rb") as handle:
                        metadata["cover_data"] = handle.read()

            return metadata
        except Exception as exc:  # noqa: BLE001 - un archivo corrupto no rompe el escaneo
            logger.warning("Error extrayendo metadatos de %s: %s", file_path, exc)
            return self._default_metadata(path.name)

    # -- lectores por formato ---------------------------------------
    def _read_mp3(self, audio, metadata: dict, path: Path) -> None:
        if not audio.tags:
            return
        metadata["title"] = str(audio.tags.get("TIT2", path.name))
        metadata["artist"] = str(audio.tags.get("TPE1", "Desconocido"))
        metadata["album"] = str(audio.tags.get("TALB", "Desconocido"))
        metadata["genre"] = str(audio.tags.get("TCON", ""))
        metadata["year"] = str(audio.tags.get("TDRC", ""))
        # Leer letras incrustadas (USLT - Unsynchronised Lyric)
        lyrics_texts = []
        for key in audio.tags.keys():
            if key.startswith("USLT"):
                tag = audio.tags[key]
                if getattr(tag, "text", None):
                    lyrics_texts.append(str(tag.text))
        if not lyrics_texts:
            for tag in audio.tags.values():
                if tag.__class__.__name__ == "USLT" and getattr(tag, "text", None):
                    lyrics_texts.append(str(tag.text))
        if lyrics_texts:
            metadata["lyrics"] = "\n".join(lyrics_texts)
        # Carátula
        for key in audio.tags.keys():
            if key.startswith("APIC"):
                tag = audio.tags[key]
                if tag.type == 3:  # Front Cover
                    metadata["cover_data"] = tag.data
                    break
        if not metadata["cover_data"]:
            for tag in audio.tags.values():
                if tag.__class__.__name__ == "APIC":
                    metadata["cover_data"] = tag.data
                    break

    def _read_flac(self, audio, metadata: dict, path: Path) -> None:
        if not audio.tags:
            return
        metadata["title"] = audio.tags.get("title", [path.name])[0]
        metadata["artist"] = audio.tags.get("artist", ["Desconocido"])[0]
        metadata["album"] = audio.tags.get("album", ["Desconocido"])[0]
        metadata["genre"] = audio.tags.get("genre", [""])[0] if audio.tags.get("genre") else ""
        metadata["year"] = audio.tags.get("date", [""])[0] if audio.tags.get("date") else ""
        # Leer letras incrustadas en FLAC (campo LYRICS o comentarios)
        lyrics_texts = []
        if audio.tags.get("lyrics"):
            lyrics_texts.append(str(audio.tags["lyrics"][0]))
        if audio.tags.get("LYRICS"):
            lyrics_texts.append(str(audio.tags["LYRICS"][0]))
        # También buscar en comentarios
        for key in audio.tags:
            if key.lower() in ("lyrics", "comment") and audio.tags[key]:
                lyrics_texts.append(str(audio.tags[key][0]))
        if lyrics_texts:
            metadata["lyrics"] = "\n".join(lyrics_texts)
        if audio.pictures:
            metadata["cover_data"] = audio.pictures[0].data

    def _read_mp4(self, audio, metadata: dict, path: Path) -> None:
        if not audio.tags:
            return
        metadata["title"] = audio.tags.get("\xa9nam", [path.name])[0]
        metadata["artist"] = audio.tags.get("\xa9ART", ["Desconocido"])[0]
        metadata["album"] = audio.tags.get("\xa9alb", ["Desconocido"])[0]
        metadata["genre"] = audio.tags.get("\xa9gen", [""])[0] if audio.tags.get("\xa9gen") else ""
        metadata["year"] = audio.tags.get("\xa9day", [""])[0] if audio.tags.get("\xa9day") else ""
        # Leer letras incrustadas en MP4 (\xa9lyr)
        if audio.tags.get("\xa9lyr"):
            metadata["lyrics"] = str(audio.tags["\xa9lyr"][0])
        if "covr" in audio.tags:
            metadata["cover_data"] = audio.tags["covr"][0]

    def _default_metadata(self, filename: str) -> dict:
        return {
            "title": filename,
            "artist": "Desconocido",
            "album": "Desconocido",
            "genre": "",
            "year": "",
            "duration": 0.0,
            "cover_data": None,
            "lyrics": "",
        }

    def _find_local_cover_file(self, directory: Path) -> Optional[Path]:
        """Busca archivos de imagen comunes en el directorio con priorización."""
        high_priority = ("front", "cover", "folder", "album")
        low_priority = ("art", "back", "disc")
        extensions = (".jpg", ".jpeg", ".png")

        candidates = []
        for p in directory.glob("*"):
            if p.suffix.lower() in extensions:
                name = p.stem.lower()
                if name in high_priority:
                    return p
                for hp in high_priority:
                    if hp in name:
                        candidates.append((1, p))
                        break
                for lp in low_priority:
                    if lp in name:
                        candidates.append((2, p))
                        break
                candidates.append((3, p))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None

    # -- limpieza y búsqueda online --------------------------------
    def _clean_text(self, text: str) -> str:
        """Limpia el texto de ruidos comunes (Official Video, prod by, etc.)."""
        if not text:
            return ""
        text = re.sub(r"\(.*?\)|\[.*?\]", "", text)
        noise = r"\b(official|video|audio|lyrics?|prod|produced|feat|ft|explicit|hd|4k|hq|remix)\b"
        text = re.sub(noise, "", text, flags=re.IGNORECASE)
        text = re.sub(r"[-_]", " ", text)
        return " ".join(text.split()).strip()

    def fetch_online_cover(self, artist: str, album: str) -> Optional[str]:
        """Busca la URL de la portada con reintentos de limpieza."""
        url = self._do_itunes_cover_search(artist, album)
        if url:
            return url
        if album != "Desconocido":
            url = self._do_itunes_cover_search("", self._clean_text(album))
            if url:
                return url
        return None

    def _do_itunes_cover_search(self, artist: str, album: str) -> Optional[str]:
        try:
            query = f"{artist} {album}".strip()
            params = {"term": query, "entity": "album", "limit": 1}
            response = requests.get(
                ITUNES_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT, headers=HEADERS
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return (results[0].get("artworkUrl100") or "").replace("100x100", "600x600")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Búsqueda de portada en iTunes falló: %s", exc)
        return None

    def is_generic_cover(self, url: str) -> bool:
        """Indica si una URL de imagen es un logo genérico o una miniatura vacía.

        Las miniaturas reales de YouTube (``i.ytimg.com/vi/<id>/hqdefault.jpg``
        y compañía) **no** son genéricas: son la mejor portada disponible para
        una pista de YouTube y se conservan.
        """
        if not url or not isinstance(url, str):
            return True

        # YouTube thumbnails NO son genéricas - son la mejor portada disponible
        if "i.ytimg.com/vi/" in url:
            return False

        generic_patterns = [
            "googleusercontent.com",
            "youtube.com/img",
            "static/images/playlist",
            "default.jpg",
            "logo_youtube",
            "yt_logo",
        ]

        url_lower = url.lower()
        for pattern in generic_patterns:
            if pattern in url_lower:
                logger.debug("Portada genérica detectada: %s", url[:60])
                return True
        return False

    def search_metadata_suggestions(self, query: str) -> list:
        """Busca múltiples sugerencias con lógica de multi-pasada y limpieza."""
        all_results: list[dict] = []
        all_results.extend(self._do_itunes_suggestion_search(query, 8))

        clean_q = self._clean_text(query)
        if len(all_results) < 3 and clean_q != query:
            all_results.extend(self._do_itunes_suggestion_search(clean_q, 8))

        seen = set()
        unique_results = []
        for res in all_results:
            key = f"{res['title']}|{res['artist']}".lower()
            if key not in seen:
                seen.add(key)
                unique_results.append(res)
        return unique_results[:15]

    def _do_itunes_suggestion_search(self, query: str, limit: int) -> list:
        try:
            params = {"term": query, "entity": "song", "limit": limit}
            response = requests.get(
                ITUNES_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT, headers=HEADERS
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                suggestions = []
                for res in results:
                    suggestions.append(
                        {
                            "title": res.get("trackName", "Desconocido"),
                            "artist": res.get("artistName", "Desconocido"),
                            "album": res.get("collectionName", "Desconocido"),
                            "genre": res.get("primaryGenreName", ""),
                            "year": res.get("releaseDate", "")[:4]
                            if res.get("releaseDate")
                            else "",
                            "cover_url": (res.get("artworkUrl100") or "").replace(
                                "100x100", "600x600"
                            ),
                        }
                    )
                return suggestions
        except Exception as exc:  # noqa: BLE001
            logger.debug("Búsqueda de sugerencias falló: %s", exc)
        return []

    # -- escritura --------------------------------------------------
    def update_metadata(
        self, file_path: str, new_meta: dict, cover_data: bytes | None = None
    ) -> bool:
        """Escribe los nuevos metadatos y carátula directamente en el archivo."""
        path = Path(file_path)
        if not path.exists():
            return False

        ext = path.suffix.lower()
        try:
            if ext == ".mp3":
                try:
                    tags = ID3(file_path)
                except Exception:  # noqa: BLE001 - el archivo no tenía tags
                    tags = ID3()

                tags["TIT2"] = TIT2(encoding=3, text=new_meta.get("title", ""))
                tags["TPE1"] = TPE1(encoding=3, text=new_meta.get("artist", ""))
                tags["TALB"] = TALB(encoding=3, text=new_meta.get("album", ""))
                if new_meta.get("genre"):
                    tags["TCON"] = TCON(encoding=3, text=new_meta["genre"])
                if new_meta.get("year"):
                    tags["TDRC"] = TDRC(encoding=3, text=new_meta["year"])

                if cover_data:
                    tags.delall("APIC")
                    tags.add(
                        APIC(
                            encoding=3,
                            mime="image/jpeg",
                            type=3,
                            desc="Cover",
                            data=cover_data,
                        )
                    )
                tags.save(file_path)

            elif ext == ".flac":
                audio = FLAC(file_path)
                audio["title"] = new_meta.get("title", "")
                audio["artist"] = new_meta.get("artist", "")
                audio["album"] = new_meta.get("album", "")
                if new_meta.get("genre"):
                    audio["genre"] = new_meta["genre"]
                if new_meta.get("year"):
                    audio["date"] = new_meta["year"]
                if cover_data:
                    audio.clear_pictures()
                    picture = Picture()
                    picture.data = cover_data
                    picture.type = 3
                    picture.mime = "image/jpeg"
                    audio.add_picture(picture)
                audio.save()

            elif ext in (".m4a", ".mp4"):
                audio = MP4(file_path)
                audio.tags["\xa9nam"] = new_meta.get("title", "")
                audio.tags["\xa9ART"] = new_meta.get("artist", "")
                audio.tags["\xa9alb"] = new_meta.get("album", "")
                if new_meta.get("genre"):
                    audio.tags["\xa9gen"] = new_meta["genre"]
                if new_meta.get("year"):
                    audio.tags["\xa9day"] = new_meta["year"]
                if cover_data:
                    audio.tags["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()

            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error actualizando archivo %s: %s", file_path, exc)
            return False

    def save_cover(self, cover_data: bytes, output_dir: str | None = None) -> Optional[str]:
        """Guarda la portada extraída y retorna su ruta.

        Por defecto escribe en la caché de la aplicación (no en el CWD), de
        modo que funciona con el ejecutable empaquetado.
        """
        if not cover_data:
            return None

        try:
            out_path = Path(output_dir) if output_dir else get_paths().covers_dir
            out_path.mkdir(parents=True, exist_ok=True)

            file_path = out_path / f"{uuid.uuid4().hex}.jpg"
            with open(file_path, "wb") as handle:
                handle.write(cover_data)
            return str(file_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error guardando portada: %s", exc)
            return None
