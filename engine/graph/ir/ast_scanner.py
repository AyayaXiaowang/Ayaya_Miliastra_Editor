from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional


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


def scan_method_body(stmt_list: List[ast.stmt]) -> List[ast.stmt]:
    """语句级 IR：当前直接返回 AST 语句序列，供后续流程建模模块消费。"""
    return list(stmt_list or [])



