"""Mode Presenter coordinator：按 ViewMode 分派进入模式副作用。"""

from __future__ import annotations

from app.models.view_modes import ViewMode

from .requests import ModeEnterRequest
from .presenters import (
    CombatModePresenter,
    CompositeModePresenter,
    GraphEditorModePresenter,
    GraphLibraryModePresenter,
    ManagementModePresenter,
    PackagesModePresenter,
    PlacementModePresenter,
    TemplateModePresenter,
    TodoModePresenter,
    ValidationModePresenter,
)


class ModePresenterCoordinator:
    """持有所有 presenter，并提供统一的 enter_mode 分派入口。"""

    def __init__(self, main_window: object) -> None:
        self._main_window = main_window
        self._presenters = {
            ViewMode.GRAPH_LIBRARY: GraphLibraryModePresenter(),
            ViewMode.COMPOSITE: CompositeModePresenter(),
            ViewMode.GRAPH_EDITOR: GraphEditorModePresenter(),
            ViewMode.VALIDATION: ValidationModePresenter(),
            ViewMode.PACKAGES: PackagesModePresenter(),
            ViewMode.MANAGEMENT: ManagementModePresenter(),
            ViewMode.TODO: TodoModePresenter(),
            ViewMode.TEMPLATE: TemplateModePresenter(),
            ViewMode.PLACEMENT: PlacementModePresenter(),
            ViewMode.COMBAT: CombatModePresenter(),
        }

    def enter_mode(self, request: ModeEnterRequest) -> str | None:
        presenter = self._presenters.get(request.view_mode)
        if presenter is None:
            return None
        return presenter.enter(self._main_window, request=request)


