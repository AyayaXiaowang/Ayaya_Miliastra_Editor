from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set

from engine.nodes.port_type_system import ANY_PORT_TYPE, FLOW_PORT_TYPE, GENERIC_PORT_TYPE
from engine.type_registry import parse_typed_dict_alias


_CONST_TYPE_MAP: Dict[type, str] = {
    int: "整数",
    float: "浮点数",
    str: "字符串",
    bool: "布尔值",
}

_TYPE_CONVERSION_NODE_FUNC_NAME = "数据类型转换"


def iter_methods(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node, item


def iter_calls_to_nodes(method: ast.FunctionDef, func_names: Set[str]):
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        func = getattr(node, "func", None)
        if isinstance(func, ast.Name) and func.id in func_names:
            yield node


def collect_annotated_vars(method: ast.FunctionDef) -> Set[str]:
    annotated: Set[str] = set()
    for node in ast.walk(method):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = getattr(node, "target", None)
        ann = getattr(node, "annotation", None)
        if not isinstance(target, ast.Name):
            continue
        if isinstance(ann, ast.Constant) and isinstance(getattr(ann, "value", None), str):
            annotated.add(target.id)
    return annotated


def collect_var_types(
    method: ast.FunctionDef,
    func_names: Set[str],
    out_types: Dict[str, List[str]],
) -> Dict[str, str]:
    var_types: Dict[str, str] = {}
    # 入参注解：允许在方法签名处以中文类型字符串标注输入参数类型（复合节点入口常见）。
    # 例如：def 入口(self, 数值A: "浮点数", 数值B: "浮点数"): ...
    args = getattr(method, "args", None)
    if isinstance(args, ast.arguments):
        all_args: List[ast.arg] = [
            *list(getattr(args, "posonlyargs", []) or []),
            *list(getattr(args, "args", []) or []),
            *list(getattr(args, "kwonlyargs", []) or []),
        ]
        for one_arg in all_args:
            if not isinstance(one_arg, ast.arg):
                continue
            if one_arg.arg == "self":
                continue
            ann = getattr(one_arg, "annotation", None)
            if isinstance(ann, ast.Constant) and isinstance(getattr(ann, "value", None), str):
                var_types.setdefault(one_arg.arg, str(ann.value))
    # 注解优先：收集注解类型
    for node in ast.walk(method):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = getattr(node, "target", None)
        ann = getattr(node, "annotation", None)
        if not isinstance(target, ast.Name):
            continue
        if isinstance(ann, ast.Constant) and isinstance(getattr(ann, "value", None), str):
            var_types[target.id] = str(ann.value)
    # 赋值推断：单输出数据类型
    for node in ast.walk(method):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target_name = single_target_name(node.targets)
            if not target_name:
                continue
            f = node.value.func
            if isinstance(f, ast.Name) and (f.id in func_names):
                t = unique_data_output_type(out_types.get(f.id, []))
                if t and t not in (FLOW_PORT_TYPE, ""):
                    var_types.setdefault(target_name, t)
    return var_types


def single_target_name(targets: List[ast.expr]) -> Optional[str]:
    # 仅支持形如 x = ... 的简单赋值
    if len(targets) != 1:
        return None
    tgt = targets[0]
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None


def unique_data_output_type(types: List[str]) -> str:
    if not isinstance(types, list):
        return ""
    data_types = [t for t in types if isinstance(t, str) and t and (t != FLOW_PORT_TYPE)]
    if len(data_types) == 1:
        return data_types[0]
    return ""


def normalize_type(t: str) -> str:
    if not isinstance(t, str):
        return ""
    text = t.strip()
    if not text:
        return ""
    # 仅对“纯泛型”同义词做归一化，保留诸如“泛型字典”“泛型列表”等具象泛型类型
    if text in (GENERIC_PORT_TYPE, ANY_PORT_TYPE, "泛型"):
        return GENERIC_PORT_TYPE

    # 别名字典：统一将 “键_值字典” 规范化为 “键-值字典”，避免同义写法导致类型匹配误报
    is_typed_dict, key_type_name, value_type_name = parse_typed_dict_alias(text)
    if is_typed_dict:
        key_type_normalized = str(key_type_name or "").strip()
        value_type_normalized = str(value_type_name or "").strip()
        return f"{key_type_normalized}-{value_type_normalized}字典"
    return text


def is_type_allowed_by_constraints(actual: str, allowed: List[str]) -> bool:
    if not isinstance(actual, str):
        return False
    if not isinstance(allowed, list):
        return True
    if actual == GENERIC_PORT_TYPE:
        # 未推断出具体类型时，不在此处阻断，交给后续规则
        return True
    return actual in allowed


def extract_type_conversion_input_expr(call_expr: ast.Call) -> Optional[ast.expr]:
    """提取【数据类型转换】调用的“输入”表达式。

    支持形式：
    - 数据类型转换(game, 输入=...)
    - 数据类型转换(game, ...)

    说明：Graph Code 通常以关键字参数传端口名；这里额外对最常见的位置参数形式做弱支持。
    """
    # 1) 优先使用关键字参数：输入=...
    for keyword_arg in getattr(call_expr, "keywords", []) or []:
        if not isinstance(keyword_arg, ast.keyword):
            continue
        if keyword_arg.arg == "输入":
            return keyword_arg.value

    # 2) 兼容：数据类型转换(game, 输入值)
    positional_args = list(getattr(call_expr, "args", []) or [])
    if len(positional_args) >= 2:
        return positional_args[1]

    return None


def extract_call_port_expr(call_expr: ast.Call, *, port_name: str, positional_index: int) -> Optional[ast.expr]:
    """提取指定端口的实参表达式（优先关键字，其次位置参数）。"""
    for keyword_arg in getattr(call_expr, "keywords", []) or []:
        if not isinstance(keyword_arg, ast.keyword):
            continue
        if keyword_arg.arg == port_name:
            return keyword_arg.value
    positional_args = list(getattr(call_expr, "args", []) or [])
    if len(positional_args) > positional_index:
        return positional_args[positional_index]
    return None


def looks_like_game_expr(expr: ast.expr) -> bool:
    """启发式判断一个表达式是否为 Graph Code 约定的 game 实参。"""
    if isinstance(expr, ast.Name) and expr.id == "game":
        return True
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name) and expr.value.id == "self" and expr.attr == "game":
            return True
    return False

