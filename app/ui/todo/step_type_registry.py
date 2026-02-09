from __future__ import annotations

"""StepType 元数据注册表（单一真源）。

目标：
- 将 graph/composite 等“步骤类型”的能力画像收敛为一份 StepTypeSpec；
- 由本注册表派生出 StepTypeRules/TodoStyles/图标/配色等所需集合，避免散点维护；
- 新增一个步骤类型时，原则上只需在本文件补一条 spec。
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from app.ui.foundation.theme_manager import Colors as ThemeColors


@dataclass(frozen=True, slots=True)
class StepTypeSpec:
    """步骤类型能力画像（面向 Todo UI）。

    说明：
    - 这里只承载 UI 所需的语义与样式元数据；不包含任何运行时对象引用；
    - icon/color 允许为空字符串，表示使用 UI 侧默认回退策略。
    """

    detail_type: str
    supports_preview: bool = True
    supports_auto_check: bool = False
    supports_rich_tokens: bool = False
    supports_context_menu_execution: bool = False

    is_config_step: bool = False
    is_type_setting_step: bool = False
    has_virtual_detail_children: bool = False

    # UI metadata (optional)
    icon: str = ""
    color: str = ""


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(v or "") for v in values if str(v or "")})


def _build_spec_map(specs: Iterable[StepTypeSpec]) -> Dict[str, StepTypeSpec]:
    result: Dict[str, StepTypeSpec] = {}
    for spec in specs:
        normalized = str(spec.detail_type or "")
        if not normalized:
            raise RuntimeError("StepTypeSpec.detail_type 不能为空")
        if normalized in result:
            raise RuntimeError(f"重复注册 StepTypeSpec: {normalized}")
        result[normalized] = spec
    return result


_SPECS: tuple[StepTypeSpec, ...] = (
    # --- Graph roots
    StepTypeSpec(
        detail_type="template_graph_root",
        color=ThemeColors.TODO_STEP_TEMPLATE_GRAPH_ROOT,
    ),
    StepTypeSpec(
        detail_type="event_flow_root",
        color=ThemeColors.TODO_STEP_EVENT_FLOW_ROOT,
    ),
    # --- Graph leaf steps (create / connect / config)
    StepTypeSpec(
        detail_type="graph_create_node",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        icon="+",
        color=ThemeColors.TODO_STEP_GRAPH_CREATE_NODE,
    ),
    StepTypeSpec(
        detail_type="graph_create_and_connect",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        icon="─",
        color=ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT,
    ),
    StepTypeSpec(
        detail_type="graph_create_and_connect_reverse",
        supports_auto_check=True,
        supports_rich_tokens=True,
        icon="─",
        color=ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT_REVERSE,
    ),
    StepTypeSpec(
        detail_type="graph_create_and_connect_data",
        supports_auto_check=True,
        supports_rich_tokens=True,
        icon="─",
        color=ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT_DATA,
    ),
    StepTypeSpec(
        detail_type="graph_create_branch_node",
        supports_auto_check=True,
    ),
    StepTypeSpec(
        detail_type="graph_connect",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        has_virtual_detail_children=True,
        icon="─",
        color=ThemeColors.TODO_STEP_GRAPH_CONNECT,
    ),
    StepTypeSpec(
        detail_type="graph_connect_merged",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        has_virtual_detail_children=True,
        icon="─",
        color=ThemeColors.TODO_STEP_GRAPH_CONNECT_MERGED,
    ),
    StepTypeSpec(
        detail_type="graph_config_node",
        supports_auto_check=True,
        is_config_step=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_CONFIG_NODE,
    ),
    StepTypeSpec(
        detail_type="graph_config_node_merged",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        is_config_step=True,
        has_virtual_detail_children=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_CONFIG_NODE_MERGED,
    ),
    StepTypeSpec(
        detail_type="graph_set_port_types_merged",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        is_type_setting_step=True,
        has_virtual_detail_children=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_SET_PORT_TYPES_MERGED,
    ),
    # --- Dynamic ports / branch config
    StepTypeSpec(
        detail_type="graph_add_variadic_inputs",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        icon="+",
        color=ThemeColors.TODO_STEP_GRAPH_ADD_VARIADIC_INPUTS,
    ),
    StepTypeSpec(
        detail_type="graph_add_dict_pairs",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        icon="+",
        color=ThemeColors.TODO_STEP_GRAPH_ADD_DICT_PAIRS,
    ),
    StepTypeSpec(
        detail_type="graph_add_branch_outputs",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        icon="+",
        color=ThemeColors.TODO_STEP_GRAPH_ADD_BRANCH_OUTPUTS,
    ),
    StepTypeSpec(
        detail_type="graph_config_branch_outputs",
        supports_auto_check=True,
        supports_rich_tokens=True,
        supports_context_menu_execution=True,
        has_virtual_detail_children=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_CONFIG_BRANCH_OUTPUTS,
    ),
    # --- Signals / structs
    StepTypeSpec(
        detail_type="graph_signals_overview",
        supports_auto_check=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_SIGNALS_OVERVIEW,
    ),
    StepTypeSpec(
        detail_type="graph_bind_signal",
        supports_auto_check=True,
        supports_rich_tokens=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_BIND_SIGNAL,
    ),
    StepTypeSpec(
        detail_type="graph_bind_struct",
        supports_auto_check=True,
        icon="◦",
        color=ThemeColors.TODO_STEP_GRAPH_BIND_STRUCT,
    ),
    # --- Graph detail-only (no preview)
    StepTypeSpec(
        detail_type="graph_variables_table",
        supports_preview=False,
    ),
)


_SPECS_BY_TYPE: Dict[str, StepTypeSpec] = _build_spec_map(_SPECS)


def get_step_type_spec(detail_type: object) -> Optional[StepTypeSpec]:
    normalized = str(detail_type or "")
    if not normalized:
        return None
    return _SPECS_BY_TYPE.get(normalized)


def list_registered_step_types() -> list[str]:
    return _sorted_unique(_SPECS_BY_TYPE.keys())


# =============================================================================
# Derived constants (consumed by todo_config.StepTypeRules/TodoStyles/Icons/Colors)
# =============================================================================

GRAPH_TASK_TYPES: list[str] = _sorted_unique(
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.supports_preview
)

GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW: list[str] = _sorted_unique(
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if not spec.supports_preview
)

AUTO_CHECK_GRAPH_STEP_TYPES: set[str] = {
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.supports_auto_check
}

RICH_TEXT_GRAPH_STEP_TYPES: set[str] = {
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.supports_rich_tokens
}

CONTEXT_MENU_EXECUTABLE_STEP_TYPES: set[str] = {
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.supports_context_menu_execution
}

CONFIG_STEP_TYPES: set[str] = {spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.is_config_step}

TYPE_SETTING_STEP_TYPES: set[str] = {
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.is_type_setting_step
}

VIRTUAL_DETAIL_CHILDREN_STEP_TYPES: set[str] = {
    spec.detail_type for spec in _SPECS_BY_TYPE.values() if spec.has_virtual_detail_children
}

GRAPH_STEP_TYPE_ICON_MAP: dict[str, str] = {
    spec.detail_type: spec.icon for spec in _SPECS_BY_TYPE.values() if isinstance(spec.icon, str) and spec.icon
}

STEP_TYPE_COLOR_MAP: dict[str, str] = {
    spec.detail_type: spec.color for spec in _SPECS_BY_TYPE.values() if isinstance(spec.color, str) and spec.color
}


