from __future__ import annotations

import re
import unicodedata
from typing import List

from engine.configs.resource_types import ResourceType
from engine.configs.specialized.node_graph_configs import STRUCT_TYPE_INGAME_SAVE

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_STRUCT_ID_10_DIGITS_PATTERN = re.compile(r"^[0-9]{10}$")
_CUSTOM_VARIABLE_NAME_MAX_LEN = 20


class ManagementConfigRule(BaseComprehensiveRule):
    rule_id = "package.management"
    category = "管理配置"
    default_level = "warning"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_management_configs(self.validator)


def validate_management_configs(validator) -> List[ValidationIssue]:
    management = getattr(validator.package, "management", None)
    if not management:
        return []
    issues: List[ValidationIssue] = []
    issues.extend(_validate_layout_widget_templates(management))
    issues.extend(_validate_level_variables(management))
    issues.extend(_validate_struct_definitions(validator))
    return issues

def _validate_layout_widget_templates(management) -> List[ValidationIssue]:
    layouts = getattr(management, "ui_layouts", {}) or {}
    templates = getattr(management, "ui_widget_templates", {}) or {}
    if not layouts:
        return []
    issues: List[ValidationIssue] = []
    for layout_id, layout_data in layouts.items():
        if not isinstance(layout_data, dict):
            continue
        layout_name = (
            layout_data.get("layout_name")
            or layout_data.get("name")
            or layout_id
        )

        referenced_ids: List[str] = []
        builtin_widgets = layout_data.get("builtin_widgets", []) or []
        custom_groups = layout_data.get("custom_groups", []) or []
        for bucket in (builtin_widgets, custom_groups):
            if not isinstance(bucket, list):
                continue
            for raw_id in bucket:
                if isinstance(raw_id, str) and raw_id.strip():
                    referenced_ids.append(raw_id.strip())

        if not referenced_ids:
            continue

        for template_id in referenced_ids:
            if template_id in templates:
                continue
            template_payload = templates.get(template_id, {})
            template_name = ""
            if isinstance(template_payload, dict):
                template_name = (
                    template_payload.get("template_name")
                    or template_payload.get("name")
                    or ""
                )
            widget_name = template_name or template_id
            detail = {
                "type": "management_ui_layout",
                "management_section_key": "ui_control_groups",
                "management_item_id": layout_id,
                "layout_id": layout_id,
                "widget_name": widget_name,
                "template_id": template_id,
            }
            issues.append(
                ValidationIssue(
                    level="error",
                    category="管理配置",
                    location=f"界面布局 '{layout_name}' > 控件 '{widget_name}'",
                    message=f"控件引用的模板 '{template_id}' 未在 UI 控件模板库中定义",
                    suggestion="请先在管理配置中创建对应的 UI 控件模板，或移除该引用。",
                    detail=detail,
                )
            )
    return issues


def _validate_level_variables(management) -> List[ValidationIssue]:
    level_variables = getattr(management, "level_variables", {}) or {}
    if not level_variables:
        return []
    issues: List[ValidationIssue] = []
    for variable_id, payload in level_variables.items():
        if not isinstance(payload, dict):
            continue

        variable_id_text = str(variable_id or "").strip()
        variable_name_value = payload.get("variable_name") or payload.get("name") or variable_id_text
        variable_name_text = str(variable_name_value or "").strip()
        if variable_name_text and len(variable_name_text) > _CUSTOM_VARIABLE_NAME_MAX_LEN:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="管理配置",
                    location=f"关卡变量 '{variable_name_text}' (ID: {variable_id_text or '?'})",
                    message=(
                        f"自定义变量名过长：{variable_name_text!r}（len={len(variable_name_text)}，上限={_CUSTOM_VARIABLE_NAME_MAX_LEN}）。"
                    ),
                    suggestion="请压缩 variable_name（<=20），并同步更新节点图/前端/UI 对该变量名的引用。",
                    detail={
                        "type": "management_level_variable_name_too_long",
                        "management_section_key": "variable",
                        "management_item_id": variable_id_text,
                        "variable_id": variable_id_text,
                        "variable_name": variable_name_text,
                        "name_len": len(variable_name_text),
                        "name_len_limit": _CUSTOM_VARIABLE_NAME_MAX_LEN,
                    },
                )
            )
        variable_type = payload.get("variable_type")
        if variable_type:
            continue
        variable_name = payload.get("name", variable_id)
        detail = {
            "type": "management_level_variable",
            "management_section_key": "variable",
            "management_item_id": variable_id,
            "variable_id": variable_id,
            "variable_name": variable_name,
        }
        issues.append(
            ValidationIssue(
                level="warning",
                category="管理配置",
                location=f"关卡变量 '{variable_name}'",
                message="关卡变量缺少 `variable_type` 定义，节点图无法推断其数据类型。",
                suggestion="请在管理配置中为该变量补充变量类型以保证节点引用安全。",
                detail=detail,
            )
        )
    return issues


