from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.view_modes import ViewMode
from app.ui.main_window.package_events.management_panels_coordinator import (
    ManagementPanelsCoordinator,
)


@dataclass(frozen=True, slots=True)
class _DummyLibrarySelection:
    kind: str
    id: str
    context: dict[str, Any]


class _SelectionReadOnceManagementWidget:
    """一个用于回归测试的管理库 stub。

    约束：`get_selection()` 只能被调用一次。
    这用于捕捉“selection 解析被重复执行”的不统一问题：
    - 第一次调用由 coordinator 解析 selection；
    - 若专用面板 updater 再次反查 selection，就会触发第二次调用并失败。
    """

    def __init__(self, selection: _DummyLibrarySelection) -> None:
        self._selection = selection
        self.get_selection_call_count: int = 0

    def get_selection(self) -> _DummyLibrarySelection:
        self.get_selection_call_count += 1
        if self.get_selection_call_count > 1:
            raise AssertionError(
                "management_widget.get_selection() 被调用超过 1 次："
                "说明管理模式 selection 解析没有做到“单一入口、单次解析”"
            )
        return self._selection


class _CentralStackStub:
    def currentIndex(self) -> int:
        return ViewMode.MANAGEMENT.value


class _RightPanelStub:
    def __init__(self) -> None:
        self.apply_calls: list[tuple[str | None, bool]] = []
        self.tab_visibility_calls: list[tuple[str, bool, bool]] = []

    def apply_management_selection(self, section_key: str | None, *, has_selection: bool) -> None:
        self.apply_calls.append((section_key, bool(has_selection)))

    def set_tab_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None:
        self.tab_visibility_calls.append((tab_id, bool(visible), bool(switch_to)))

    def update_visibility(self) -> None:
        return


class _StructEditorStub:
    def __init__(self) -> None:
        self.loaded_struct_name: str | None = None
        self.loaded_fields: list[dict[str, object]] | None = None
        self.loaded_allow_edit_name: bool | None = None
        self.is_read_only: bool | None = None

    def load_struct(self, *, struct_name: str, fields: Any, allow_edit_name: bool) -> None:
        self.loaded_struct_name = str(struct_name)
        self.loaded_fields = list(fields) if fields is not None else []
        self.loaded_allow_edit_name = bool(allow_edit_name)

    def set_read_only(self, is_read_only: bool) -> None:
        self.is_read_only = bool(is_read_only)

    def build_struct_data(self) -> dict[str, object]:
        return {"name": self.loaded_struct_name or "", "value": []}


class _StructDefinitionPanelStub:
    def __init__(self) -> None:
        self.editor = _StructEditorStub()
        self.current_struct_id: str | None = None
        self.field_count: int | None = None
        self.title: str | None = None
        self.description: str | None = None

    def reset(self) -> None:
        self.current_struct_id = None

    def set_field_count(self, count: int) -> None:
        self.field_count = int(count)

    def set_title(self, title: str) -> None:
        self.title = str(title)

    def set_description(self, description: str) -> None:
        self.description = str(description)

    def set_current_struct_id(self, struct_id: str | None) -> None:
        self.current_struct_id = struct_id if isinstance(struct_id, str) else None

    def set_packages_and_membership(self, packages: list[dict], membership: set[str]) -> None:
        _ = packages
        _ = membership


class _PackageIndexManagerStub:
    def list_packages(self) -> list[dict]:
        return []

    def get_resource_owner_root_id(self, *, resource_type: str, resource_id: str) -> str:
        _ = resource_type
        _ = resource_id
        return ""


class _AppStateStub:
    def __init__(self) -> None:
        self.package_index_manager = _PackageIndexManagerStub()


class _PackageControllerStub:
    def __init__(self, current_package: object) -> None:
        self.current_package = current_package


class _ManagementSelectionStateStub:
    def __init__(self) -> None:
        self.section_key: str = ""
        self.item_id: str = ""


class _ViewStateStub:
    def __init__(self) -> None:
        self.management = _ManagementSelectionStateStub()


def test_management_special_panel_selection_is_parsed_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """回归：管理模式专用面板刷新不应二次反查 management_widget.get_selection()."""

    # 让 struct 面板 updater 所需的两个依赖变成轻量可控：
    # - ResourceManager 类型检查：改为使用 dummy class
    # - get_struct_payload：返回一个最小 payload
    class _DummyResourceManager:
        pass

    import engine.resources.resource_manager as resource_manager_module

    monkeypatch.setattr(resource_manager_module, "ResourceManager", _DummyResourceManager)

    import engine.configs.specialized.struct_definitions_data as struct_definitions_data_module

    monkeypatch.setattr(
        struct_definitions_data_module,
        "get_struct_payload",
        lambda struct_id, _resource_manager=None: {
            "type": "结构体",
            "struct_ype": "ingame_save",
            "name": f"测试结构体_{struct_id}",
            "value": [{"key": "字段A", "param_type": "整数"}],
        },
    )

    selection = _DummyLibrarySelection(
        kind="management",
        id="测试_结构体ID",
        context={"section_key": "ingame_struct_definitions"},
    )
    management_widget = _SelectionReadOnceManagementWidget(selection)

    # 只需要满足 struct 专用面板 updater 的最小主窗口契约
    dummy_package = SimpleNamespace(resource_manager=_DummyResourceManager())

    main_window = SimpleNamespace(
        central_stack=_CentralStackStub(),
        management_widget=management_widget,
        right_panel=_RightPanelStub(),
        view_state=_ViewStateStub(),
        package_controller=_PackageControllerStub(dummy_package),
        struct_definition_panel=_StructDefinitionPanelStub(),
        app_state=_AppStateStub(),
        _build_struct_membership_index=lambda: {},
        _on_immediate_persist_requested=lambda **kwargs: None,
        _on_library_selection_state_changed=lambda has_selection, context: None,
        _get_management_packages_and_membership=lambda binding_key, item_id: ([], set()),
        _get_packages_and_membership_for_level_variable_group=lambda group_id: ([], set(), []),
    )

    coordinator = ManagementPanelsCoordinator()
    coordinator.on_management_selection_changed(
        main_window,
        has_selection=True,
        title="结构体",
        description="desc",
        rows=[],
    )

    assert management_widget.get_selection_call_count == 1


