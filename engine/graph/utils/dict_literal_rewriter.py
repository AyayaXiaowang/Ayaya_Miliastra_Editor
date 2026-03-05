from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .graph_code_rewrite_config import DEFAULT_MAX_DICT_LITERAL_PAIRS
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


BUILD_DICT_NODE_CALL_NAME = "拼装字典"


@dataclass(frozen=True)
class DictLiteralRewriteIssue:
    """字典字面量重写过程中的问题。

    约定：
    - issue.node 必须是可定位行号的 AST 节点（通常就是 ast.Dict）；
    - 不做 try/except：若 AST 结构异常直接抛出。
    """

    code: str
    message: str
    node: ast.AST


def rewrite_graph_code_dict_literals(
    tree: ast.Module,
    *,
    max_pairs: int = DEFAULT_MAX_DICT_LITERAL_PAIRS,
) -> Tuple[ast.Module, List[DictLiteralRewriteIssue]]:
    """将 Graph Code 中“类方法体”出现的字典字面量改写为【拼装字典】节点调用。

    改写能力：
    - `映射: "字符串-整数字典" = {k: v}` → `映射: "字符串-整数字典" = 拼装字典(self.game, k, v)`
    - `节点(..., 字典={k: v})` → `节点(..., 字典=拼装字典(self.game, k, v))`（仍会改写，但会产出错误：禁止未显式声明别名字典类型的字典字面量）

    限制（按项目约定）：
    - 禁止空字典 `{}`（无法确定字典键/值类型，也无法映射到【拼装字典】的最少入参）；
    - 禁止键值对数量超过 max_pairs（【拼装字典】最多 50 对）；
    - 禁止出现 `{**d}` 这类字典展开语法（无法静态展开）。
    - `for x in {...}` 直接报错：节点图 for 循环仅支持遍历“列表变量”，字典请先转为键/值列表再迭代。
    - **字典字面量必须显式声明别名字典中文类型注解**：仅允许形如
      `映射: "键类型-值类型字典" = {...}` / `映射: "键类型_值类型字典" = {...}` 的写法；
      禁止直接在节点调用入参或其它表达式中书写 `{...}`，避免出现“未明确数据类型”的字典构造。

    注意：
    - 该函数为“纯函数”：会 deepcopy 输入 AST，并返回新 AST；
    - 不处理模块顶层除 GRAPH_VARIABLES 之外的字典字面量：应由验证层报错（无法转换为节点）。
    """
    if not isinstance(tree, ast.Module):
        raise TypeError("rewrite_graph_code_dict_literals 仅支持 ast.Module 输入")

    max_pairs_int = int(max_pairs)
    if max_pairs_int <= 0:
        raise ValueError("max_pairs 必须为正整数")

    cloned_tree: ast.Module = copy.deepcopy(tree)
    issues: List[DictLiteralRewriteIssue] = []
    module_dict_constant_literals = _collect_module_typed_dict_constant_literals(cloned_tree)

    # 1) 模块顶层：禁止出现字典字面量（GRAPH_VARIABLES 顶层声明除外）
    for top_level_stmt in list(getattr(cloned_tree, "body", []) or []):
        if _is_graph_variables_declaration(top_level_stmt):
            continue
        if _is_allowed_module_level_typed_container_constant(top_level_stmt):
            continue
        if isinstance(top_level_stmt, ast.ClassDef):
            # 类体顶层（非方法体）同样不允许字典字面量：无法转换为节点且会绕过静态校验语义
            for class_item in list(getattr(top_level_stmt, "body", []) or []):
                if isinstance(class_item, ast.FunctionDef):
                    continue
                for node in ast.walk(class_item):
                    if isinstance(node, ast.Dict):
                        issues.append(
                            DictLiteralRewriteIssue(
                                code="CODE_DICT_LITERAL_CLASS_BODY_FORBIDDEN",
                                message="类体顶层禁止使用字典字面量；请将字典构造放到方法体内（会自动转换为【拼装字典】节点），或改写为节点逻辑",
                                node=node,
                            )
                        )
            continue

        for node in ast.walk(top_level_stmt):
            if isinstance(node, ast.Dict):
                issues.append(
                    DictLiteralRewriteIssue(
                        code="CODE_DICT_LITERAL_TOP_LEVEL_FORBIDDEN",
                        message="模块顶层禁止使用字典字面量；请在类方法体内使用字典字面量（会自动转换为【拼装字典】节点），或改写为节点逻辑",
                        node=node,
                    )
                )

    # 2) 类方法体：允许并重写字典字面量（带限制）
    for class_def in _iter_class_defs(cloned_tree):
        for method_def in _iter_method_defs(class_def):
            used_names = _collect_all_name_ids(method_def)
            transformer = _GraphCodeDictLiteralTransformer(
                max_pairs=max_pairs_int,
                used_names=used_names,
                module_dict_constant_literals=module_dict_constant_literals,
            )
            transformer.visit(method_def)
            issues.extend(transformer.issues)

    ast.fix_missing_locations(cloned_tree)
    return cloned_tree, issues


