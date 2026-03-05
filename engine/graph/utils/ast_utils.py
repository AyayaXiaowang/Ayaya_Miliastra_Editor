"""AST工具函数

提供AST遍历、常量提取、格式检测等通用工具。
"""
from __future__ import annotations

import ast
import threading
from typing import Any, Dict, Optional

from engine.type_registry import (
    BASE_TYPES,
    LIST_TYPES,
    TYPE_DICT,
    TYPE_FLOW,
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    TYPE_LIST_PLACEHOLDER,
    parse_typed_dict_alias,
)

class _NotExtractable:
    """哨兵：表示无法静态提取常量值"""
    pass


NOT_EXTRACTABLE = _NotExtractable()


def _is_hashable_constant_key(value: Any) -> bool:
    """判断 dict 常量键是否为“可安全构造”的可哈希值。

    说明：
    - 为避免在常量提取阶段因 `dict[key] = value` 触发 TypeError 而中断解析，
      这里仅允许项目中常见的可哈希常量类型作为键。
    - 不使用 try/except：不满足条件直接返回 False（上层会返回 NOT_EXTRACTABLE）。
    """
    if value is None:
        return True
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, tuple):
        return all(_is_hashable_constant_key(item) for item in value)
    return False


# ============================================================================
# 模块级常量上下文（线程安全）
# ============================================================================

_module_constants_context = threading.local()
_module_constant_types_context = threading.local()


def _get_or_init_stack(container: threading.local, attr_name: str) -> list[dict]:
    existing = getattr(container, attr_name, None)
    if existing is None:
        stack: list[dict] = []
        setattr(container, attr_name, stack)
        return stack
    if isinstance(existing, list):
        return existing
    # 兼容历史：若外部误写入了非 list 的值，直接覆盖为新栈（不吞错、不 try/except）
    stack = []
    setattr(container, attr_name, stack)
    return stack


def set_module_constants_context(constants: Dict[str, Any]) -> None:
    """设置当前解析上下文的模块级常量映射
    
    Args:
        constants: 常量名 -> 常量值 的映射
    """
    # 重要：使用“栈式上下文”以支持嵌套解析：
    # - GraphCodeParser 在解析节点图时会在同一线程内调用信号/结构体/关卡变量等 schema 视图；
    # - 这些 schema 载入同样会临时设置模块常量上下文；
    # - 若仅使用单一全局槽位，内层 clear 会把外层上下文清空，导致外层 AST 常量无法回填到 input_constants，
    #   strict 结构校验会误报“缺少数据来源”。
    stack = _get_or_init_stack(_module_constants_context, "stack")
    stack.append(dict(constants))


def set_module_constant_types_context(type_map: Dict[str, str]) -> None:
    """设置当前解析上下文的模块级常量类型映射。

    约定：type_map 的 value 必须是“源码中的显式类型注解文本”（中文端口类型）。
    """
    stack = _get_or_init_stack(_module_constant_types_context, "stack")
    stack.append(dict(type_map))


def clear_module_constants_context() -> None:
    """清除当前解析上下文的模块级常量映射"""
    stack = _get_or_init_stack(_module_constants_context, "stack")
    if stack:
        stack.pop()


def clear_module_constant_types_context() -> None:
    """清除当前解析上下文的模块级常量类型映射。"""
    stack = _get_or_init_stack(_module_constant_types_context, "stack")
    if stack:
        stack.pop()


def get_module_constants_context() -> Optional[Dict[str, Any]]:
    """获取当前解析上下文的模块级常量映射"""
    stack = _get_or_init_stack(_module_constants_context, "stack")
    return stack[-1] if stack else None


def get_module_constant_types_context() -> Optional[Dict[str, str]]:
    """获取当前解析上下文的模块级常量类型映射。"""
    stack = _get_or_init_stack(_module_constant_types_context, "stack")
    return stack[-1] if stack else None


