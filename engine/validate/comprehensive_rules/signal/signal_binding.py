from __future__ import annotations

from typing import Any, Dict

from engine.graph.common import SIGNAL_NAME_PORT_NAME
from engine.nodes.advanced_node_features import SignalDefinition


def infer_signal_id_from_constants(
    node: Dict[str, Any],
    signal_definitions: Dict[str, SignalDefinition],
) -> str:
    """根据节点上的“信号名”输入常量推断信号 ID。

    约定：
    - 常量文本被视为信号的“显示名称”（SignalDefinition.signal_name）；
    - 不再接受直接填写信号 ID，ID 仅通过绑定或 register_handlers 传入；
    - 只在节点本身尚未绑定 signal_id 时作为智能回退使用。
    """
    if not signal_definitions:
        return ""

    input_constants = node.get("input_constants", {}) or {}
    if not isinstance(input_constants, dict):
        return ""

    raw_value = input_constants.get(SIGNAL_NAME_PORT_NAME)
    if raw_value is None:
        return ""

    text = str(raw_value).strip()
    if not text:
        return ""

    # 按 signal_name 匹配到对应的 ID
    for signal_id, signal_def in signal_definitions.items():
        signal_name_value = getattr(signal_def, "signal_name", None)
        if str(signal_name_value or "").strip() == text:
            return str(signal_id)

    return ""


__all__ = ["infer_signal_id_from_constants"]


