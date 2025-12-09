from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text
from engine.nodes.node_registry import get_node_registry
from engine.configs.rules.datatype_rules import BASE_TYPES, LIST_TYPES


BANNED_PIN_TYPES: Set[str] = {"通用", "Any", "any", "ANY"}
ALLOWED_DATA_PIN_TYPES: Set[str] = set(BASE_TYPES.keys()) | set(LIST_TYPES.keys()) | {"字典"}


class CompositeTypesAndNestingRule(ValidationRule):
    """复合节点：参数/返回中文类型、流程入必填、禁止复合嵌套"""

    rule_id = "engine_composite_types_and_nesting"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if not ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        # 先处理类格式复合节点（@composite_class）
        composite_classes = _find_composite_classes(tree)
        if composite_classes:
            issues.extend(_check_class_based_pin_types(composite_classes, file_path))

        # 建立复合节点名称集合（用于嵌套检测）
        registry = get_node_registry(ctx.workspace_path, include_composite=True)
        lib = registry.get_library()
        composite_names: Set[str] = {nd.name for _, nd in lib.items() if getattr(nd, "is_composite", False)}

        # 找到顶层可导出函数（按常规：文件内第一个顶层 FunctionDef）
        comp_func = _find_top_level_function(tree)
        if comp_func is None:
            return issues

        # 1) 参数/返回类型：必须为中文字符串注解
        for arg in (comp_func.args.args or []):
            if arg.arg == "game":
                # 运行时对象，不强制中文注解
                continue
            ann = getattr(arg, "annotation", None)
            if not (isinstance(ann, ast.Constant) and isinstance(getattr(ann, "value", None), str)):
                issues.append(EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="COMPOSITE_ARG_CHINESE_TYPE_REQUIRED",
                    message=f"参数 '{arg.arg}' 需要中文字符串类型注解（例如：\"实体\"、\"整数列表\"）",
                    file=str(file_path),
                    line_span=line_span_text(arg) if ann is not None else None,
                ))
        # 返回类型：要求存在且为中文字符串
        ret = getattr(comp_func, "returns", None)
        if not (isinstance(ret, ast.Constant) and isinstance(getattr(ret, "value", None), str)):
            issues.append(EngineIssue(
                level=self.default_level,
                category=self.category,
                code="COMPOSITE_RETURN_CHINESE_TYPE_REQUIRED",
                message="复合节点函数需要中文字符串返回类型注解（例如：\"流程\" 或具体数据类型）",
                file=str(file_path),
                line_span=line_span_text(comp_func) if ret is not None else None,
            ))

        # 2) 流程入声明必填：要求存在名为"流程入"的参数且注解为"流程"
        flow_in_ok = False
        for arg in (comp_func.args.args or []):
            if arg.arg == "流程入":
                ann = getattr(arg, "annotation", None)
                if isinstance(ann, ast.Constant) and (getattr(ann, "value", None) == "流程"):
                    flow_in_ok = True
                break
        if not flow_in_ok:
            issues.append(EngineIssue(
                level=self.default_level,
                category=self.category,
                code="COMPOSITE_FLOW_IN_REQUIRED",
                message="复合节点必须声明参数『流程入: \"流程\"』以表明流程入口",
                file=str(file_path),
                line_span=line_span_text(comp_func),
            ))

        # 3) 禁止复合嵌套：函数体内不允许直接调用其他复合节点
        for node in ast.walk(comp_func):
            if isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name):
                fname = node.func.id
                if fname in composite_names:
                    issues.append(EngineIssue(
                        level=self.default_level,
                        category=self.category,
                        code="COMPOSITE_NESTING_FORBIDDEN",
                        message=f"{line_span_text(node)}: 禁止在复合节点内部调用其他复合节点 '{fname}'",
                        file=str(file_path),
                        line_span=line_span_text(node),
                    ))

        return issues


def _find_top_level_function(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def _find_composite_classes(tree: ast.Module) -> List[ast.ClassDef]:
    classes: List[ast.ClassDef] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for deco in node.decorator_list:
                if _decorator_name(deco) == "composite_class":
                    classes.append(node)
                    break
    return classes


def _decorator_name(decorator: ast.AST) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return ""


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


def _check_class_based_pin_types(class_defs: List[ast.ClassDef], file_path: Path) -> List[EngineIssue]:
    issues: List[EngineIssue] = []
    for cls in class_defs:
        for item in cls.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            for decorator in item.decorator_list:
                deco_name = _decorator_name(decorator)
                if deco_name not in {"flow_entry", "event_handler"}:
                    continue
                if not isinstance(decorator, ast.Call):
                    continue
                pin_defs: List[Tuple[str, str, ast.AST]] = []
                pin_defs.extend(_extract_pin_defs(decorator, "inputs"))
                pin_defs.extend(_extract_pin_defs(decorator, "outputs"))
                for pin_name, pin_type, pin_node in pin_defs:
                    if not _is_supported_pin_type(pin_type):
                        suggestion = (
                            "请改为受支持的中文类型（基础类型或列表类型，"
                            "如'实体/整数/字符串/浮点数/三维向量/实体列表'等）。"
                        )
                        if pin_type in {"列表", "泛型列表"}:
                            suggestion = "列表类型需写成具体列表（如'整数列表/实体列表/字符串列表/三维向量列表'）。"
                        elif pin_type == "泛型":
                            suggestion = "泛型不支持，请改为具体的基础类型或具体列表类型。"
                        elif pin_type in BANNED_PIN_TYPES:
                            suggestion = "不支持该类型标注，请改为具体的基础类型或列表类型。"
                        issues.append(
                            EngineIssue(
                                level="error",
                                category="复合节点",
                                code="COMPOSITE_PIN_TYPE_FORBIDDEN",
                                message=(
                                    f"类格式复合节点 {cls.name}.{item.name} 的引脚'{pin_name}'使用了"
                                    f"未受支持的类型标注'{pin_type}'，{suggestion}"
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

    if type_name == "流程":
        return True

    return type_name in ALLOWED_DATA_PIN_TYPES
