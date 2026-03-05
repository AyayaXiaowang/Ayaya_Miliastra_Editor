"""常量编辑器：展示文本解析（用于控件虚拟化占位绘制）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.graph.common import VARIABLE_NAME_PORT_NAME

from app.ui.widgets.constant_editors_helpers import (
    _extract_level_variable_id_candidate,
    _safe_strip_text,
    _try_resolve_level_variable_name_from_id,
)

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


def resolve_constant_display_for_port(
    node_item: "NodeGraphicsItem",
    port_name: str,
    port_type: str,
) -> tuple[str, str]:
    """将 node.input_constants 的原始值解析为“画布展示文本”。

    目的：
    - 供节点图在“未创建真实编辑控件（虚拟化）”时绘制占位文本；
    - 与 `ConstantTextEdit._sync_display_from_node_constant` 保持一致的语义化展示口径：
      - 关卡变量引用：var_xxx → 中文 variable_name（tooltip 保留 var_xxx）
      - self.owner_entity → 获取自身实体（tooltip 保留原文）
      - 字符串 "None" 视为未填写 → 空文本

    Returns:
        (display_text, tooltip_text)
    """
    port_name_text = str(port_name or "").strip()
    port_type_text = str(port_type or "").strip()

    tooltip_text = ""

    # 1) 布尔值：与 ConstantBoolComboBox 的判定口径一致
    if port_type_text == "布尔值":
        raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, False)
        is_true: bool = False
        if isinstance(raw_value, bool):
            is_true = bool(raw_value)
        elif isinstance(raw_value, (int, float)):
            is_true = bool(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip().lower()
            is_true = text in {"true", "是", "1", "yes", "y", "on"}
        return ("是" if is_true else "否", tooltip_text)

    # 2) 三维向量：统一为 "x, y, z" 字符串展示
    if port_type_text == "三维向量":
        raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, "0, 0, 0")
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 3:
            values = [str(v).strip() for v in raw_value]
        else:
            text_value = _safe_strip_text(raw_value)
            if (len(text_value) >= 2) and (
                (text_value[0] == "(" and text_value[-1] == ")") or (text_value[0] == "[" and text_value[-1] == "]")
            ):
                text_value = text_value[1:-1].strip()
            values = [v.strip() for v in text_value.split(",")]
        if len(values) != 3:
            values = ["0", "0", "0"]
        return (f"{values[0]}, {values[1]}, {values[2]}", tooltip_text)

    # 3) 其它类型：按文本展示 + 特殊语义化映射
    raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, "")
    raw_text = _safe_strip_text(raw_value)

    # 将值为字符串 "None" 的常量视为“未填写”
    if isinstance(raw_value, str) and raw_text.lower() == "none":
        raw_text = ""

    display_text = raw_text

    # 关卡变量（自定义变量）端口：var_xxx → 中文 variable_name
    node_title = str(getattr(getattr(node_item, "node", None), "title", "") or "").strip()
    if raw_text and (port_name_text == VARIABLE_NAME_PORT_NAME) and node_title and ("自定义变量" in node_title):
        candidate_id = _extract_level_variable_id_candidate(raw_text)
        resolved_name = _try_resolve_level_variable_name_from_id(candidate_id, node_item=node_item)
        if resolved_name:
            display_text = resolved_name
            tooltip_text = candidate_id

    # 图所属实体：self.owner_entity（语义化展示为“获取自身实体”）
    if raw_text == "self.owner_entity" and display_text == raw_text:
        display_text = "获取自身实体"
        tooltip_text = "self.owner_entity"

    return display_text, tooltip_text

