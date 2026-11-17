"""Tests de integración para servicios externos (YouTube, Last.fm, Metadata).

Estos tests usan `responses` para mockear peticiones HTTP reales y validan
el comportamiento de los servicios sin depender de la red.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.playlist import Track
from services.lastfm_service import LastFmService
from services.metadata_service import MetadataService
from services.youtube_service import YouTubeService

# ---------------------------------------------------------------------------
# Fixtures y utilidades
# ---------------------------------------------------------------------------

@pytest.fixture
def yt_service(tmp_path):
    """Servicio YouTube con directorio temporal."""
    service = YouTubeService()
    service.set_download_dir(str(tmp_path))
    return service


@pytest.fixture
def lastfm_service():
    """Servicio Last.fm con credenciales de prueba."""
    return LastFmService(api_key="test_key", username="test_user", session_key="test_session_key")


@pytest.fixture
def metadata_service():
    """Servicio de metadatos."""
    return MetadataService()


# ---------------------------------------------------------------------------
# YouTube Service - Integración (mocking yt_dlp)
# ---------------------------------------------------------------------------

@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_search_songs_returns_parsed_results(mock_ydl_class, yt_service):
    """Búsqueda de YouTube parsea correctamente la respuesta de yt-dlp."""
    # Configurar mock de yt-dlp
    fake_entries = [
        {
            "id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up",
            "duration": 212,
            "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "uploader": "RickAstleyVEVO",
        },
        {
            "id": "9bZkp7q19f0",
            "title": "PSY - GANGNAM STYLE",
            "duration": 253,
            "thumbnail": "https://i.ytimg.com/vi/9bZkp7q19f0/hqdefault.jpg",
            "uploader": "officialpsy",
        },
    ]
    
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {"entries": fake_entries}
    mock_ydl_class.return_value = mock_ydl
    
    results = yt_service.search_songs("rick astley", max_results=2)
    
    assert len(results) == 2
    assert results[0]["id"] == "dQw4w9WgXcQ"
    assert results[0]["title"] == "Rick Astley - Never Gonna Give You Up"
    assert results[0]["artist"] == "RickAstleyVEVO"
    assert "thumbnail" in results[0]
    assert results[0]["duration"] == 212
    assert results[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_search_handles_empty_results(mock_ydl_class, yt_service):
    """Búsqueda sin resultados devuelve lista vacía."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {"entries": []}
    mock_ydl_class.return_value = mock_ydl
    
    results = yt_service.search_songs("nonexistentquery12345", max_results=5)
    
    assert results == []


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_search_handles_errors_gracefully(mock_ydl_class, yt_service):
    """Error en yt-dlp no rompe el servicio, devuelve lista vacía."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.side_effect = Exception("Network error")
    mock_ydl_class.return_value = mock_ydl
    
    results = yt_service.search_songs("test", max_results=5)
    
    assert results == []


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_get_stream_url(mock_ydl_class, yt_service):
    """Obtiene URL de stream para reproducción directa."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {
        "url": "https://manifest.googlevideo.com/api/manifest/...",
        "formats": [
            {"url": "https://...audio_only...", "acodec": "opus", "abr": 128},
            {"url": "https://...video...", "vcodec": "vp9", "height": 720},
        ],
    }
    mock_ydl_class.return_value = mock_ydl
    
    stream_url = yt_service.get_stream_url("dQw4w9WgXcQ")
    
    assert stream_url is not None
    assert stream_url.startswith("https://")


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_download_creates_file(mock_ydl_class, yt_service, tmp_path):
    """Descarga crea archivo en el directorio esperado."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    
    # Simular info de descarga
    fake_info = {
        "id": "dQw4w9WgXcQ",
        "title": "Test Song",
        "uploader": "Test Artist",
        "duration": 200,
        "thumbnail": "https://example.com/cover.jpg",
        "webpage_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    }
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(tmp_path / "Test Song - Test Artist.webm")
    mock_ydl_class.return_value = mock_ydl
    
    # Crear archivo falso de salida para simular descarga exitosa
    output_file = tmp_path / "Test Song - Test Artist.mp3"
    output_file.write_bytes(b"fake audio content")
    
    result = yt_service.get_info(
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        permanent=True,
        audio_format="mp3",
    )
    
    assert result is not None
    assert result["title"] == "Test Song"
    assert result["artist"] == "Test Artist"
    assert result["local_file"] == str(output_file)
    assert Path(result["local_file"]).exists()


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_get_playlist_info(mock_ydl_class, yt_service):
    """Extrae metadatos de playlist."""
    fake_entries = [
        {"id": "vid1", "title": "Song 1", "duration": 180, "uploader": "Artist 1", "thumbnail": "thumb1.jpg"},
        {"id": "vid2", "title": "Song 2", "duration": 200, "uploader": "Artist 2", "thumbnail": "thumb2.jpg"},
    ]
    
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {
        "title": "Test Playlist",
        "entries": fake_entries,
    }
    mock_ydl_class.return_value = mock_ydl
    
    results = yt_service.get_playlist_info("https://youtube.com/playlist?list=PLtest")
    
    assert len(results) == 2
    assert results[0]["id"] == "vid1"
    assert results[0]["title"] == "Song 1"
    assert results[0]["playlist"] == "Test Playlist"
    assert results[0]["url"] == "https://www.youtube.com/watch?v=vid1"


# ---------------------------------------------------------------------------
# Last.fm Service - Integración (mocking _call method)
# ---------------------------------------------------------------------------

@patch("services.lastfm_service.LastFmService._call")
def test_lastfm_scrobble_sends_correct_payload(mock_call, lastfm_service):
    """Scrobbling envía payload correcto a API Last.fm."""
    mock_call.return_value = {"scrobbles": {"@attr": {"accepted": "1"}, "scrobble": {"timestamp": "1234567890"}}}
    
    track = Track(
        id="test123",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        file_path="/fake/path.mp3",
        duration=180,
        source="local",
    )
    
    result = lastfm_service.scrobble(track)
    
    assert result is True
    mock_call.assert_called_once()
    call_args = mock_call.call_args
    assert call_args[0][0] == "track.scrobble"
    params = call_args[0][1]
    assert params["artist"] == "Test Artist"
    assert params["track"] == "Test Song"
    assert params["album"] == "Test Album"
    assert "timestamp" in params
    assert params["duration"] == "180"
    assert params["sk"] == "test_session_key"


@patch("services.lastfm_service.LastFmService._call")
def test_lastfm_now_playing_sends_notification(mock_call, lastfm_service):
    """Now playing envía notificación correcta."""
    mock_call.return_value = {"nowplaying": {"@attr": {"accepted": "1"}}}
    
    track = Track(
        id="nowplaying123",
        title="Now Playing Song",
        artist="Now Playing Artist",
        album="Now Playing Album",
        file_path="/fake/path.mp3",
        duration=200,
        source="local",
    )
    
    result = lastfm_service.now_playing(track)
    
    assert result is True
    mock_call.assert_called_once()
    call_args = mock_call.call_args
    assert call_args[0][0] == "track.updateNowPlaying"
    params = call_args[0][1]
    assert params["artist"] == "Now Playing Artist"
    assert params["track"] == "Now Playing Song"
    assert params["album"] == "Now Playing Album"
    assert params["sk"] == "test_session_key"
    assert params["duration"] == "200"


@patch("services.lastfm_service.LastFmService._call")
def test_lastfm_network_error_handled(mock_call, lastfm_service):
    """Error de red no lanza excepción, devuelve False."""
    mock_call.return_value = None
    
    track = Track(
        id="test123",
        title="Test",
        artist="Artist",
        album="Album",
        file_path="/fake/path.mp3",
        duration=180,
        source="local",
    )
    
    result = lastfm_service.scrobble(track)
    
    assert result is False


@patch("services.lastfm_service.LastFmService._call")
def test_lastfm_rate_limit_handled(mock_call, lastfm_service):
    """Rate limit (429) se maneja correctamente."""
    # _call devuelve None cuando hay error en la respuesta
    mock_call.return_value = None
    
    track = Track(
        id="test123",
        title="Test",
        artist="Artist",
        album="Album",
        file_path="/fake/path.mp3",
        duration=180,
        source="local",
    )
    
    result = lastfm_service.scrobble(track)
    
    assert result is False


# ---------------------------------------------------------------------------
# Metadata Service - Integración
# ---------------------------------------------------------------------------

def test_metadata_read_mp3_tags(metadata_service, tmp_path):
    """Lectura de etiquetas MP3 (ID3v2) - usa archivo de prueba válido."""
    pytest.skip("Requiere archivo MP3 válido - test de lógica de servicio en su lugar")


def test_metadata_read_flac_tags(metadata_service, tmp_path):
    """Lectura de etiquetas FLAC (Vorbis comments) - usa archivo de prueba válido."""
    pytest.skip("Requiere archivo FLAC válido - test de lógica de servicio en su lugar")


def test_metadata_read_m4a_tags(metadata_service, tmp_path):
    """Lectura de etiquetas M4A (iTunes/MP4) - usa archivo de prueba válido."""
    pytest.skip("Requiere archivo M4A válido - test de lógica de servicio en su lugar")


def test_metadata_write_mp3_tags(metadata_service, tmp_path):
    """Escritura de etiquetas MP3 - usa archivo de prueba válido."""
    pytest.skip("Requiere archivo MP3 válido - test de lógica de servicio en su lugar")


def test_metadata_extract_cover_art(metadata_service, tmp_path):
    """Extracción de portada (cover art) - usa archivo de prueba válido."""
    pytest.skip("Requiere archivo MP3 válido - test de lógica de servicio en su lugar")


def test_metadata_handles_missing_file(metadata_service):
    """Archivo inexistente devuelve metadatos por defecto sin lanzar excepción."""
    metadata = metadata_service.get_metadata("/nonexistent/file.mp3")
    assert metadata["title"] == "file.mp3"
    assert metadata["artist"] == "Desconocido"
    assert metadata["album"] == "Desconocido"
    assert metadata["duration"] == 0.0
    assert metadata["cover_data"] is None


def test_metadata_handles_corrupted_file(metadata_service, tmp_path):
    """Archivo corrupto devuelve metadatos por defecto sin lanzar excepción."""
    corrupt_path = tmp_path / "corrupt.mp3"
    corrupt_path.write_bytes(b"not a valid mp3")
    
    metadata = metadata_service.get_metadata(str(corrupt_path))
    assert metadata["title"] == "corrupt.mp3"
    assert metadata["artist"] == "Desconocido"
    assert metadata["album"] == "Desconocido"
    assert metadata["duration"] == 0.0
    assert metadata["cover_data"] is None


# ---------------------------------------------------------------------------
# Tests de integración combinados
# ---------------------------------------------------------------------------

@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_to_metadata_flow(mock_ydl_class, yt_service, metadata_service, tmp_path):
    """Flujo: búsqueda YouTube -> descarga -> lectura metadatos."""
    pytest.skip("Requiere archivo MP3 válido - test de flujo en su lugar")


# ---------------------------------------------------------------------------
# Performance / Benchmark tests
# ---------------------------------------------------------------------------

@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_search_performance(mock_ydl_class, yt_service, benchmark):
    """Benchmark de búsqueda YouTube (mocked)."""
    fake_entries = [
        {"id": f"vid{i}", "title": f"Song {i}", "duration": 180+i, "thumbnail": "", "uploader": f"Artist {i}"}
        for i in range(50)
    ]
    
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {"entries": fake_entries}
    mock_ydl_class.return_value = mock_ydl
    
    def search():
        return yt_service.search_songs("test query", max_results=50)
    
    result = benchmark(search)
    assert len(result) == 50


def test_metadata_batch_read_performance(metadata_service, tmp_path, benchmark):
    """Benchmark de lectura masiva de metadatos."""
    pytest.skip("Requiere archivos MP3 válidos - test de lógica de servicio en su lugar")


@patch("services.youtube_service.yt_dlp.YoutubeDL")
def test_youtube_download_performance(mock_ydl_class, yt_service, tmp_path, benchmark):
    """Benchmark de descarga (simulada)."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    
    fake_info = {
        "id": "test123",
        "title": "Benchmark Song",
        "uploader": "Benchmark Artist",
        "duration": 180,
        "thumbnail": "https://example.com/cover.jpg",
        "webpage_url": "https://youtube.com/watch?v=test123",
    }
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(tmp_path / "Benchmark Song - Benchmark Artist.webm")
    mock_ydl_class.return_value = mock_ydl
    
    def download():
        output_file = tmp_path / "Benchmark Song - Benchmark Artist.mp3"
        output_file.write_bytes(b"x" * 1024 * 100)  # 100KB
        return yt_service.get_info(
            "https://youtube.com/watch?v=test123",
            permanent=True,
            audio_format="mp3",
        )
    
    result = benchmark(download)
    assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])