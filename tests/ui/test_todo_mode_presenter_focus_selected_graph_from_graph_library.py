from __future__ import annotations

from app.models.view_modes import ViewMode
from app.ui.main_window.mode_presenters.presenters import TodoModePresenter
from app.ui.main_window.mode_presenters.requests import ModeEnterRequest
from app.ui.main_window.todo_events_mixin import _PendingTodoFocusRequest


class _FakePropertyPanel:
    def __init__(self) -> None:
        self.clear_called: int = 0

    def clear(self) -> None:
        self.clear_called += 1


class _FakeGraphLibraryWidget:
    def __init__(self, graph_id: str) -> None:
        self._graph_id = str(graph_id or "")

    def get_selected_graph_id(self) -> str:
        return self._graph_id


class _FakeMainWindow:
    def __init__(self, graph_id: str) -> None:
        self.property_panel = _FakePropertyPanel()
        self.graph_library_widget = _FakeGraphLibraryWidget(graph_id)
        self.refresh_called: int = 0

    def _refresh_todo_list(self) -> None:
        self.refresh_called += 1


def test_todo_mode_presenter_sets_pending_focus_when_entering_from_graph_library() -> None:
    main_window = _FakeMainWindow("graph_test_001")
    presenter = TodoModePresenter()

    presenter.enter(
        main_window,
        request=ModeEnterRequest(view_mode=ViewMode.TODO, previous_mode=ViewMode.GRAPH_LIBRARY),
    )

    pending = getattr(main_window, "_pending_todo_focus_request", None)
    assert isinstance(pending, _PendingTodoFocusRequest)
    assert pending.todo_id == ""
    assert pending.detail_info is None
    assert pending.graph_id == "graph_test_001"
    assert main_window.refresh_called == 1
    assert main_window.property_panel.clear_called == 1


def test_todo_mode_presenter_does_not_set_pending_focus_when_graph_id_empty() -> None:
    main_window = _FakeMainWindow("")
    presenter = TodoModePresenter()

    presenter.enter(
        main_window,
        request=ModeEnterRequest(view_mode=ViewMode.TODO, previous_mode=ViewMode.GRAPH_LIBRARY),
    )

    assert not hasattr(main_window, "_pending_todo_focus_request")

