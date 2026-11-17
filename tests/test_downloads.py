"""Pruebas del gestor de descargas (tamaños, panel y tarea por lotes)."""

from __future__ import annotations

from PyQt6.QtCore import Qt

from core.tasks.youtube_tasks import YouTubeBatchDownloadTask
from services.youtube_service import estimate_audio_size
from ui.panels.downloads_panel import DownloadsPanel, format_size


def _item(index: int, duration: float = 60.0) -> dict:
    return {
        "id": f"vid{index}",
        "title": f"Canción {index}",
        "artist": "Artista",
        "url": f"https://www.youtube.com/watch?v=vid{index}",
        "duration": duration,
        "source": "youtube",
    }


def test_format_size_units():
    assert format_size(0) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"


def test_estimate_audio_size_depends_on_format_and_duration():
    mp3 = estimate_audio_size(60, "mp3")
    flac = estimate_audio_size(60, "flac")
    assert mp3 > 0
    assert flac > mp3
    assert estimate_audio_size(0, "mp3") == 0


def test_panel_playlist_mode_selects_everything(qtbot):
    panel = DownloadsPanel(destination="C:/descargas")
    qtbot.addWidget(panel)
    panel.set_items([_item(0), _item(1)], mode="playlist")

    assert len(panel.selected_items()) == 2
    assert "2 pista(s)" in panel.selected_label.text()


def test_panel_individual_mode_uses_checkboxes(qtbot):
    panel = DownloadsPanel(destination="C:/descargas")
    qtbot.addWidget(panel)
    panel.set_items([_item(0), _item(1)], mode="individual", selected_urls=[_item(0)["url"]])

    assert [item["id"] for item in panel.selected_items()] == ["vid0"]

    panel.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert len(panel.selected_items()) == 2


def test_panel_start_requires_destination_and_selection(qtbot):
    panel = DownloadsPanel(destination="")
    qtbot.addWidget(panel)
    messages: list[str] = []
    panel.validation_failed.connect(messages.append)

    assert panel.start() is False
    assert messages

    panel.set_destination("C:/descargas")
    panel.set_items([_item(0)], mode="individual", selected_urls=[])
    assert panel.start() is False
    assert len(messages) >= 2


def test_panel_start_emits_selected_items(qtbot):
    panel = DownloadsPanel(destination="C:/descargas")
    qtbot.addWidget(panel)
    panel.set_items([_item(0), _item(1)], mode="individual", selected_urls=[_item(1)["url"]])

    with qtbot.waitSignal(panel.start_requested, timeout=1000) as blocker:
        assert panel.start() is True
    assert [item["id"] for item in blocker.args[0]] == ["vid1"]


def test_panel_maps_batch_indices_to_selected_rows(qtbot):
    panel = DownloadsPanel(destination="C:/descargas")
    qtbot.addWidget(panel)
    panel.set_items(
        [_item(0), _item(1), _item(2)],
        mode="individual",
        selected_urls=[_item(1)["url"], _item(2)["url"]],
    )
    panel.mark_started(2)
    panel.update_item_progress(0, {"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})

    # El índice 0 del lote corresponde a la fila 1, no a la 0.
    assert "Descargando" in panel.table.item(1, 3).text()
    assert panel.table.item(0, 3).text() == "Pendiente"


def test_batch_task_reports_per_item_progress(tmp_path):
    file_path = tmp_path / "audio.mp3"
    file_path.write_bytes(b"audio")

    class FakeService:
        def get_info(
            self,
            url,
            permanent=False,
            audio_format="mp3",
            progress_hook=None,
            cancel_event=None,
        ):
            if progress_hook:
                progress_hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
                progress_hook({"status": "finished"})
            return {
                "id": "vid",
                "title": "Canción",
                "artist": "Artista",
                "duration": 10,
                "local_file": str(file_path),
            }

    progress: list[tuple[int, dict]] = []
    finished: list[tuple[int, object]] = []
    task = YouTubeBatchDownloadTask(
        FakeService(),
        [_item(0)],
        permanent=True,
        audio_format="flac",
        on_item_progress=lambda index, data: progress.append((index, data)),
        on_item_finished=lambda index, track: finished.append((index, track)),
    )

    tracks = task()

    assert len(tracks) == 1
    assert [data["status"] for _, data in progress] == ["downloading", "finished"]
    assert finished[0][0] == 0
    assert finished[0][1].file_path == str(file_path)