def _is_concrete_port_type_text(type_text: object) -> bool:
    text = str(type_text or "").strip()
    if text == "":
        return False
    if text in {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT, TYPE_LIST_PLACEHOLDER, TYPE_DICT, TYPE_FLOW}:
        return False
    if text in BASE_TYPES:
        return True
    if text in LIST_TYPES:
        return True
    is_alias, key_type, value_type = parse_typed_dict_alias(text)
    if not is_alias:
        return False
    return _is_concrete_port_type_text(key_type) and _is_concrete_port_type_text(value_type)


def collect_module_constant_types(tree: ast.Module) -> Dict[str, str]:
    """收集模块顶层“命名常量”的显式类型注解。

    仅收集可静态提取值且类型为“具体类型”的声明，示例：
    - `常量A: "整数列表" = [1, 2, 3]`
    - `常量B: "整数-整数字典" = {1: 10, 2: 20}`
    """
    result: Dict[str, str] = {}
    for stmt in list(getattr(tree, "body", []) or []):
        if not isinstance(stmt, ast.AnnAssign):
            continue
        target = getattr(stmt, "target", None)
        annotation = getattr(stmt, "annotation", None)
        value_node = getattr(stmt, "value", None)
        if not isinstance(target, ast.Name):
            continue
        if not isinstance(annotation, ast.Constant) or not isinstance(getattr(annotation, "value", None), str):
            continue
        if value_node is None:
            continue

        annotation_text = str(annotation.value or "").strip()
        if not _is_concrete_port_type_text(annotation_text):
            continue
        if _extract_constant_value_raw(value_node) is NOT_EXTRACTABLE:
            continue
        result[target.id] = annotation_text
    return result


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
    # 1) 收集模块顶层“单目标赋值”的 RHS 表达式（按出现顺序，后者覆盖前者）
    expr_by_name: Dict[str, ast.expr] = {}
    for stmt in getattr(tree, "body", []) or []:
        # 带类型标注的赋值（AnnAssign）
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(getattr(stmt, "target", None), ast.Name) and isinstance(getattr(stmt, "value", None), ast.expr):
                expr_by_name[stmt.target.id] = stmt.value
            continue

        # 普通赋值（Assign）
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) == 1 and isinstance(targets[0], ast.Name) and isinstance(getattr(stmt, "value", None), ast.expr):
                expr_by_name[targets[0].id] = stmt.value
            continue

    # 2) 解析：支持“字面量/容器字面量”以及“引用其他模块常量”的别名链（例如 POS_X = ZERO_FLOAT）
    resolved: Dict[str, Any] = {}
    resolving: set[str] = set()

    def _resolve_expr(expr: ast.expr) -> Any:
        raw = _extract_constant_value_raw(expr)
        if raw is not NOT_EXTRACTABLE:
            return raw

        # 变量引用：支持模块级常量别名
        if isinstance(expr, ast.Name):
            return _resolve_name(expr.id)

        # 一元 +/-：支持对模块级常量做一元正负号
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
            operand = getattr(expr, "operand", None)
            if isinstance(operand, ast.expr):
                inner = _resolve_expr(operand)
                if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                    if isinstance(expr.op, ast.USub):
                        return -inner
                    return +inner
            return NOT_EXTRACTABLE

        # 容器字面量：允许元素引用模块级常量（如 LIST = [A, B]）
        if isinstance(expr, ast.List):
            items: list[Any] = []
            for element in list(getattr(expr, "elts", []) or []):
                if not isinstance(element, ast.expr):
                    return NOT_EXTRACTABLE
                extracted = _resolve_expr(element)
                if extracted is NOT_EXTRACTABLE:
                    return NOT_EXTRACTABLE
                items.append(extracted)
            return items
        if isinstance(expr, ast.Tuple):
            items: list[Any] = []
            for element in list(getattr(expr, "elts", []) or []):
                if not isinstance(element, ast.expr):
                    return NOT_EXTRACTABLE
                extracted = _resolve_expr(element)
                if extracted is NOT_EXTRACTABLE:
                    return NOT_EXTRACTABLE
                items.append(extracted)
            return tuple(items)
        if isinstance(expr, ast.Dict):
            keys = list(getattr(expr, "keys", []) or [])
            values = list(getattr(expr, "values", []) or [])
            if len(keys) != len(values):
                return NOT_EXTRACTABLE
            result: Dict[Any, Any] = {}
            for k_node, v_node in zip(keys, values):
                if (k_node is None) or (v_node is None):
                    return NOT_EXTRACTABLE
                if not isinstance(k_node, ast.expr) or not isinstance(v_node, ast.expr):
                    return NOT_EXTRACTABLE
                k_val = _resolve_expr(k_node)
                if k_val is NOT_EXTRACTABLE:
                    return NOT_EXTRACTABLE
                if not _is_hashable_constant_key(k_val):
                    return NOT_EXTRACTABLE
                v_val = _resolve_expr(v_node)
                if v_val is NOT_EXTRACTABLE:
                    return NOT_EXTRACTABLE
                result[k_val] = v_val
            return result

        return NOT_EXTRACTABLE

    def _resolve_name(name: str) -> Any:
        if name in resolved:
            return resolved[name]
        if name in resolving:
            return NOT_EXTRACTABLE
        expr = expr_by_name.get(name)
        if expr is None:
            return NOT_EXTRACTABLE
        resolving.add(name)
        val = _resolve_expr(expr)
        resolving.remove(name)
        if val is not NOT_EXTRACTABLE:
            resolved[name] = val
        return val

    for name in list(expr_by_name.keys()):
        _resolve_name(name)

    return dict(resolved)


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
        items: list[Any] = []
        for element in value_node.elts:
            extracted = _extract_constant_value_raw(element)
            if extracted is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            items.append(extracted)
        return items
    if isinstance(value_node, ast.Tuple):
        items: list[Any] = []
        for element in value_node.elts:
            extracted = _extract_constant_value_raw(element)
            if extracted is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            items.append(extracted)
        return tuple(items)
    if isinstance(value_node, ast.Dict):
        keys = list(getattr(value_node, "keys", []) or [])
        values = list(getattr(value_node, "values", []) or [])
        if len(keys) != len(values):
            return NOT_EXTRACTABLE
        result: Dict[Any, Any] = {}
        for key_node, value_node_item in zip(keys, values):
            if key_node is None or value_node_item is None:
                return NOT_EXTRACTABLE
            key_value = _extract_constant_value_raw(key_node)
            if key_value is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            if not _is_hashable_constant_key(key_value):
                return NOT_EXTRACTABLE
            value_value = _extract_constant_value_raw(value_node_item)
            if value_value is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            result[key_value] = value_value
        return result
    
    return NOT_EXTRACTABLE


