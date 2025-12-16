"""主窗口的 ViewState（单一真源雏形）。

目的：
- 把“当前模式 + 关键选中上下文”集中到一个明确对象里，减少 Mixin/Widget 间的隐式依赖；
- 逐步让 mode presenter 只依赖 view_state，而不是到处从 widget 读取临时状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.view_modes import ViewMode


@dataclass(slots=True)
class CombatSelectionState:
    """战斗预设的选中状态（含跨模式缓存）。"""

    pending_section_key: str = ""
    pending_item_id: str = ""
    current_section_key: str = ""
    current_item_id: str = ""


@dataclass(slots=True)
class ManagementSelectionState:
    """管理面板当前选中的 section 与条目。"""

    section_key: str = ""
    item_id: str = ""


@dataclass(slots=True)
class TemplateSelectionState:
    """元件库当前选中。"""

    template_id: str = ""


@dataclass(slots=True)
class PlacementSelectionState:
    """实体摆放当前选中。"""

    instance_id: str = ""
    has_level_entity_selected: bool = False


@dataclass(slots=True)
class TodoSelectionState:
    """任务清单当前选中。"""

    todo_id: str = ""
    task_type: str = ""
    detail_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphSelectionState:
    """节点图库/编辑器相关选中与上下文。"""

    graph_library_selected_graph_id: str = ""
    graph_editor_open_graph_id: str = ""


@dataclass(slots=True)
class MainWindowViewState:
    """主窗口 ViewState：当前模式 + 各页面关键选中上下文。"""

    current_view_mode: ViewMode = ViewMode.TEMPLATE
    previous_view_mode: ViewMode = ViewMode.TEMPLATE

    template: TemplateSelectionState = field(default_factory=TemplateSelectionState)
    placement: PlacementSelectionState = field(default_factory=PlacementSelectionState)
    combat: CombatSelectionState = field(default_factory=CombatSelectionState)
    management: ManagementSelectionState = field(default_factory=ManagementSelectionState)
    todo: TodoSelectionState = field(default_factory=TodoSelectionState)
    graph: GraphSelectionState = field(default_factory=GraphSelectionState)

    def set_mode(self, *, current: ViewMode, previous: ViewMode) -> None:
        self.current_view_mode = current
        self.previous_view_mode = previous

    def clear_template_selection(self) -> None:
        self.template.template_id = ""

    def clear_placement_selection(self) -> None:
        self.placement.instance_id = ""
        self.placement.has_level_entity_selected = False

    def clear_management_selection(self) -> None:
        self.management.section_key = ""
        self.management.item_id = ""

    def clear_combat_selection(self) -> None:
        self.combat.current_section_key = ""
        self.combat.current_item_id = ""

    def clear_todo_selection(self) -> None:
        self.todo.todo_id = ""
        self.todo.task_type = ""
        self.todo.detail_info = {}

    def clear_graph_library_selection(self) -> None:
        self.graph.graph_library_selected_graph_id = ""