def _is_graph_variables_declaration(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.AnnAssign):
        return False
    target = getattr(stmt, "target", None)
    if not isinstance(target, ast.Name):
        return False
    return target.id == "GRAPH_VARIABLES"


def _extract_string_annotation_text(annotation: ast.AST | None) -> str:
    if isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str):
        return str(annotation.value).strip()
    return ""


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


def _is_allowed_module_level_typed_container_constant(stmt: ast.stmt) -> bool:
    """允许模块顶层“显式具体类型 + 容器字面量”的命名常量声明。"""
    if not isinstance(stmt, ast.AnnAssign):
        return False
    if not isinstance(getattr(stmt, "target", None), ast.Name):
        return False

    value_node = getattr(stmt, "value", None)
    if not isinstance(value_node, (ast.List, ast.Dict)):
        return False

    annotation_text = _extract_string_annotation_text(getattr(stmt, "annotation", None))
    if annotation_text == "":
        return False

    if isinstance(value_node, ast.List):
        return annotation_text in LIST_TYPES and _is_concrete_port_type_text(annotation_text)
    is_alias, _, _ = parse_typed_dict_alias(annotation_text)
    return is_alias and _is_concrete_port_type_text(annotation_text)


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


def _collect_module_typed_dict_constant_literals(tree: ast.Module) -> Dict[str, ast.Dict]:
    """收集模块顶层“显式字典别名类型 + 字典字面量”的命名常量。"""
    mapping: Dict[str, ast.Dict] = {}
    for stmt in list(getattr(tree, "body", []) or []):
        if not isinstance(stmt, ast.AnnAssign):
            continue
        target = getattr(stmt, "target", None)
        value = getattr(stmt, "value", None)
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Dict):
            continue
        annotation_text = _extract_string_annotation_text(getattr(stmt, "annotation", None))
        if annotation_text == "":
            continue
        is_typed_dict_alias, _, _ = parse_typed_dict_alias(annotation_text)
        if not is_typed_dict_alias:
            continue
        if not _is_concrete_port_type_text(annotation_text):
            continue
        mapping[target.id] = value
    return mapping


