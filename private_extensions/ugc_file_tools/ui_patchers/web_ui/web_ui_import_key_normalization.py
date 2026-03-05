from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .web_ui_import_guid_registry import normalize_ui_key


def _summarize_widget_value(value: Any) -> Any:
    """
    用于 report/debug 的轻量摘要：
    - 保留常见标量/小结构
    - 避免把超大字符串/深层结构塞进 report（难读且易膨胀）
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        s = value
        if len(s) > 300:
            return s[:300] + "…"
        return s
    if isinstance(value, (list, tuple)):
        if len(value) > 16:
            return list(value[:16]) + ["…"]
        return list(value)
    if isinstance(value, dict):
        # 只保留一层 + 限制 key 数量
        out: Dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 24:
                out["…"] = "…"
                break
            kk = str(k)
            out[kk] = _summarize_widget_value(v)
        return out
    return str(value)


def build_widget_source_meta(
    widget: Dict[str, Any],
    *,
    ui_key: str,
    widget_id: str,
    widget_name: str,
    widget_type: str,
    widget_index: int,
    group_key: str,
) -> Dict[str, Any]:
    """
    构造“导入溯源信息”，用于回答：
    - 这个 guid 对应的控件到底是谁（哪个 ui_key / 哪类 widget / 从哪个组件组来的）
    - 它的原始位置/大小/settings 是什么
    - widget 是否带有前端/Workbench 的 HTML 溯源字段（通常以 __ 开头）
    """
    meta: Dict[str, Any] = {
        "ui_key": str(ui_key),
        "widget_id": str(widget_id),
        "widget_name": str(widget_name),
        "widget_type": str(widget_type),
        "widget_index": int(widget_index),
        "group_key": str(group_key),
        "layer_index": int(widget.get("layer_index") or 0),
        "position": _summarize_widget_value(widget.get("position")),
        "size": _summarize_widget_value(widget.get("size")),
    }

    settings = widget.get("settings")
    if isinstance(settings, dict):
        # 保留一份“扁平化摘要”，方便肉眼查：颜色/背景/绑定变量等
        meta["settings"] = _summarize_widget_value(settings)

    # 额外溯源字段：允许前端/Workbench 带任意 "__xxx" 附加信息
    extra: Dict[str, Any] = {}
    for k, v in widget.items():
        key = str(k)
        if not key.startswith("__"):
            continue
        extra[key] = _summarize_widget_value(v)
    if extra:
        meta["extra"] = extra

    return meta


def ensure_unique_ui_keys_in_widgets(widgets: List[Any]) -> int:
    """
    guard: ui_key must be unique inside one import

    经验：若 Workbench 导出的 ui_key 未全局唯一（例如同一元素多个 shadow 层仍然同 key），
    写回阶段会把多个 widget 复用同一个 GUID，导致“游戏里看起来少了很多”。
    后端在写回时强制做一次去重（不依赖前端实现是否正确）。

    返回：本次修复的冲突数量。
    """
    seen_ui_keys: set[str] = set()
    fixed_total = 0

    def rect_suffix_from_widget_dict(w: Dict[str, Any]) -> str:
        pos = w.get("position")
        size = w.get("size")
        if not (isinstance(pos, (list, tuple)) and isinstance(size, (list, tuple)) and len(pos) == 2 and len(size) == 2):
            return ""
        x = float(pos[0])
        y = float(pos[1])
        ww = float(size[0])
        hh = float(size[1])
        if ww <= 0 or hh <= 0:
            return ""
        ix = int(round(x))
        iy = int(round(y))
        iw = int(round(ww))
        ih = int(round(hh))
        return f"r{ix}_{iy}_{iw}_{ih}"

    for w in widgets:
        if not isinstance(w, dict):
            continue
        widget_id = str(w.get("widget_id") or "")
        raw_key = str(w.get("ui_key") or "").strip() or widget_id
        if raw_key == "":
            continue
        key = raw_key
        if key in seen_ui_keys:
            rect_suffix = rect_suffix_from_widget_dict(w)
            base = raw_key
            candidate = f"{base}__{rect_suffix}" if rect_suffix else f"{base}__dup"
            counter = 2
            while candidate in seen_ui_keys:
                candidate = f"{base}__{rect_suffix if rect_suffix else 'dup'}_{counter}"
                counter += 1
            w["ui_key"] = candidate
            key = candidate
            fixed_total += 1
        seen_ui_keys.add(key)

    return int(fixed_total)


def collect_ui_action_meta_by_ui_key(widgets: List[Any]) -> Dict[str, Dict[str, str]]:
    """
    UI 交互动作标注：由 Workbench 导出，写回端不解释其语义，仅用于生成映射文件供节点图侧自由处理。
    注意：必须在 ui_key 去重之后再采集（否则 action 可能还挂在“去重前的 key”上）。
    """
    out: Dict[str, Dict[str, str]] = {}
    for w in widgets:
        if not isinstance(w, dict):
            continue
        widget_id = str(w.get("widget_id") or "")
        ui_key = normalize_ui_key(w.get("ui_key"), fallback=widget_id)
        action_key = str(w.get("ui_action_key") or "").strip()
        action_args = str(w.get("ui_action_args") or "").strip()
        if action_key == "" and action_args == "":
            continue
        out[ui_key] = {"action_key": action_key, "action_args": action_args}
    return out

