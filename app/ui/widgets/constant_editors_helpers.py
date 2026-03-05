"""常量编辑器：内部 helper（文本清洗、变量 ID/名称映射、虚拟化判定等）。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


def _safe_strip_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _extract_level_variable_id_candidate(text_value: object) -> str:
    """从常见展示/存储格式中提取“候选 variable_id”。

    兼容：
    - `name (variable_id)`
    - `name | variable_id | ...`
    - 直接为 `variable_id`
    """
    raw_text = _safe_strip_text(text_value)
    if not raw_text:
        return ""

    candidate = raw_text

    # 1) name (variable_id)
    if candidate.endswith(")") and "(" in candidate:
        inside = candidate.rsplit("(", 1)[-1].rstrip(")").strip()
        if inside:
            candidate = inside

    # 2) name | variable_id | ...
    if "|" in candidate:
        parts = [part.strip() for part in candidate.split("|")]
        if len(parts) >= 2 and parts[1]:
            candidate = parts[1]

    return candidate or raw_text


def _get_package_level_variables_from_node_item(
    node_item: "NodeGraphicsItem",
) -> dict[str, dict[str, Any]] | None:
    """从 GraphScene 的 signal_edit_context 中获取“当前包引用过滤后的关卡变量集合”。

    返回字典形态：{variable_id: payload}
    """
    scene = node_item.scene()
    scene_any = cast(Any, scene)
    edit_context = getattr(scene_any, "signal_edit_context", None)
    if not isinstance(edit_context, dict):
        return None

    get_current_package = edit_context.get("get_current_package")
    current_package = get_current_package() if callable(get_current_package) else None
    management = getattr(current_package, "management", None) if current_package is not None else None
    package_level_variables = getattr(management, "level_variables", None) if management is not None else None
    if isinstance(package_level_variables, dict) and package_level_variables:
        return package_level_variables
    return None


def _is_inline_constant_virtualization_active_for_node_item(node_item: object) -> bool:
    """判断当前 NodeGraphicsItem 是否启用了“行内常量控件虚拟化”。

    说明：
    - 优先调用 NodeGraphicsItem 自身的判定方法（避免在此处复制 fast_preview_mode 等细节）；
    - 若宿主未提供该方法，则回退到 settings 开关（不抛异常）。
    """
    fn = getattr(node_item, "_is_inline_constant_virtualization_active", None)
    if callable(fn):
        return bool(fn())
    from engine.configs.settings import settings as _settings

    return bool(getattr(_settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))


def _try_resolve_level_variable_name_from_id(
    variable_id: str,
    *,
    node_item: "NodeGraphicsItem",
) -> str:
    """把 variable_id 映射为可展示的 variable_name（用于 UI 显示）。"""
    variable_id_text = _safe_strip_text(variable_id)
    if not variable_id_text:
        return ""

    # 1) 优先使用“当前包过滤后的变量集合”（更贴近用户正在看的存档上下文）
    package_level_variables = _get_package_level_variables_from_node_item(node_item)
    if isinstance(package_level_variables, dict):
        payload = package_level_variables.get(variable_id_text)
        if isinstance(payload, dict):
            display_name = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
            if display_name:
                return display_name

    # 2) 回退到全局 Schema（ID 设计上全局唯一）
    if not variable_id_text.startswith("var_"):
        return ""
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    global_payload = get_default_level_variable_schema_view().get_all_variables().get(variable_id_text)
    if not isinstance(global_payload, dict):
        return ""
    return _safe_strip_text(global_payload.get("variable_name")) or _safe_strip_text(global_payload.get("name"))


def _try_resolve_level_variable_id_from_name(
    variable_name: str,
    *,
    node_item: "NodeGraphicsItem",
) -> str:
    """把 variable_name 映射回稳定 variable_id（仅在可唯一解析时返回）。"""
    variable_name_text = _safe_strip_text(variable_name)
    if not variable_name_text:
        return ""

    # 1) 优先在“当前包过滤后的变量集合”内做名称→ID 匹配
    package_level_variables = _get_package_level_variables_from_node_item(node_item)
    if isinstance(package_level_variables, dict):
        matched_ids: list[str] = []
        for candidate_id, payload in package_level_variables.items():
            if not isinstance(payload, dict):
                continue
            name_text = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
            if name_text == variable_name_text:
                matched_ids.append(str(candidate_id))
                if len(matched_ids) > 1:
                    return ""  # 包内重名：不做不确定映射
        return matched_ids[0] if len(matched_ids) == 1 else ""

    # 2) 无包上下文时：仅在“全局唯一”时映射
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    all_variables = get_default_level_variable_schema_view().get_all_variables()
    if not isinstance(all_variables, dict) or not all_variables:
        return ""

    matched_global_ids: list[str] = []
    for candidate_id, payload in all_variables.items():
        if not isinstance(payload, dict):
            continue
        name_text = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
        if name_text == variable_name_text:
            matched_global_ids.append(str(candidate_id))
            if len(matched_global_ids) > 1:
                return ""  # 全局重名：不做不确定映射
    return matched_global_ids[0] if len(matched_global_ids) == 1 else ""

