from __future__ import annotations

from typing import Any, Dict, Optional


def parse_initial_visible(value: Any, *, default_value: bool = True) -> bool:
    if value is None:
        return bool(default_value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return bool(int(value) != 0)
    if isinstance(value, float):
        if not (value == value):  # NaN
            return bool(default_value)
        return bool(float(value) != 0.0)
    text = str(value).strip().lower()
    if text == "":
        return bool(default_value)
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return bool(default_value)


def _try_get_visibility_node14(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    返回用于表达“初始隐藏”的 node14（dict），或 None。

    经验口径（对齐真源/参考存档）：
    - 初始隐藏由 `component_list[1]['503']['14']['502']=1` 表达（缺失=可见，=1=隐藏）
    - 少量 record 形态可能在 component_list[1] 缺失 node14；此时才降级扫描其它 component
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None

    # 优先：component_list[1]
    if len(component_list) >= 2 and isinstance(component_list[1], dict):
        nested1 = component_list[1].get("503")
        if isinstance(nested1, dict):
            node14 = nested1.get("14")
            if isinstance(node14, dict) and node14.get("501") == 5:
                return node14

    # 兜底：扫描其它 component（避免因真源差异导致“完全写不进初始隐藏”）
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        node14 = nested.get("14")
        if not isinstance(node14, dict):
            continue
        # guard：真源样本中该 node14 具备固定形态（含 15/<binary_data> 与 501=5）
        if node14.get("501") != 5:
            continue
        return node14
    return None


def apply_visibility_patch(record: Dict[str, Any], *, visible: Optional[bool]) -> int:
    if visible is None:
        return 0
    #
    # IMPORTANT (对齐真源/参考存档)：
    # “初始隐藏”并不是通过 `record['505'][*]['503']['503']` 控制。
    #
    # 在用户提供的真源参考存档中：
    # - 所有 component 的 `nested['503']` 恒为 1
    # - 初始隐藏由 `component_list[1]['503']['14']['502']=1` 表达
    #   - 可见：node14 不含 502
    #   - 隐藏：node14.502 == 1
    #
    # 因此这里按该字段写回，避免“dump-readable 显示隐藏但编辑器仍显示”的错觉。
    desired_hidden_flag = 1 if (not bool(visible)) else None
    node14 = _try_get_visibility_node14(record)
    if node14 is None:
        return 0

    if desired_hidden_flag is None:
        # visible: remove node14.502 if present (match reference: missing means visible)
        if "502" in node14:
            node14.pop("502", None)
            return 1
        return 0

    # hidden: ensure node14.502 == 1
    current = node14.get("502")
    if current != 1:
        node14["502"] = 1
        return 1
    return 0


def try_get_record_visibility_flag(record: Dict[str, Any]) -> Optional[int]:
    node14 = _try_get_visibility_node14(record)
    if node14 is None:
        return None
    # 参考存档：node14.502 缺失=可见；=1 表示隐藏
    hidden = bool(int(node14.get("502", 0)) == 1)
    return 0 if hidden else 1

