# -*- coding: utf-8 -*-
"""
端口与类型模板相关的小工具（仅供 core.automation 内部使用）。

保持纯函数、无副作用，便于在 `editor_executor` 等模块中复用，
避免分散的重复实现。
"""

from __future__ import annotations
from typing import Any, Callable, List, Optional, Tuple, Literal

from engine.utils.graph.graph_utils import is_flow_port_name


PortKind = Literal["flow", "data", "settings", "select", "warning", "other"]
PortCategory = Literal[
    "data_input",
    "data_output",
    "flow_input",
    "flow_output",
    "settings_inline",
    "select_inline",
    "warning_inline",
    "other",
]


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
    """判定是否为不可连接的行内元素模板（如 Settings/Select/Warning 等行内按钮/图标）。

    使用归一化后的种类名进行判断，以便同时覆盖 "Settings2" 等带后缀/变体标记的模板名称。
    """
    kind_norm = normalize_kind_text(text)
    return kind_norm in ("settings", "select", "warning")


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


def get_port_kind_text(port_obj: Any) -> PortKind:
    """基于端口对象的 kind 文本做归一化，返回标准种类名称。"""
    raw = str(getattr(port_obj, "kind", "") or "")
    return normalize_kind_text(raw)  # type: ignore[return-value]


def is_non_connectable_port(port_obj: Any) -> bool:
    """统一的“不可连接端口”判定，基于端口对象本身而非纯文本。

    目前将 Settings/Select/Warning 一类行内按钮与图标视为不可连接。
    """
    kind_norm = get_port_kind_text(port_obj)
    return kind_norm in ("settings", "select", "warning")


def get_port_center(port_obj: Any) -> Tuple[int, int]:
    """安全取得端口中心坐标，缺失或异常时返回 (0, 0)。"""
    center_value = getattr(port_obj, "center", (0, 0))
    if isinstance(center_value, tuple) and len(center_value) >= 2:
        return int(center_value[0]), int(center_value[1])
    return 0, 0


def get_port_center_x(port_obj: Any) -> int:
    return get_port_center(port_obj)[0]


def get_port_center_y(port_obj: Any) -> int:
    return get_port_center(port_obj)[1]


def get_port_category(port_obj: Any) -> PortCategory:
    """综合 side/kind/name_cn，对端口做高层语义分类。

    约定：
    - Settings/Select/Warning 一律视为行内元素（不可连接）；
    - data_input 复用现有 is_data_input_port 的语义，保证与输入类型设置等场景严格一致；
    - flow_input/flow_output 优先使用 kind 归一化为 flow，其次用端口中文名做回退；
    - data_output 代表右侧且 kind 归一化为 data 的端口；
    - 其余情况归入 other。
    """
    side_text = str(getattr(port_obj, "side", "") or "").lower()
    kind_norm = get_port_kind_text(port_obj)
    name_cn = str(getattr(port_obj, "name_cn", "") or "")

    # 1) 行内控件/图标
    if kind_norm == "settings":
        return "settings_inline"
    if kind_norm == "select":
        return "select_inline"
    if kind_norm == "warning":
        return "warning_inline"

    # 2) 数据输入端口：与 is_data_input_port 语义保持完全一致
    if is_data_input_port(port_obj):
        return "data_input"

    # 3) 流程端口（输入/输出）
    is_flow_like = (kind_norm == "flow") or is_flow_port_name(name_cn)
    if is_flow_like:
        if side_text == "left":
            return "flow_input"
        if side_text == "right":
            return "flow_output"
        return "other"

    # 4) 数据输出端口：右侧且归一化种类为 data
    if side_text == "right" and kind_norm == "data":
        return "data_output"

    return "other"


def filter_ports_for_screen_candidates(
    ports_all: List[Any],
    preferred_side: Optional[str],
    expected_kind: Optional[str],
    log_kind_miss: Optional[Callable[[str], None]] = None,
) -> List[Any]:
    """按侧别与种类(flow/data)过滤“可连接端口”候选，并按垂直位置从上到下排序。

    约定：
    - preferred_side 为 'left' / 'right' 时优先使用该侧端口；若该侧无候选则回退为“不限制侧别”，
      以在端口识别 side 字段缺失或错误时仍能得到候选列表；
    - 始终排除行内不可连接元素（Settings/Select/Warning 等）；
    - expected_kind 为 'flow' 或 'data' 时，仅当该类型在当前候选集中存在时才收紧到该类型；
      若不存在则保留原候选并在提供 log_kind_miss 回调时输出说明日志；
    - 返回列表按 center.y 从小到大排序，表示“从上到下”的屏幕顺序。
    """
    candidates: List[Any] = list(ports_all)

    side = (preferred_side or "").lower()
    if side in ("left", "right"):
        specific = [
            port_obj
            for port_obj in candidates
            if str(getattr(port_obj, "side", "")).lower() == side
        ]
        # 仅在该侧存在至少一个端口时才收紧侧别，否则退回“不限制侧别”
        if len(specific) > 0:
            candidates = specific

    # 排除行内不可连接元素
    candidates = [port_obj for port_obj in candidates if not is_non_connectable_port(port_obj)]

    # 按类型(flow/data)进一步筛选，必要时保留原候选并输出日志
    if expected_kind in ("flow", "data"):
        by_kind: List[Any]
        if expected_kind == "data" and side == "left":
            # 左侧数据端口沿用 is_data_input_port 的语义，确保与输入类型设置等场景一致
            by_kind = [port_obj for port_obj in candidates if is_data_input_port(port_obj)]
        else:
            by_kind = [
                port_obj
                for port_obj in candidates
                if normalize_kind_text(str(getattr(port_obj, "kind", "") or "")) == expected_kind
            ]
        if len(by_kind) > 0:
            candidates = by_kind
        elif log_kind_miss is not None:
            log_kind_miss(
                f"[端口定位] 期望类型 '{expected_kind}' 无候选，改为不限制类型继续匹配"
            )

    def _sort_key(port_obj: Any) -> int:
        return get_port_center_y(port_obj)

    return sorted(candidates, key=_sort_key)