def _text_width_chinese_as_two(text: str) -> int:
    """计算文本“字符宽度”：中文（宽字符）按 2，其余按 1。"""
    width = 0
    for ch in str(text or ""):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _validate_struct_definitions(validator) -> List[ValidationIssue]:
    """校验结构体定义本身的命名约束（与节点图引用无关）。

    约束：结构体 struct_name 最长 30（中文算 2）。

    额外约束：STRUCT_ID 必须为 **10 位纯数字**（UGC 结构体 ID 的唯一合法表示）。
    """
    resource_manager = getattr(validator, "resource_manager", None)
    if resource_manager is None:
        return []

    file_paths = resource_manager.list_resource_file_paths(ResourceType.STRUCT_DEFINITION)

    issues: List[ValidationIssue] = []
    struct_ids = resource_manager.list_resources(ResourceType.STRUCT_DEFINITION)
    for raw_id in struct_ids:
        if not isinstance(raw_id, str):
            continue
        struct_id = raw_id.strip()
        if not struct_id:
            continue

        if _STRUCT_ID_10_DIGITS_PATTERN.fullmatch(struct_id) is None:
            file_path = file_paths.get(struct_id)
            location = f"结构体定义 STRUCT_ID={struct_id!r}"
            if file_path is not None:
                location = f"{location}  ({file_path})"
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=location,
                    message="STRUCT_ID 必须是 10 位纯数字（例如 1077936129）。",
                    suggestion="请在结构体定义文件中将 STRUCT_ID 改为 10 位纯数字（不允许额外后缀/前缀/下划线）。",
                    detail={
                        "type": "management_struct_definition",
                        "management_section_key": "struct_definitions",
                        "management_item_id": struct_id,
                        "struct_id": struct_id,
                        "file_path": str(file_path) if file_path is not None else "",
                    },
                )
            )
            # 结构体 ID 非法时，后续 name/长度等检查意义不大（也避免 load_resource 异常链路）
            continue

        payload = resource_manager.load_resource(ResourceType.STRUCT_DEFINITION, struct_id)
        if not isinstance(payload, dict):
            continue

        raw_name = payload.get("struct_name")
        struct_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
        if not struct_name:
            continue

        width = _text_width_chinese_as_two(struct_name)
        limit = 30
        if width <= limit:
            continue

        struct_type_value = payload.get("struct_ype") or payload.get("struct_type")
        struct_type_text = str(struct_type_value).strip() if isinstance(struct_type_value, str) else ""
        section_key = (
            "ingame_struct_definitions"
            if struct_type_text == STRUCT_TYPE_INGAME_SAVE
            else "struct_definitions"
        )

        file_path = file_paths.get(struct_id)
        location_name = struct_name or struct_id
        location = f"结构体 '{location_name}'"
        if file_path is not None:
            location = f"{location}  ({file_path})"

        issues.append(
            ValidationIssue(
                level="error",
                category="结构体系统",
                location=location,
                message=f"结构体名称过长：{width}/{limit}（中文算2）",
                suggestion=(
                    "请缩短结构体定义中的 `name`/`struct_name` 文本，使其长度不超过 30（中文算2）。"
                ),
                detail={
                    "type": "management_struct_definition",
                    "management_section_key": section_key,
                    "management_item_id": struct_id,
                    "struct_id": struct_id,
                    "struct_name": struct_name,
                    "name_width": width,
                    "name_width_limit": limit,
                    "struct_type": struct_type_text,
                    "file_path": str(file_path) if file_path is not None else "",
                },
            )
        )

    return issues


__all__ = ["ManagementConfigRule"]