def extract_constant_value(value_node: ast.expr) -> Any:
    """从 AST 节点提取"静态可解析"的常量值。
    
    支持的形式（统一供 IR 与复合节点等场景复用）：
    - 标准常量：int / float / str / bool / None（ast.Constant）
    - 一元运算：数值前的一元正负号（+/-Constant）
    - 容器字面量：list / tuple / dict（元素/键值递归调用本函数；任一子项不可提取则整体视为不可提取）
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
        items: list[Any] = []
        for element in value_node.elts:
            extracted = extract_constant_value(element)
            if extracted is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            items.append(extracted)
        return items
    if isinstance(value_node, ast.Tuple):
        items: list[Any] = []
        for element in value_node.elts:
            extracted = extract_constant_value(element)
            if extracted is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            items.append(extracted)
        return tuple(items)
    if isinstance(value_node, ast.Dict):
        # `{**d}` 在 AST 中会以 key=None 表示，统一视为不可静态提取
        keys = list(getattr(value_node, "keys", []) or [])
        values = list(getattr(value_node, "values", []) or [])
        if len(keys) != len(values):
            return NOT_EXTRACTABLE
        result: Dict[Any, Any] = {}
        for key_node, value_node_item in zip(keys, values):
            if key_node is None or value_node_item is None:
                return NOT_EXTRACTABLE
            key_value = extract_constant_value(key_node)
            if key_value is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            if not _is_hashable_constant_key(key_value):
                return NOT_EXTRACTABLE
            value_value = extract_constant_value(value_node_item)
            if value_value is NOT_EXTRACTABLE:
                return NOT_EXTRACTABLE
            result[key_value] = value_value
        return result
    
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

