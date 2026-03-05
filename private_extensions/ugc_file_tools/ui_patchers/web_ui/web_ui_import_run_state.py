from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from .web_ui_import_types import ImportedWebItemDisplay, ImportedWebProgressbar, ImportedWebTextbox


@dataclass(slots=True)
class WebUiImportRunState:
    imported_progressbars: List[ImportedWebProgressbar]
    imported_textboxes: List[ImportedWebTextbox]
    imported_item_displays: List[ImportedWebItemDisplay]

    skipped_widgets: List[Dict[str, Any]]

    referenced_variable_full_names: Set[str]
    # (group_name, variable_name) -> roles(current/min/max)
    progressbar_variable_roles: Dict[Tuple[str, str], Set[str]]
    progressbar_binding_auto_filled_total: int

    ui_click_actions: List[Dict[str, Any]]

    # guid -> widget_index (for deterministic ordering)
    import_order_by_guid: Dict[int, int]

    # 导入溯源：记录“导入时看到的原始 widget 信息”（来自 Workbench bundle/widgets）
    # - key: 控件 guid（写回后的 guid）
    # - value: 原始 widget 的关键字段（ui_key/widget_type/position/size/settings/...）
    widget_sources_by_guid: Dict[int, Dict[str, Any]]

    # UI 交互按键码（道具展示）：同一页面强制 1..14 且唯一
    interactive_item_display_key_codes_used: Set[int]
    # UI 交互按键码冲突（不再阻断导入）：用于 report 提示与排查
    interactive_item_display_key_code_warnings: List[Dict[str, Any]]

    # 道具展示（按钮锚点）所引用的“配置ID变量”（用于写回阶段自动创建到目标实体自定义变量列表）
    # (group_name, variable_name) -> referenced
    item_display_config_id_variable_refs: Set[Tuple[str, str]]

    # 道具展示（按钮锚点）所引用的“整数变量”（次数/数量等，type_code=3），用于写回阶段自动创建
    item_display_int_variable_refs: Set[Tuple[str, str]]

    # 道具展示（按钮锚点）所引用的“浮点变量”（冷却时间等，type_code=5），用于写回阶段自动创建
    item_display_float_variable_refs: Set[Tuple[str, str]]

    # 文本框占位符引用到的变量：
    # - {{lv.var}}：标量变量（自动创建为字符串 type_code=6）
    # - {{lv.dict.key}}：字典变量（自动创建为字典 type_code=27，key_type=字符串，value_type 由命名后缀或默认值推断）
    # 结构：(group_name, variable_name, field_path_parts)
    # - field_path_parts 为空 tuple：标量
    # - field_path_parts 非空：字典 key 路径（多段会用 '.' 拼成一个键名）
    text_placeholder_variable_refs: Set[Tuple[str, str, Tuple[str, ...]]]

    # 初始可见性写回：record component['503']['503']（1=可见，0=隐藏）
    visibility_changed_total: int
