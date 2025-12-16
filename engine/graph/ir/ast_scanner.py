from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional


# 语义 IR 基元：仅做轻量封装，保持对原始 AST 的可见性


@dataclass
class EventIR:
    name: str
    method_def: ast.FunctionDef


def find_graph_class(tree: ast.Module) -> Optional[ast.ClassDef]:
    """定位节点图类定义：必须同时包含 __init__ 与至少一个 on_ 开头的方法。"""
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            has_init = False
            has_event_handler = False
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == '__init__':
                        has_init = True
                    if item.name.startswith('on_'):
                        has_event_handler = True
            if has_init and has_event_handler:
                return node
    return None


def scan_event_methods(class_def: ast.ClassDef) -> List[EventIR]:
    """扫描类内所有事件处理器为 EventIR 列表。"""
    events: List[EventIR] = []
    for item in class_def.body:
        if isinstance(item, ast.FunctionDef) and item.name.startswith('on_'):
            events.append(EventIR(name=item.name[3:], method_def=item))
    return events


def scan_register_handlers_bindings(class_def: ast.ClassDef) -> Dict[str, str]:
    """扫描类内 register_handlers，提取 handler 方法名到事件字面量的映射。

    约定：
    - 仅处理形如 `self.game.register_event_handler("<literal>", self.on_<处理器>, ...)`；
    - 返回映射的 key 为 `<处理器>`（去掉 on_ 前缀），value 为 `<literal>` 原始文本。
    """
    register_func: Optional[ast.FunctionDef] = None
    for item in class_def.body:
        if isinstance(item, ast.FunctionDef) and item.name == "register_handlers":
            register_func = item
            break
    if register_func is None:
        return {}

    mapping: Dict[str, str] = {}
    for stmt in register_func.body or []:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            func_expr = node.func
            if not isinstance(func_expr, ast.Attribute):
                continue
            if func_expr.attr != "register_event_handler":
                continue

            args = list(node.args or [])
            if len(args) < 2:
                continue
            event_name_node = args[0]
            handler_node = args[1]

            if not isinstance(event_name_node, ast.Constant) or not isinstance(event_name_node.value, str):
                continue
            literal = str(event_name_node.value).strip()
            if not literal:
                continue

            if not (
                isinstance(handler_node, ast.Attribute)
                and isinstance(handler_node.value, ast.Name)
                and handler_node.value.id == "self"
                and isinstance(handler_node.attr, str)
                and handler_node.attr.startswith("on_")
            ):
                continue

            method_base_name = handler_node.attr[3:]
            if not method_base_name:
                continue

            mapping[method_base_name] = literal

    return mapping


def scan_method_body(stmt_list: List[ast.stmt]) -> List[ast.stmt]:
    """语句级 IR：当前直接返回 AST 语句序列，供后续流程建模模块消费。"""
    return list(stmt_list or [])



