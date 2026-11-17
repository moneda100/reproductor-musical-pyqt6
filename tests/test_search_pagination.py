"""Paginación de búsquedas de YouTube y crecimiento del modelo de resultados."""

from __future__ import annotations

from core.tasks.youtube_tasks import YouTubeSearchTask
from ui.models.results_model import ResultsModel


class FakeSearchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def search_songs(self, query: str, max_results: int = 20, offset: int = 0) -> list[dict]:
        self.calls.append((query, max_results, offset))
        return [{"id": f"v{offset}", "title": query}]


def test_search_task_forwards_offset() -> None:
    service = FakeSearchService()
    task = YouTubeSearchTask(service, "cafe", max_results=20, offset=40)

    results = task()

    assert service.calls == [("cafe", 20, 40)]
    assert results[0]["id"] == "v40"


def test_search_task_supports_legacy_service_without_offset() -> None:
    class LegacyService:
        def search_songs(self, query: str, max_results: int = 20) -> list[dict]:
            return [{"id": "legacy", "title": query}]

    task = YouTubeSearchTask(LegacyService(), "rock", max_results=10, offset=10)

    assert task()[0]["id"] == "legacy"


def test_results_model_append_preserves_existing_rows() -> None:
    model = ResultsModel()
    model.set_results([{"id": "a"}, {"id": "b"}])

    added = model.append_results([{"id": "c"}, {"id": "d"}])

    assert added == 2
    assert model.rowCount() == 4
    assert [row["id"] for row in model.results()] == ["a", "b", "c", "d"]


def test_results_model_append_empty_is_noop() -> None:
    model = ResultsModel()
    model.set_results([{"id": "a"}])

    assert model.append_results([]) == 0
    assert model.rowCount() == 1
