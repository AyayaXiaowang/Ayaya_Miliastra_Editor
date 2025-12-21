"""AST工具函数

提供AST遍历、常量提取、格式检测等通用工具。
"""
from __future__ import annotations

import ast
import threading
from typing import Any, Dict, Optional


class _NotExtractable:
    """哨兵：表示无法静态提取常量值"""
    pass


NOT_EXTRACTABLE = _NotExtractable()


# ============================================================================
# 模块级常量上下文（线程安全）
# ============================================================================

_module_constants_context = threading.local()


def set_module_constants_context(constants: Dict[str, Any]) -> None:
    """设置当前解析上下文的模块级常量映射
    
    Args:
        constants: 常量名 -> 常量值 的映射
    """
    _module_constants_context.constants = constants


def clear_module_constants_context() -> None:
    """清除当前解析上下文的模块级常量映射"""
    _module_constants_context.constants = None


def get_module_constants_context() -> Optional[Dict[str, Any]]:
    """获取当前解析上下文的模块级常量映射"""
    return getattr(_module_constants_context, 'constants', None)


def collect_module_constants(tree: ast.Module) -> Dict[str, Any]:
    """从 AST 模块中收集模块级常量定义
    
    识别形如以下的顶层赋值语句：
    - `关卡实体GUID常量: "GUID" = "1094713345"`  (带类型注解)
    - `MY_CONSTANT = 42`  (普通赋值)
    
    只收集值为字面量（可静态提取）的常量。
    
    Args:
        tree: AST 模块节点
        
    Returns:
        常量名 -> 常量值 的映射
    """
    constants: Dict[str, Any] = {}
    
    for stmt in tree.body:
        # 带类型标注的赋值（AnnAssign）
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                var_name = stmt.target.id
                # 递归提取值（不使用上下文，避免循环）
                const_val = _extract_constant_value_raw(stmt.value)
                if const_val is not NOT_EXTRACTABLE:
                    constants[var_name] = const_val
        
        # 普通赋值（Assign）
        elif isinstance(stmt, ast.Assign):
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                var_name = stmt.targets[0].id
                const_val = _extract_constant_value_raw(stmt.value)
                if const_val is not NOT_EXTRACTABLE:
                    constants[var_name] = const_val
    
    return constants


def _extract_constant_value_raw(value_node: ast.expr) -> Any:
    """从 AST 节点提取常量值（不查找模块常量上下文，用于收集常量定义本身）"""
    # 标准常量
    if isinstance(value_node, ast.Constant):
        return value_node.value
    
    # 一元 +/- 运算
    if isinstance(value_node, ast.UnaryOp):
        if isinstance(value_node.op, ast.USub):
            inner_value = _extract_constant_value_raw(value_node.operand)
            if isinstance(inner_value, (int, float)) and not isinstance(inner_value, bool):
                return -inner_value
            return NOT_EXTRACTABLE
        if isinstance(value_node.op, ast.UAdd):
            inner_value = _extract_constant_value_raw(value_node.operand)
            if isinstance(inner_value, (int, float)) and not isinstance(inner_value, bool):
                return +inner_value
            return NOT_EXTRACTABLE
    
    # 容器字面量
    if isinstance(value_node, ast.List):
        return [_extract_constant_value_raw(element) for element in value_node.elts]
    if isinstance(value_node, ast.Tuple):
        return tuple(_extract_constant_value_raw(element) for element in value_node.elts)
    
    return NOT_EXTRACTABLE


def extract_constant_value(value_node: ast.expr) -> Any:
    """从 AST 节点提取"静态可解析"的常量值。
    
    支持的形式（统一供 IR 与复合节点等场景复用）：
    - 标准常量：int / float / str / bool / None（ast.Constant）
    - 一元运算：数值前的一元正负号（+/-Constant）
    - 容器字面量：list / tuple（元素递归调用本函数）
    - self.<字段> 访问：
      - self.owner_entity：返回字符串 "self.owner_entity"，由上层按"图所属实体"语义处理；
      - self._xxx：视为运行期状态字段，统一返回 NOT_EXTRACTABLE；
      - 其他公开字段：返回 "self.<字段名>" 字符串，供上层按需处理。
    - 模块级常量引用：若当前上下文中设置了模块常量映射，变量名会被解析为对应的常量值
    
    无法提取的情况返回 NOT_EXTRACTABLE 哨兵值。
    """
    # 标准常量
    if isinstance(value_node, ast.Constant):
        return value_node.value
    
    # 一元 +/- 运算（主要用于 -1 / +1 / -1.0 等写法）
    if isinstance(value_node, ast.UnaryOp):
        if isinstance(value_node.op, ast.USub):
            inner_value = extract_constant_value(value_node.operand)
            if isinstance(inner_value, (int, float)) and not isinstance(inner_value, bool):
                return -inner_value
            return NOT_EXTRACTABLE
        if isinstance(value_node.op, ast.UAdd):
            inner_value = extract_constant_value(value_node.operand)
            if isinstance(inner_value, (int, float)) and not isinstance(inner_value, bool):
                return +inner_value
            return NOT_EXTRACTABLE
    
    # 容器字面量
    if isinstance(value_node, ast.List):
        return [extract_constant_value(element) for element in value_node.elts]
    if isinstance(value_node, ast.Tuple):
        return tuple(extract_constant_value(element) for element in value_node.elts)
    
    # f-string 无法静态提取
    if isinstance(value_node, ast.JoinedStr):
        return NOT_EXTRACTABLE
    
    # self.xxx 属性访问
    if isinstance(value_node, ast.Attribute):
        if isinstance(value_node.value, ast.Name) and value_node.value.id == "self":
            attribute_name = value_node.attr
            if attribute_name == "owner_entity":
                return f"self.{attribute_name}"
            if attribute_name.startswith("_"):
                # 私有字段通常代表运行期状态（不可静态提取）。
                # 但节点图类中常见“类常量”写法：在 class body 顶层定义 `_xxx = "常量"`，
                # 然后在方法体内通过 `self._xxx` 传给节点入参（例如 定时器名称）。
                # 解析阶段若已将该类常量写入模块常量上下文（key: "self._xxx"），则允许静态提取。
                module_constants = get_module_constants_context()
                if module_constants is not None:
                    self_key = f"self.{attribute_name}"
                    if self_key in module_constants:
                        return module_constants[self_key]
                return NOT_EXTRACTABLE
            return f"self.{attribute_name}"
        return NOT_EXTRACTABLE
    
    # 普通变量引用：检查是否是模块级常量
    if isinstance(value_node, ast.Name):
        var_name = value_node.id
        module_constants = get_module_constants_context()
        if module_constants is not None and var_name in module_constants:
            return module_constants[var_name]
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

