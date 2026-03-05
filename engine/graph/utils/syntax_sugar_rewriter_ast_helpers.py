from __future__ import annotations

import copy
import ast
from typing import Dict, List, Optional, Set, Tuple


def _iter_class_defs(tree: ast.Module) -> List[ast.ClassDef]:
    class_defs: List[ast.ClassDef] = []
    for node in list(getattr(tree, "body", []) or []):
        if isinstance(node, ast.ClassDef):
            class_defs.append(node)
    return class_defs


def _iter_method_defs(class_def: ast.ClassDef) -> List[ast.FunctionDef]:
    methods: List[ast.FunctionDef] = []
    for item in list(getattr(class_def, "body", []) or []):
        if isinstance(item, ast.FunctionDef):
            methods.append(item)
    return methods


def _build_self_game_expr() -> ast.expr:
    return ast.Attribute(
        value=ast.Name(id="self", ctx=ast.Load()),
        attr="game",
        ctx=ast.Load(),
    )


def _build_positive_mod_expr(
    numerator_expr: ast.expr,
    modulus_expr: ast.expr,
    *,
    source_node: ast.AST,
) -> ast.Call:
    """构建“正模”表达式：保证输出在 [0, 模数-1]。

    背景：部分运行环境对负数的 `%` / mod 可能返回“负余数”（C 风格），导致循环索引等逻辑异常。
    我们用等价的“修正余数”模板实现正模：
        ((a % m) + m) % m

    注意：
    - 该 helper 直接输出“节点调用形态”（模运算/加法运算/模运算），供语法糖改写器在 server 作用域使用；
    - modulus_expr 会被复制多份，避免生成“同一 AST 节点多父节点引用”的非树结构。
    """

    modulus_expr_1 = copy.deepcopy(modulus_expr)
    modulus_expr_2 = copy.deepcopy(modulus_expr)
    modulus_expr_3 = copy.deepcopy(modulus_expr)

    raw_mod_call = ast.Call(
        func=ast.Name(id="模运算", ctx=ast.Load()),
        args=[_build_self_game_expr()],
        keywords=[
            ast.keyword(arg="被模数", value=numerator_expr),
            ast.keyword(arg="模数", value=modulus_expr_1),
        ],
    )

    add_call = ast.Call(
        func=ast.Name(id="加法运算", ctx=ast.Load()),
        args=[_build_self_game_expr()],
        keywords=[
            ast.keyword(arg="左值", value=raw_mod_call),
            ast.keyword(arg="右值", value=modulus_expr_2),
        ],
    )

    positive_mod_call = ast.Call(
        func=ast.Name(id="模运算", ctx=ast.Load()),
        args=[_build_self_game_expr()],
        keywords=[
            ast.keyword(arg="被模数", value=add_call),
            ast.keyword(arg="模数", value=modulus_expr_3),
        ],
    )

    # 位置与行号：让后续报错/定位仍指向原始表达式位置
    for created in (raw_mod_call, add_call, positive_mod_call):
        ast.copy_location(created, source_node)
        created.end_lineno = getattr(source_node, "end_lineno", getattr(created, "lineno", None))

    # 标记：避免后续可能新增的“模运算 call 级语法糖”对该结构重复套娃
    setattr(positive_mod_call, "_syntax_sugar_positive_mod_rewritten", True)
    setattr(add_call, "_syntax_sugar_positive_mod_rewritten", True)
    setattr(raw_mod_call, "_syntax_sugar_positive_mod_rewritten", True)

    return positive_mod_call


def _extract_subscript_index_expr(node: ast.Subscript) -> Optional[ast.expr]:
    slice_node = getattr(node, "slice", None)
    if isinstance(slice_node, ast.Slice):
        return None
    if isinstance(slice_node, ast.Tuple):
        return None
    if isinstance(slice_node, ast.expr):
        return slice_node
    return None


def _collect_container_var_names(method_def: ast.FunctionDef) -> Tuple[Set[str], Set[str]]:
    """收集方法体内“显式声明”的列表/字典变量名集合。

    说明：
    - 优先使用中文类型注解（AnnAssign），避免把任意 `x = ...` 误判为容器；
    - 兼容从 `拼装列表/拼装字典` 直接赋值的写法（可能无显式注解）。
    """
    list_var_names: Set[str] = set()
    dict_var_names: Set[str] = set()

    for node in ast.walk(method_def):
        if isinstance(node, ast.AnnAssign):
            target = getattr(node, "target", None)
            annotation = getattr(node, "annotation", None)
            if not isinstance(target, ast.Name):
                continue
            if not (isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str)):
                continue
            type_text = str(annotation.value).strip()
            if type_text.endswith("列表"):
                list_var_names.add(target.id)
            elif type_text.endswith("字典"):
                dict_var_names.add(target.id)
            continue

        if isinstance(node, ast.Assign):
            targets = list(getattr(node, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            target_name = targets[0].id
            value_expr = getattr(node, "value", None)

            # 兼容“尚未重写字面量”的场景
            if isinstance(value_expr, ast.List):
                list_var_names.add(target_name)
                continue
            if isinstance(value_expr, ast.Dict):
                dict_var_names.add(target_name)
                continue

            if not isinstance(value_expr, ast.Call):
                continue
            call_func = getattr(value_expr, "func", None)
            if not isinstance(call_func, ast.Name):
                continue
            call_name = call_func.id
            if call_name == "拼装列表":
                list_var_names.add(target_name)
            elif call_name == "拼装字典":
                dict_var_names.add(target_name)

    return list_var_names, dict_var_names


def _collect_list_var_type_by_name(method_def: ast.FunctionDef) -> Dict[str, str]:
    """收集方法体内显式声明的“列表变量类型”：{变量名: 'X列表'}。

    目的：为 enumerate(...) 语法糖改写提供稳定的元素类型推断来源，避免生成泛型输出导致端口类型校验漂移。
    """
    mapping: Dict[str, str] = {}
    for node in ast.walk(method_def):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = getattr(node, "target", None)
        annotation = getattr(node, "annotation", None)
        if not isinstance(target, ast.Name):
            continue
        if not (isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str)):
            continue
        type_text = str(annotation.value).strip()
        if type_text.endswith("列表"):
            mapping[target.id] = type_text
    return mapping


def _collect_var_type_by_name(method_def: ast.FunctionDef) -> Dict[str, str]:
    """收集方法体内显式声明的变量中文类型注解：{变量名: '类型文本'}。

    说明：
    - 仅收集 `AnnAssign` 且注解为字符串常量（例如：`x: "整数" = ...`）；
    - 用于语法糖归一化时的“类型定向改写”（例如三维向量运算符、not 等），避免做不可靠的推断。
    """
    mapping: Dict[str, str] = {}
    for node in ast.walk(method_def):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = getattr(node, "target", None)
        annotation = getattr(node, "annotation", None)
        if not isinstance(target, ast.Name):
            continue
        if not (isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str)):
            continue
        type_text = str(annotation.value).strip()
        if type_text:
            mapping[target.id] = type_text
    return mapping


def _collect_all_name_ids(node: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(getattr(sub, "id", None), str):
            if sub.id:
                names.add(sub.id)
    return names


def _is_dict_var_name(name: str, dict_var_names: Set[str]) -> bool:
    return str(name or "") in (dict_var_names or set())


