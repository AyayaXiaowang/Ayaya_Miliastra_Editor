from __future__ import annotations

from typing import Any, Dict, List

from ...comprehensive_types import ValidationIssue


def validate_signal_constants_for_send_node(
    node: Dict[str, Any],
    location: str,
    detail: Dict[str, Any],
    param_type_map: Dict[str, str],
) -> List[ValidationIssue]:
    """3.3 参数值类型校验：发送信号节点上常量值是否符合信号参数类型。"""
    issues: List[ValidationIssue] = []
    input_constants = node.get("input_constants", {}) or {}
    if not isinstance(input_constants, dict):
        return issues

    for param_name, expected_type in param_type_map.items():
        if param_name not in input_constants:
            continue
        raw_value = input_constants[param_name]
        value_str = str(raw_value)
        if _is_value_compatible_with_type(value_str, expected_type):
            continue
        node_detail = dict(detail)
        node_detail["param_name"] = param_name
        node_detail["expected_type"] = expected_type
        node_detail["current_value"] = value_str
        issues.append(
            ValidationIssue(
                level="error",
                category="信号系统",
                location=location,
                message=(
                    "[信号参数错误] 节点的参数 "
                    f"'{param_name}' 期望类型 '{expected_type}'，"
                    f"当前填入 '{value_str}'。"
                ),
                suggestion="请根据信号参数类型修正常量格式，例如数值/向量/列表的书写方式。",
                reference="信号系统设计.md:3.3 参数值类型校验",
                detail=node_detail,
            )
        )

    return issues


def _strip_quotes(text: str) -> str:
    value = text.strip()
    if len(value) >= 2:
        left = value[0]
        right = value[-1]
        if (left == "'" and right == "'") or (left == '"' and right == '"'):
            return value[1:-1].strip()
    return value


def _is_int_literal(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if value[0] in "+-":
        body = value[1:]
    else:
        body = value
    return body.isdigit() and body != ""


def _is_float_literal(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if _is_int_literal(value):
        return True
    if value[0] in "+-":
        body = value[1:]
    else:
        body = value
    parts = body.split(".")
    if len(parts) != 2:
        return False
    left = parts[0]
    right = parts[1]
    if left != "" and not left.isdigit():
        return False
    if right != "" and not right.isdigit():
        return False
    return left != "" or right != ""


def _is_bool_literal(text: str) -> bool:
    value = text.strip()
    return value in {"True", "False", "true", "false", "是", "否", "0", "1"}


def _split_vector_components(text: str) -> List[str]:
    raw = text.strip()
    if len(raw) >= 2:
        left = raw[0]
        right = raw[-1]
        if (left == "(" and right == ")") or (left == "[" and right == "]"):
            raw = raw[1:-1].strip()
    raw = raw.replace("，", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    if len(parts) < 3:
        more = [p.strip() for p in raw.split() if p.strip() != ""]
        parts = more
    return parts


def _is_vector3_literal(text: str) -> bool:
    components = _split_vector_components(text)
    if len(components) != 3:
        return False
    for component in components:
        if not (_is_int_literal(component) or _is_float_literal(component)):
            return False
    return True


def _split_list_items(text: str) -> List[str]:
    raw = text.strip()
    if not raw:
        return []
    if len(raw) >= 2:
        left = raw[0]
        right = raw[-1]
        if (left == "[" and right == "]") or (left == "{" and right == "}"):
            raw = raw[1:-1].strip()
    raw = raw.replace("，", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    return parts


def _is_value_compatible_with_type(value_str: str, expected_type: str) -> bool:
    """根据信号参数类型的语义，粗略判断常量字符串是否兼容。"""
    type_name = expected_type.strip()
    plain_value = _strip_quotes(value_str)

    # 字符串类型不过滤，避免误报（格式通常由上游规则约束）
    if type_name in {"字符串", "字符串列表"}:
        return True

    if type_name == "整数":
        return _is_int_literal(plain_value)
    if type_name == "浮点数":
        return _is_float_literal(plain_value)
    if type_name == "布尔值":
        return _is_bool_literal(plain_value)
    if type_name == "三维向量":
        return _is_vector3_literal(plain_value)
    if type_name in {"GUID", "实体", "元件ID", "配置ID"}:
        return _is_int_literal(plain_value)

    items = _split_list_items(plain_value)
    if type_name == "整数列表":
        return all(_is_int_literal(item) for item in items) or not items
    if type_name == "浮点数列表":
        return all(_is_float_literal(item) for item in items) or not items
    if type_name == "布尔值列表":
        return all(_is_bool_literal(item) for item in items) or not items
    if type_name == "三维向量列表":
        return all(_is_vector3_literal(item) for item in items) or not items
    if type_name in {"GUID列表", "实体列表", "元件ID列表", "配置ID列表"}:
        return all(_is_int_literal(item) for item in items) or not items

    # 未识别的类型：保持宽松，视为兼容，避免误报
    return True


__all__ = ["validate_signal_constants_for_send_node"]


