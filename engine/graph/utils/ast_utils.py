"""AST工具函数

提供AST遍历、常量提取、格式检测等通用工具。
"""
from __future__ import annotations

import ast
from typing import Any, Optional


class _NotExtractable:
    """哨兵：表示无法静态提取常量值"""
    pass


NOT_EXTRACTABLE = _NotExtractable()


def extract_constant_value(value_node: ast.expr) -> Any:
    """从AST节点提取常量值
    
    支持的常量类型：
    - 数字（int, float）
    - 字符串（str）
    - 布尔值（True, False, None）
    - 列表字面量
    - 元组字面量
    - self.xxx 属性访问（返回字符串表示）
    
    无法提取的情况返回 NOT_EXTRACTABLE 哨兵值。
    
    Args:
        value_node: AST表达式节点
        
    Returns:
        提取的常量值，或 NOT_EXTRACTABLE
    """
    if isinstance(value_node, ast.Constant):
        return value_node.value
    
    # 处理旧 AST 节点类型
    if isinstance(value_node, ast.Str):
        return value_node.s
    if isinstance(value_node, ast.Num):
        return value_node.n
    if isinstance(value_node, ast.NameConstant):
        return value_node.value
    
    # 容器字面量
    if isinstance(value_node, ast.List):
        return [extract_constant_value(e) for e in value_node.elts]
    if isinstance(value_node, ast.Tuple):
        return tuple(extract_constant_value(e) for e in value_node.elts)
    
    # f-string无法静态提取
    if isinstance(value_node, ast.JoinedStr):
        return NOT_EXTRACTABLE
    
    # self.xxx 属性访问
    if isinstance(value_node, ast.Attribute):
        if isinstance(value_node.value, ast.Name) and value_node.value.id == 'self':
            return f"self.{value_node.attr}"
        return NOT_EXTRACTABLE
    
    # 变量引用无法静态提取
    if isinstance(value_node, ast.Name):
        return NOT_EXTRACTABLE
    
    return NOT_EXTRACTABLE


def is_class_structure_format(code: str) -> bool:
    """检测代码是否为类结构格式（事件方法格式）
    
    判定规则：
    1. 优先使用IR扫描器的严格判定（要求有__init__和至少一个on_*方法）
    2. 若IR扫描失败，使用宽松判定（存在on_*或register_handlers任一）
    
    Args:
        code: Python代码字符串
        
    Returns:
        True表示类结构格式，False表示其他格式
    """
    tree = ast.parse(code)
    
    # 严格判定（首选）：使用IR扫描器
    from engine.graph.ir.ast_scanner import find_graph_class
    if find_graph_class(tree) is not None:
        return True
    
    # 兼容：宽松判定
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_event_handler = False
            has_register = False
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name.startswith('on_'):
                        has_event_handler = True
                    if item.name == 'register_handlers':
                        has_register = True
            if has_event_handler or has_register:
                return True
    
    return False


def find_composite_function(tree: ast.Module) -> Optional[ast.FunctionDef]:
    """查找复合节点函数定义
    
    复合节点函数特征：
    - 第一个参数为 game: GameRuntime（或简写为 game）
    - 有返回类型标注（或无返回值）
    
    Args:
        tree: AST模块节点
        
    Returns:
        找到的函数定义，或None
    """
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            # 检查第一个参数是否为 game
            if node.args.args:
                first_arg = node.args.args[0]
                if first_arg.arg == 'game':
                    return node
    
    return None

