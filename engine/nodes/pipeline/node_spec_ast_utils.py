from __future__ import annotations

import ast
from typing import Optional

__all__ = [
    "is_node_spec_decorator",
    "find_node_spec_decorator_call",
    "get_call_kw_str",
]


def is_node_spec_decorator(decorator_node: ast.AST) -> bool:
    """判断装饰器节点是否为 @node_spec（支持 Name/Attribute/Call 形态）。"""
    if isinstance(decorator_node, ast.Call):
        func = decorator_node.func
        if isinstance(func, ast.Name):
            return func.id == "node_spec"
        if isinstance(func, ast.Attribute):
            return func.attr == "node_spec"
    if isinstance(decorator_node, ast.Name):
        return decorator_node.id == "node_spec"
    if isinstance(decorator_node, ast.Attribute):
        return decorator_node.attr == "node_spec"
    return False


def find_node_spec_decorator_call(function_def: ast.FunctionDef) -> Optional[ast.Call]:
    """返回函数上匹配到的 @node_spec(...) 装饰器调用（若装饰器不是 Call 则返回 None）。"""
    for decorator_node in function_def.decorator_list:
        if not is_node_spec_decorator(decorator_node):
            continue
        return decorator_node if isinstance(decorator_node, ast.Call) else None
    return None


def get_call_kw_str(call_node: ast.Call, key: str) -> Optional[str]:
    """从形如 func(..., key=\"value\") 的调用中读取指定关键字参数（仅支持字符串常量）。"""
    for keyword in call_node.keywords:
        if keyword.arg != key:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


