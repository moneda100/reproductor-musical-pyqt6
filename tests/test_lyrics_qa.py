"""Pruebas QA para letras (lyrics): distinción YouTube vs local,
letras incrustadas en archivos locales, y estados del panel."""

from __future__ import annotations

from unittest.mock import patch

from core.lyrics import LyricLine, LyricsService, active_line_index, parse_lrc


# ======================================================================
# Letras: parseo y activo
# ======================================================================
def test_parse_lrc_handles_mixed_timestamps():
    """Parsea LRC con diferentes formatos de marca de tiempo."""
    content = "[00:12]Primera\n[00:15.5]Segunda\n[1:05.25]Tercera"
    lines = parse_lrc(content)
    assert len(lines) == 3
    assert lines[0].timestamp_ms == 12000
    assert lines[1].timestamp_ms == 15500
    assert lines[2].timestamp_ms == 65250


def test_active_line_index_edge_cases():
    """Índice de línea activa: casos borde."""
    lines = [
        LyricLine(0, "a"),
        LyricLine(5000, "b"),
        LyricLine(10000, "c"),
    ]
    assert active_line_index(lines, -1) == -1
    assert active_line_index(lines, 0) == 0
    assert active_line_index(lines, 4999) == 0
    assert active_line_index(lines, 5000) == 1
    assert active_line_index(lines, 9999) == 1
    assert active_line_index(lines, 10000) == 2
    assert active_line_index([], 100) == -1


# ======================================================================
# Letras: distinción YouTube vs local
# ======================================================================
def test_lyrics_service_constructor():
    """LyricsService se construye sin errores."""
    service = LyricsService()
    assert service.cache_dir is not None
    assert service.cache_dir.exists()


@patch("services.metadata_service.MetadataService.get_metadata")
def test_read_embedded_lyrics_mp3(mock_get_metadata, tmp_path):
    """Lee letras incrustadas USLT de un archivo MP3 local."""
    mock_get_metadata.return_value = {
        "title": "Canción",
        "artist": "Artista",
        "lyrics": "Letra incrustada\nLínea 2",
    }
    service = LyricsService(cache_dir=tmp_path / "lyrics")
    result = service.read_embedded_lyrics("/music/cancion.mp3")
    assert result == "Letra incrustada\nLínea 2"


@patch("services.metadata_service.MetadataService.get_metadata")
def test_read_embedded_lyrics_returns_none_when_empty(mock_get_metadata, tmp_path):
    """Devuelve None si no hay letras incrustadas."""
    mock_get_metadata.return_value = {"lyrics": ""}
    service = LyricsService(cache_dir=tmp_path / "lyrics")
    result = service.read_embedded_lyrics("/music/cancion.mp3")
    assert result is None


@patch("services.metadata_service.MetadataService.get_metadata")
def test_read_embedded_lyrics_handles_error(mock_get_metadata, tmp_path):
    """No falla si el archivo no se puede leer."""
    mock_get_metadata.side_effect = OSError("archivo corrupto")
    service = LyricsService(cache_dir=tmp_path / "lyrics")
    result = service.read_embedded_lyrics("/music/corrupto.mp3")
    assert result is None


def test_fetch_lyrics_passes_is_youtube_and_video_id():
    """fetch_lyrics acepta y pasa is_youtube y video_id sin lanzar excepción."""
    service = LyricsService()
    # Verifica que no lanza excepción con parámetros de YouTube.
    # La red puede o no tener letras, lo importante es que no falla.
    result = service.fetch_lyrics(
        "Test Song", "Test Artist", is_youtube=True, video_id="dQw4w9WgXcQ"
    )
    if result is not None:
        assert "synced" in result
        assert "plain" in result


def test_get_lyrics_local_tries_embedded_first(tmp_path):
    """Para pistas locales, get_lyrics intenta letras incrustadas antes que online."""
    service = LyricsService(cache_dir=tmp_path / "lyrics")

    with patch.object(service, "read_embedded_lyrics", return_value="Letra incrustada"):
        payload = service.get_lyrics(
            track_key="local:test",
            title="Canción",
            artist="Artista",
            is_youtube=False,
            file_path="/music/cancion.mp3",
        )
    assert payload is not None
    assert payload["plain"] == "Letra incrustada"
    assert len(payload["synced"]) == 1  # una línea sin timestamp


def test_get_lyrics_youtube_skips_embedded(tmp_path):
    """Para pistas de YouTube, get_lyrics NO intenta letras incrustadas."""
    service = LyricsService(cache_dir=tmp_path / "lyrics")

    with patch.object(service, "read_embedded_lyrics") as mock_embedded:
        payload = service.get_lyrics(
            track_key="yt:dQw4w9WgXcQ",
            title="Canción",
            artist="Artista",
            is_youtube=True,
            video_id="dQw4w9WgXcQ",
            file_path="/nonexistent.mp4",
        )
    # read_embedded_lyrics no debería haberse llamado para YouTube
    mock_embedded.assert_not_called()
    # Sin red, no hay letras online
    assert payload is None


def test_get_lyrics_cache_hit(tmp_path):
    """El caché devuelve la letra guardada sin llamar a la red."""
    service = LyricsService(cache_dir=tmp_path / "lyrics")

    # Escribir directamente en caché
    service.write_cache(
        "local:cache_test",
        {
            "synced": [{"timestamp_ms": 0, "text": "Letra cacheada"}],
            "plain": "Letra cacheada",
        },
    )

    with patch.object(service, "fetch_lyrics") as mock_fetch:
        payload = service.get_lyrics(
            track_key="local:cache_test",
            title="Canción",
            artist="Artista",
            is_youtube=False,
        )
    mock_fetch.assert_not_called()
    assert payload is not None
    assert payload["plain"] == "Letra cacheada"


# ======================================================================
# Letras: panel UI estados
# ======================================================================
def test_lyrics_panel_set_no_lyrics(qtbot):
    """set_no_lyrics muestra mensaje informativo."""
    panel = __import__("ui.panels.lyrics_panel", fromlist=["LyricsPanel"]).LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_no_lyrics()
    text = panel.text_browser.toPlainText()
    assert "No se encontraron letras" in text
    assert panel._lines == []
    assert panel._active_index == -1


def test_lyrics_panel_set_loading(qtbot):
    """set_loading muestra mensaje de carga."""
    panel = __import__("ui.panels.lyrics_panel", fromlist=["LyricsPanel"]).LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_loading(True)
    assert panel._loading is True
    assert "Buscando letras" in panel.text_browser.toPlainText()
    panel.set_loading(False)
    assert panel._loading is False


def test_lyrics_panel_set_lyrics_after_no_lyrics(qtbot):
    """Después de set_no_lyrics, set_lyrics carga la letra correctamente."""
    panel = __import__("ui.panels.lyrics_panel", fromlist=["LyricsPanel"]).LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_no_lyrics()
    lines = [LyricLine(timestamp_ms=0, text="Nueva letra")]
    panel.set_lyrics(lines)
    assert panel._lines == [lines[0]]
    assert "Nueva letra" in panel.text_browser.toPlainText()


def test_lyrics_panel_clear_resets_loading(qtbot):
    """clear() resetea el estado de carga."""
    panel = __import__("ui.panels.lyrics_panel", fromlist=["LyricsPanel"]).LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_loading(True)
    panel.clear()
    assert panel._loading is False
