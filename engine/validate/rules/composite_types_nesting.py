from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text
from engine.nodes.node_registry import get_node_registry
from engine.type_registry import (
    BANNED_TYPE_ALIASES,
    COMPOSITE_ALLOWED_DATA_PIN_TYPES,
    PYTHON_BUILTIN_TYPE_NAMES,
    parse_typed_dict_alias,
    TYPE_FLOW,
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    TYPE_LIST_PLACEHOLDER,
)
from engine.graph.composite.source_format import (
    find_composite_classes,
    try_extract_composite_payload_json,
)
from engine.graph.composite.pin_marker_collector import (
    PinMarker,
    collect_pin_markers,
    infer_data_inputs_from_signature,
)


BANNED_PIN_TYPES: Set[str] = set(BANNED_TYPE_ALIASES)
PYTHON_BUILTIN_PIN_TYPES: Set[str] = set(PYTHON_BUILTIN_TYPE_NAMES)
# 复合节点对外引脚类型允许：基础类型/列表类型/字典/流程。
# “泛型/列表/泛型列表/泛型字典”等仅作为编辑期“未设置”的占位，成品校验阶段必须禁止。
ALLOWED_DATA_PIN_TYPES: Set[str] = set(COMPOSITE_ALLOWED_DATA_PIN_TYPES)


class CompositeTypesAndNestingRule(ValidationRule):
    """复合节点：参数/返回中文类型、流程入必填（允许复合内嵌套复合）"""

    rule_id = "engine_composite_types_and_nesting"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if not ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        # 0) payload 格式（可视化落盘）：直接从 JSON 校验虚拟引脚与嵌套复合
        payload_json = try_extract_composite_payload_json(tree)
        if payload_json is not None:
            payload_obj = json.loads(payload_json)
            issues.extend(_check_payload_virtual_pins(payload_obj, file_path, default_level=self.default_level))
            return issues

        # 1) 类格式复合节点（@composite_class）：以方法体 pin_marker 声明为权威来源
        composite_classes = find_composite_classes(tree)
        if composite_classes:
            issues.extend(
                _check_class_based_pin_markers_and_nesting(
                    composite_classes,
                    file_path,
                    default_level=self.default_level,
                )
            )
            return issues

        issues.append(
            EngineIssue(
                level=self.default_level,
                category="复合节点",
                code="COMPOSITE_FORMAT_UNSUPPORTED",
                message=(
                    "复合节点仅支持 payload（COMPOSITE_PAYLOAD_JSON）或类格式（@composite_class）。"
                    "旧函数式复合节点格式已不再支持，请迁移为类格式并通过校验后再使用。"
                ),
                file=str(file_path),
            )
        )
        return issues


def _decorator_name(decorator: ast.AST) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return ""


def _check_payload_virtual_pins(
    payload_obj: object,
    file_path: Path,
    *,
    default_level: str,
) -> List[EngineIssue]:
    issues: List[EngineIssue] = []
    if not isinstance(payload_obj, dict):
        issues.append(
            EngineIssue(
                level=default_level,
                category="复合节点",
                code="COMPOSITE_PAYLOAD_INVALID",
                message="COMPOSITE_PAYLOAD_JSON 解析后必须为 dict（CompositeNodeConfig.serialize() 的结果）",
                file=str(file_path),
            )
        )
        return issues

    virtual_pins = payload_obj.get("virtual_pins", [])
    if not isinstance(virtual_pins, list):
        issues.append(
            EngineIssue(
                level=default_level,
                category="复合节点",
                code="COMPOSITE_PAYLOAD_INVALID",
                message="COMPOSITE_PAYLOAD_JSON.virtual_pins 必须为 list",
                file=str(file_path),
            )
        )
        return issues

    for pin in virtual_pins:
        if not isinstance(pin, dict):
            continue
        pin_name = str(pin.get("pin_name", "") or "")
        pin_type = str(pin.get("pin_type", "") or "")
        is_input = bool(pin.get("is_input", False))
        is_flow = bool(pin.get("is_flow", False))
        effective_type = "流程" if is_flow else pin_type

        if not _is_supported_pin_type(effective_type):
            suggestion = _build_pin_type_suggestion(effective_type)
            issues.append(
                EngineIssue(
                    level=default_level,
                    category="复合节点",
                    code="COMPOSITE_PIN_TYPE_FORBIDDEN",
                    message=f"payload 复合节点引脚 '{pin_name}' 使用了未受支持的类型标注 '{effective_type}'，{suggestion}",
                    file=str(file_path),
                )
            )

    return issues


def _extract_pin_defs(call_node: ast.Call, keyword: str) -> List[Tuple[str, str, ast.AST]]:
    pins: List[Tuple[str, str, ast.AST]] = []
    for kw in call_node.keywords:
        if kw.arg != keyword:
            continue
        pins.extend(_parse_pin_list_expr(kw.value))
    return pins