def _collect_all_name_ids(node: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(getattr(sub, "id", None), str):
            names.add(sub.id)
    return names


def _build_self_game_expr() -> ast.expr:
    return ast.Attribute(
        value=ast.Name(id="self", ctx=ast.Load()),
        attr="game",
        ctx=ast.Load(),
    )


class _GraphCodeDictLiteralTransformer(ast.NodeTransformer):
    def __init__(
        self,
        *,
        max_pairs: int,
        used_names: Set[str],
        module_dict_constant_literals: Optional[Dict[str, ast.Dict]] = None,
    ):
        self.max_pairs = int(max_pairs)
        self.used_names: Set[str] = set(used_names or set())
        self.issues: List[DictLiteralRewriteIssue] = []
        self._module_dict_constant_literals: Dict[str, ast.Dict] = dict(module_dict_constant_literals or {})
        # 仅允许“直接作为 AnnAssign.value 的字典字面量”，且该 AnnAssign 的注解必须为别名字典类型。
        # 通过记录“允许的 dict 节点 id”精确放行，避免误放行嵌套 dict（例如 {"a": {"b": 1}}）。
        self._allowed_typed_dict_literal_ids: Set[int] = set()

    def visit_Call(self, node: ast.Call):  # noqa: N802
        # 模块级“带字典别名类型注解”的命名常量在调用参数位改写为【拼装字典】调用：
        # - 与列表常量策略对齐，避免整表落入目标节点 input_constants；
        # - 仅在调用参数位处理，不改变变量声明语义。
        args = list(getattr(node, "args", []) or [])
        new_args: List[ast.expr] = []
        for arg in args:
            replaced = self._maybe_replace_module_dict_constant_ref(arg)
            new_args.append(replaced)
        node.args = new_args

        keywords = list(getattr(node, "keywords", []) or [])
        for keyword in keywords:
            keyword.value = self._maybe_replace_module_dict_constant_ref(keyword.value)

        return self.generic_visit(node)

    def visit_For(self, node: ast.For):  # noqa: N802
        # 约定：for 的迭代器位置禁止直接使用字典字面量 `{...}`：
        # - 节点图 for 循环仅支持遍历“列表变量”；字典遍历应先用节点转为键/值列表再迭代；
        # - 同时该位置无法显式表达字典键/值的中文类型注解，容易造成类型推断与端口校验口径不一致。
        iter_expr = getattr(node, "iter", None)
        if isinstance(iter_expr, ast.Dict):
            dict_node = iter_expr
            if self._is_dict_literal_valid(dict_node):
                self.issues.append(
                    DictLiteralRewriteIssue(
                        code="CODE_DICT_LITERAL_FOR_ITER_FORBIDDEN",
                        message=(
                            "for 循环的迭代器位置禁止直接使用字典字面量；"
                            "节点图 for 循环仅支持遍历“列表变量”。如需遍历字典，请先使用"
                            "【获取字典中键组成的列表】或【获取字典中值组成的列表】得到列表变量，再进行 for 迭代。"
                        ),
                        node=dict_node,
                    )
                )
            else:
                self._report_dict_literal_issue(dict_node)

            node.target = self.visit(node.target)  # type: ignore[assignment]
            node.body = self._visit_stmt_list(getattr(node, "body", []) or [])
            node.orelse = self._visit_stmt_list(getattr(node, "orelse", []) or [])
            return node

        return self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict):  # noqa: N802
        if not self._is_dict_literal_valid(node):
            self._report_dict_literal_issue(node)
            return self.generic_visit(node)

        # 项目核心约束：字典必须具备“键/值类型”的显式中文注解（别名字典），否则视为未明确定义数据类型。
        # 允许的唯一路径：该 dict 是某个 AnnAssign.value 且其注解为别名字典类型。
        if id(node) not in self._allowed_typed_dict_literal_ids:
            self.issues.append(
                DictLiteralRewriteIssue(
                    code="CODE_DICT_LITERAL_TYPED_ANNOTATION_REQUIRED",
                    message=(
                        "禁止直接使用字典字面量 `{...}` 作为节点入参或表达式；"
                        "字典必须先落到变量并显式声明别名字典中文类型注解（键类型-值类型字典 / 键类型_值类型字典）。"
                        "例如：映射: \"字符串-GUID字典\" = {\"校准_键\": 占位_GUID}"
                    ),
                    node=node,
                )
            )
        return self._rewrite_dict_literal_to_build_dict_call(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):  # noqa: N802
        """仅放行：带别名字典中文类型注解的 `x: "键-值字典" = {...}`。"""
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Dict):
            return self.generic_visit(node)

        annotation = getattr(node, "annotation", None)
        type_text = ""
        if isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str):
            type_text = str(annotation.value).strip()

        is_typed_dict_alias, _, _ = parse_typed_dict_alias(type_text)
        if is_typed_dict_alias:
            self._allowed_typed_dict_literal_ids.add(id(value))
        visited_value = self.visit(value)
        if isinstance(visited_value, ast.expr):
            node.value = visited_value  # type: ignore[assignment]
        if is_typed_dict_alias:
            self._allowed_typed_dict_literal_ids.discard(id(value))

        # target/annotation 不需要改写；但仍递归访问以处理其中可能存在的语法糖（保守一致）。
        node.target = self.visit(node.target)  # type: ignore[assignment]
        node.annotation = self.visit(node.annotation)  # type: ignore[assignment]
        return node

    def _visit_stmt_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        new_list: List[ast.stmt] = []
        for stmt in list(stmts or []):
            visited = self.visit(stmt)
            if visited is None:
                continue
            if isinstance(visited, list):
                for sub in visited:
                    if isinstance(sub, ast.stmt):
                        new_list.append(sub)
                continue
            if isinstance(visited, ast.stmt):
                new_list.append(visited)
        return new_list

    def _is_dict_literal_valid(self, node: ast.Dict) -> bool:
        keys = list(getattr(node, "keys", []) or [])
        values = list(getattr(node, "values", []) or [])
        if len(keys) == 0:
            return False
        if len(keys) != len(values):
            return False
        if len(keys) > self.max_pairs:
            return False
        # `{**d}` 在 AST 中以 key=None 表示
        if any(key is None for key in keys):
            return False
        return True

    def _report_dict_literal_issue(self, node: ast.Dict) -> None:
        keys = list(getattr(node, "keys", []) or [])
        values = list(getattr(node, "values", []) or [])
        pair_count = len(keys)
        if pair_count == 0:
            self.issues.append(
                DictLiteralRewriteIssue(
                    code="CODE_EMPTY_DICT_LITERAL_FORBIDDEN",
                    message="禁止定义空字典字面量 {}",
                    node=node,
                )
            )
            return
        if pair_count != len(values):
            self.issues.append(
                DictLiteralRewriteIssue(
                    code="CODE_DICT_LITERAL_KEY_VALUE_COUNT_MISMATCH",
                    message="字典字面量键和值数量不一致（语法结构异常）",
                    node=node,
                )
            )
            return
        if pair_count > self.max_pairs:
            self.issues.append(
                DictLiteralRewriteIssue(
                    code="CODE_DICT_LITERAL_TOO_LONG",
                    message=f"字典字面量键值对数量为 {pair_count}，超过上限 {self.max_pairs}；请拆分为多段或改写为节点逻辑",
                    node=node,
                )
            )
            return
        if any(key is None for key in keys):
            self.issues.append(
                DictLiteralRewriteIssue(
                    code="CODE_DICT_LITERAL_UNPACK_NOT_SUPPORTED",
                    message="字典字面量不支持使用 ** 展开语法（例如 {**d}）；请改用字典相关节点逐步构造/更新",
                    node=node,
                )
            )
            return
        self.issues.append(
            DictLiteralRewriteIssue(
                code="CODE_DICT_LITERAL_UNSUPPORTED",
                message="该字典字面量写法暂不支持转换为【拼装字典】节点",
                node=node,
            )
        )

    def _rewrite_dict_literal_to_build_dict_call(self, node: ast.Dict) -> ast.Call:
        rewritten_pairs: List[ast.expr] = []
        keys = list(getattr(node, "keys", []) or [])
        values = list(getattr(node, "values", []) or [])
        for key_expr, value_expr in zip(keys, values, strict=True):
            if key_expr is None:
                continue
            visited_key = self.visit(key_expr)
            visited_value = self.visit(value_expr)
            if isinstance(visited_key, ast.expr):
                rewritten_key = visited_key
            else:
                rewritten_key = key_expr
            if isinstance(visited_value, ast.expr):
                rewritten_value = visited_value
            else:
                rewritten_value = value_expr
            rewritten_pairs.extend([rewritten_key, rewritten_value])

        call_node = ast.Call(
            func=ast.Name(id=BUILD_DICT_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr(), *rewritten_pairs],
            keywords=[],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    def _maybe_replace_module_dict_constant_ref(self, expr: ast.expr) -> ast.expr:
        if not (isinstance(expr, ast.Name) and isinstance(getattr(expr, "ctx", None), ast.Load)):
            return expr
        dict_literal = self._module_dict_constant_literals.get(expr.id)
        if not isinstance(dict_literal, ast.Dict):
            return expr

        inlined_dict = copy.deepcopy(dict_literal)
        ast.copy_location(inlined_dict, expr)
        inlined_dict.end_lineno = getattr(expr, "end_lineno", getattr(inlined_dict, "lineno", None))
        if not self._is_dict_literal_valid(inlined_dict):
            self._report_dict_literal_issue(inlined_dict)
            return expr
        return self._rewrite_dict_literal_to_build_dict_call(inlined_dict)


