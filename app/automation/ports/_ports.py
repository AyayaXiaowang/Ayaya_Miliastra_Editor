# -*- coding: utf-8 -*-
"""
端口与类型模板相关的小工具（仅供 core.automation 内部使用）。

保持纯函数、无副作用，便于在 `editor_executor` 等模块中复用，
避免分散的重复实现。
"""

from __future__ import annotations
from engine.utils.graph.graph_utils import is_flow_port_name


def normalize_kind_text(text: str) -> str:
    """将模板/检测返回的端口种类文本归一化为 flow/data/settings/select/warning/other。
    
    约定：
    - 包含 "settings" 或 "设置" → settings（行内设置按钮）
    - 包含 "select" 或 "选择" → select（行内选择控件/选择端口）
    - 包含 "warning" 或 "警告" → warning（行内告警图标）
    - 包含 "process"、"流程" 或等于 "flow" → flow
    - 在 {data, data2, generic, generic2, list} 或包含"数据"/"列表" → data
    - 其余 → other
    """
    raw = str(text or "")
    lowered = raw.lower()
    if ("settings" in lowered) or ("设置" in raw):
        return "settings"
    if ("select" in lowered) or ("选择" in raw):
        return "select"
    if ("warning" in lowered) or ("警告" in raw):
        return "warning"
    if ("流程" in raw) or ("process" in lowered) or (lowered == "flow"):
        return "flow"
    if (
        ("数据" in raw)
        or ("列表" in raw)
        or lowered in ("data", "data2", "generic", "generic2", "list")
    ):
        return "data"
    return "other"


def is_non_connectable_kind(text: str) -> bool:
    """判定是否为不可连接的行内元素模板（如 Settings/Select/Warning）。"""
    tl = (text or "").lower()
    return tl in ("settings", "select", "warning")



def is_data_input_port(port_obj) -> bool:
    """判断是否为“数据输入端口”。

    规则：
    - 必须在左侧（side == 'left'）
    - 排除行内元素（Settings/Warning）
    - 排除流程端口：优先用 kind 归一化为 flow；若 kind 不可用，再以端口中文名做回退判断
    """
    side = str(getattr(port_obj, 'side', '') or '')
    if side != 'left':
        return False
    kind_text = str(getattr(port_obj, 'kind', '') or '')
    if is_non_connectable_kind(kind_text):
        return False
    if normalize_kind_text(kind_text) == 'flow':
        return False
    name_text = str(getattr(port_obj, 'name_cn', '') or '')
    if is_flow_port_name(name_text):
        return False
    return True


def is_flow_output_port(port_obj) -> bool:
    """判断是否为“流程输出端口”候选。

    规则：
    - 必须在右侧（side == 'right'）
    - 排除行内元素（Settings/Warning）
    - 对 kind 不做强制要求：若检测不可用，仍保留右侧端口作为候选（与现有逻辑一致）
    """
    side = str(getattr(port_obj, 'side', '') or '')
    if side != 'right':
        return False
    kind_text = str(getattr(port_obj, 'kind', '') or '')
    if is_non_connectable_kind(kind_text):
        return False
    return True