def _parse_pin_list_expr(expr: ast.AST) -> List[Tuple[str, str, ast.AST]]:
    pins: List[Tuple[str, str, ast.AST]] = []
    if not isinstance(expr, ast.List):
        return pins
    for elt in expr.elts:
        if not isinstance(elt, ast.Tuple):
            continue
        if len(getattr(elt, "elts", [])) != 2:
            continue
        name_node, type_node = elt.elts
        if not (isinstance(name_node, ast.Constant) and isinstance(name_node.value, str)):
            continue
        if not (isinstance(type_node, ast.Constant) and isinstance(type_node.value, str)):
            continue
        pins.append((name_node.value.strip(), type_node.value.strip(), type_node))
    return pins


def _check_class_based_pin_markers_and_nesting(
    class_defs: List[ast.ClassDef],
    file_path: Path,
    *,
    default_level: str,
) -> List[EngineIssue]:
    issues: List[EngineIssue] = []
    for cls in class_defs:
        for item in cls.body:
            if not isinstance(item, ast.FunctionDef):
                continue

            decorator_names = [_decorator_name(d) for d in (item.decorator_list or [])]
            is_flow_entry = "flow_entry" in decorator_names
            is_event_handler = "event_handler" in decorator_names
            if not (is_flow_entry or is_event_handler):
                continue

            markers = collect_pin_markers(item)
            signature_inputs = infer_data_inputs_from_signature(item)
            overrides: Dict[str, str] = {m.name: m.pin_type for m in (markers.data_inputs or [])}

            # 计算 inputs/outputs：以 pin_marker 为权威来源；装饰器 inputs/outputs 仅作冗余声明（可选）
            effective_pins: List[Tuple[str, str, ast.AST]] = []

            for marker in (markers.flow_inputs or []):
                effective_pins.append((marker.name, marker.pin_type, item))

            handled_signature_inputs: set[str] = set()
            for marker in signature_inputs:
                effective_type = overrides.get(marker.name, marker.pin_type)
                effective_pins.append((marker.name, effective_type, item))
                handled_signature_inputs.add(marker.name)

            for marker in (markers.data_inputs or []):
                if marker.name not in handled_signature_inputs:
                    effective_pins.append((marker.name, marker.pin_type, item))

            flow_outputs: List[PinMarker] = list(markers.flow_outputs or [])
            if is_event_handler and not flow_outputs:
                flow_outputs = [PinMarker("流程出", "流程")]

            for marker in flow_outputs:
                effective_pins.append((marker.name, marker.pin_type, item))

            for marker in (markers.data_outputs or []):
                effective_pins.append((marker.name, marker.pin_type, item))

            for pin_name, pin_type, pin_node in effective_pins:
                if not _is_supported_pin_type(pin_type):
                    issues.append(
                        EngineIssue(
                            level=default_level,
                            category="复合节点",
                            code="COMPOSITE_PIN_TYPE_FORBIDDEN",
                            message=(
                                f"类格式复合节点 {cls.name}.{item.name} 的引脚'{pin_name}'使用了"
                                f"未受支持的类型标注'{pin_type}'，{_build_pin_type_suggestion(pin_type)}"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(pin_node),
                        )
                    )

    return issues


def _is_supported_pin_type(type_name: str) -> bool:
    type_name = type_name.strip()
    if not type_name:
        return False
    if type_name in BANNED_PIN_TYPES:
        return False
    if type_name in PYTHON_BUILTIN_PIN_TYPES:
        return False

    if type_name == TYPE_FLOW:
        return True
    # 别名字典：允许作为复合节点对外数据引脚类型（用于稳定表达 dict(K,V)）
    ok_alias, key_type, value_type = parse_typed_dict_alias(type_name)
    if ok_alias:
        # key/value 递归要求为“复合允许的数据引脚类型”（基础/列表/字典），但禁止占位型
        if key_type in {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT, TYPE_LIST_PLACEHOLDER}:
            return False
        if value_type in {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT, TYPE_LIST_PLACEHOLDER}:
            return False
        # 允许 value 为列表类型；是否允许 value 继续为别名字典由 parse_typed_dict_alias 递归表达决定。
        return _is_supported_pin_type(key_type) and _is_supported_pin_type(value_type)

    return type_name in ALLOWED_DATA_PIN_TYPES


def _build_pin_type_suggestion(type_name: str) -> str:
    base_suggestion = (
        "请改为受支持的中文类型（基础类型或列表类型，如'实体/整数/字符串/浮点数/三维向量/实体列表'等）。"
    )
    if type_name in BANNED_PIN_TYPES:
        return "不支持旧别名（通用/Any 等），请改为具体的中文端口类型。"
    if type_name in PYTHON_BUILTIN_PIN_TYPES:
        return (
            "不支持 Python 内置类型名，请使用对应中文端口类型（如：int→整数，float→浮点数，"
            "str→字符串，bool→布尔值，list→具体列表类型，dict→字典）。"
        )
    if type_name in {TYPE_GENERIC, TYPE_LIST_PLACEHOLDER, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT}:
        return "泛型/列表 仅作为“未设置”占位，必须选择具体类型后再保存/通过校验。"
    return base_suggestion
