from __future__ import annotations

from types import SimpleNamespace

from app.models.view_modes import ViewMode
from app.ui.main_window.package_events.packages_view_mixin import PackagesViewMixin
from app.ui.main_window.right_panel_contracts import CONTRACT_SHOW_GRAPH_PROPERTY


class _CentralStackStub:
    def __init__(self, index: int) -> None:
        self._index = index

    def currentIndex(self) -> int:  # noqa: D401 - Qt API shape
        return self._index


class _GraphPropertyPanelStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def set_graph(self, graph_id: str) -> None:
        self.calls.append(("set_graph", graph_id))

    def set_graph_preview(self, graph_id: str, **kwargs: object) -> None:
        self.calls.append(("set_graph_preview", {"graph_id": graph_id, **kwargs}))


class _RightPanelStub:
    def __init__(self) -> None:
        self.contracts: list[object] = []

    def apply_visibility_contract(self, contract: object) -> None:
        self.contracts.append(contract)


class _MainStub(PackagesViewMixin):
    def __init__(
        self,
        *,
        selected_package_id: str,
        current_package_id: str,
    ) -> None:
        self.central_stack = _CentralStackStub(ViewMode.PACKAGES.value)
        self.graph_property_panel = _GraphPropertyPanelStub()
        self.right_panel = _RightPanelStub()
        self.package_controller = SimpleNamespace(current_package_id=current_package_id)
        self.package_library_widget = SimpleNamespace(_current_package_id=selected_package_id)


def test_packages_view_graph_click_other_package_uses_preview_mode() -> None:
    main = _MainStub(selected_package_id="pkg_b", current_package_id="pkg_a")
    main._on_package_resource_activated("graph", "server_graph_1__pkg_b")

    assert main.graph_property_panel.calls
    assert main.graph_property_panel.calls[0][0] == "set_graph_preview"
    assert main.right_panel.contracts == [CONTRACT_SHOW_GRAPH_PROPERTY]


def test_packages_view_graph_click_current_package_loads_full() -> None:
    main = _MainStub(selected_package_id="pkg_a", current_package_id="pkg_a")
    main._on_package_resource_activated("graph", "server_graph_1__pkg_a")

    assert main.graph_property_panel.calls
    assert main.graph_property_panel.calls[0][0] == "set_graph"
    assert main.right_panel.contracts == [CONTRACT_SHOW_GRAPH_PROPERTY]


def test_packages_view_graph_click_global_view_loads_full() -> None:
    main = _MainStub(selected_package_id="global_view", current_package_id="pkg_a")
    main._on_package_resource_activated("graph", "shared_graph_1")

    assert main.graph_property_panel.calls
    assert main.graph_property_panel.calls[0][0] == "set_graph"
    assert main.right_panel.contracts == [CONTRACT_SHOW_GRAPH_PROPERTY]


