from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional

from .graph_code_rewrite_config import DEFAULT_MAX_LIST_LITERAL_ELEMENTS
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


BUILD_LIST_NODE_CALL_NAME = "拼装列表"
LIST_SET_ITEM_NODE_CALL_NAME = "对列表修改值"
LIST_DELETE_ITEM_NODE_CALL_NAME = "对列表移除值"
LIST_INSERT_ITEM_NODE_CALL_NAME = "对列表插入值"
LIST_CLEAR_NODE_CALL_NAME = "清除列表"
LIST_EXTEND_NODE_CALL_NAME = "拼接列表"

_LIST_METHOD_INSERT_NAME = "insert"
_LIST_METHOD_CLEAR_NAME = "clear"
_LIST_METHOD_EXTEND_NAME = "extend"


@dataclass(frozen=True)
class ListLiteralRewriteIssue:
    """列表字面量重写过程中的问题。

    约定：
    - issue.node 必须是可定位行号的 AST 节点（通常就是 ast.List）；
    - 不做 try/except：若 AST 结构异常直接抛出。
    """

    code: str
    message: str
    node: ast.AST


def rewrite_graph_code_list_literals(
    tree: ast.Module,
    *,
    max_elements: int = DEFAULT_MAX_LIST_LITERAL_ELEMENTS,
) -> Tuple[ast.Module, List[ListLiteralRewriteIssue]]:
    """将 Graph Code 中“类方法体”的列表相关语法糖改写为等价的节点调用。

    支持：
    - `x = [a, b, c]` → `x = 拼装列表(self.game, a, b, c)`
    - `节点(..., 列表=[a, b])` → `节点(..., 列表=拼装列表(self.game, a, b))`
    - `目标列表[序号] = 值` → `对列表修改值(self.game, 列表=目标列表, 序号=序号, 值=值)`（仅单下标，不支持切片）
    - `del 目标列表[序号]` → `对列表移除值(self.game, 列表=目标列表, 移除序号=序号)`（仅单下标，不支持切片）
    - `目标列表.insert(序号, 值)` → `对列表插入值(self.game, 列表=目标列表, 插入序号=序号, 插入值=值)`
    - `目标列表.clear()` → `清除列表(self.game, 列表=目标列表)`
    - `目标列表.extend(接入列表)` → `拼接列表(self.game, 目标列表=目标列表, 接入的列表=接入列表)`

    限制（按项目约定）：
    - 禁止空列表 `[]`；
    - 禁止元素数超过 max_elements；
    - 禁止出现 `[*xs]` 这类 Starred 扩展语法（解析器无法静态展开）。
    - `for x in [...]` 不允许：for 的迭代器位置必须是“显式声明带中文类型注解”的列表变量（例如 `列表: "整数列表" = [1,2,3]`）。

    注意：
    - 该函数为“纯函数”：会 deepcopy 输入 AST，并返回新 AST；
    - 不处理模块/类体顶层的语法糖：应由验证层报错（无法转换为节点）。
    """
    if not isinstance(tree, ast.Module):
        raise TypeError("rewrite_graph_code_list_literals 仅支持 ast.Module 输入")

    max_elements_int = int(max_elements)
    if max_elements_int <= 0:
        raise ValueError("max_elements 必须为正整数")

    cloned_tree: ast.Module = copy.deepcopy(tree)
    issues: List[ListLiteralRewriteIssue] = []
    module_list_constant_literals = _collect_module_typed_list_constant_literals(cloned_tree)

    # 1) 模块顶层：禁止出现列表字面量（GRAPH_VARIABLES 顶层声明除外）
    for top_level_stmt in list(getattr(cloned_tree, "body", []) or []):
        if _is_graph_variables_declaration(top_level_stmt):
            continue
        if _is_allowed_module_level_typed_container_constant(top_level_stmt):
            continue
        if isinstance(top_level_stmt, ast.ClassDef):
            # 类体顶层（非方法体）同样不允许列表字面量：无法转换为节点且会绕过静态校验语义
            for class_item in list(getattr(top_level_stmt, "body", []) or []):
                if isinstance(class_item, ast.FunctionDef):
                    continue
                for node in ast.walk(class_item):
                    if isinstance(node, ast.List):
                        issues.append(
                            ListLiteralRewriteIssue(
                                code="CODE_LIST_LITERAL_CLASS_BODY_FORBIDDEN",
                                message="类体顶层禁止使用列表字面量；请将列表构造放到方法体内（会自动转换为【拼装列表】节点），或改写为节点逻辑",
                                node=node,
                            )
                        )
            continue
        for node in ast.walk(top_level_stmt):
            if isinstance(node, ast.List):
                issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_LITERAL_TOP_LEVEL_FORBIDDEN",
                        message="模块顶层禁止使用列表字面量；请在类方法体内使用列表字面量（会自动转换为【拼装列表】节点），或改写为节点逻辑",
                        node=node,
                    )
                )

    # 2) 类方法体：允许并重写列表字面量（带限制）
    for class_def in _iter_class_defs(cloned_tree):
        for method_def in _iter_method_defs(class_def):
            used_names = _collect_all_name_ids(method_def)
            transformer = _GraphCodeListLiteralTransformer(
                max_elements=max_elements_int,
                used_names=used_names,
                module_list_constant_literals=module_list_constant_literals,
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
    """允许模块顶层“显式具体类型 + 容器字面量”的命名常量声明。

    仅放行：
    - `常量: "具体列表类型" = [...]`
    - `常量: "键类型-值类型字典" = {...}`（或 `_` 分隔）
    """
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
    return _is_concrete_port_type_text(annotation_text) and parse_typed_dict_alias(annotation_text)[0]


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


def _collect_module_typed_list_constant_literals(tree: ast.Module) -> Dict[str, ast.List]:
    """收集模块顶层“显式列表类型 + 列表字面量”的命名常量。

    用途：
    - 当方法体中的节点调用参数直接引用这些常量（如 `列表=常量列表`）时，
      先内联回列表字面量，再交给统一的列表字面量改写流程，
      从而稳定生成【拼装列表】节点，而不是把整表写成目标节点的 input_constants。
    """
    mapping: Dict[str, ast.List] = {}
    for stmt in list(getattr(tree, "body", []) or []):
        if not isinstance(stmt, ast.AnnAssign):
            continue
        target = getattr(stmt, "target", None)
        value = getattr(stmt, "value", None)
        if not isinstance(target, ast.Name) or not isinstance(value, ast.List):
            continue
        annotation_text = _extract_string_annotation_text(getattr(stmt, "annotation", None))
        if annotation_text == "":
            continue
        if annotation_text not in LIST_TYPES:
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


class _GraphCodeListLiteralTransformer(ast.NodeTransformer):
    def __init__(
        self,
        *,
        max_elements: int,
        used_names: Set[str],
        module_list_constant_literals: Optional[Dict[str, ast.List]] = None,
    ):
        self.max_elements = int(max_elements)
        self.used_names: Set[str] = set(used_names or set())
        self.issues: List[ListLiteralRewriteIssue] = []
        self._temp_counter = 1
        self._module_list_constant_literals: Dict[str, ast.List] = dict(module_list_constant_literals or {})

    def visit_Call(self, node: ast.Call):  # noqa: N802
        # 模块级“带列表类型注解”的命名常量在调用参数位统一内联为列表字面量：
        # - 之后会被 visit_List 改写为【拼装列表】节点调用；
        # - 仅在“调用参数位置”处理，避免影响 for-iter 等其它语义位置。
        args = list(getattr(node, "args", []) or [])
        new_args: List[ast.expr] = []
        for arg in args:
            if isinstance(arg, ast.Name) and isinstance(getattr(arg, "ctx", None), ast.Load):
                list_literal = self._module_list_constant_literals.get(arg.id)
                if isinstance(list_literal, ast.List):
                    inlined = copy.deepcopy(list_literal)
                    ast.copy_location(inlined, arg)
                    inlined.end_lineno = getattr(arg, "end_lineno", getattr(inlined, "lineno", None))
                    new_args.append(inlined)
                    continue
            new_args.append(arg)
        node.args = new_args

        keywords = list(getattr(node, "keywords", []) or [])
        for kw in keywords:
            value = getattr(kw, "value", None)
            if isinstance(value, ast.Name) and isinstance(getattr(value, "ctx", None), ast.Load):
                list_literal = self._module_list_constant_literals.get(value.id)
                if isinstance(list_literal, ast.List):
                    inlined = copy.deepcopy(list_literal)
                    ast.copy_location(inlined, value)
                    inlined.end_lineno = getattr(value, "end_lineno", getattr(inlined, "lineno", None))
                    kw.value = inlined

        return self.generic_visit(node)

    def visit_For(self, node: ast.For):  # noqa: N802
        # 先处理 for 的 iter，再递归处理循环体。
        #
        # 约定：for 的迭代器位置禁止直接使用列表字面量 `[...]`：
        # - 该写法无法在源码层显式声明列表类型，类型推断会变弱，容易让后续端口类型校验漏报；
        # - 必须先用“带中文类型注解”的列表变量承接（例如 `列表: "整数列表" = [1,2,3]`），再 `for x in 列表:`。
        iter_expr = getattr(node, "iter", None)
        if isinstance(iter_expr, ast.List):
            list_node = iter_expr
            if self._is_list_literal_valid(list_node):
                self.issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_LITERAL_FOR_ITER_FORBIDDEN",
                        message=(
                            "for 循环的迭代器位置禁止直接使用列表字面量；"
                            "请先声明带中文类型注解的列表变量（例如：列表: \"整数列表\" = [1, 2, 3]），"
                            "再写为 `for 当前元素 in 列表:`"
                        ),
                        node=list_node,
                    )
                )
            else:
                # iter 列表本身不合法（空/超长/*展开等）：沿用通用错误
                self._report_list_literal_issue(list_node)

            node.target = self.visit(node.target)  # type: ignore[assignment]
            node.body = self._visit_stmt_list(getattr(node, "body", []) or [])
            node.orelse = self._visit_stmt_list(getattr(node, "orelse", []) or [])
            return node

        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):  # noqa: N802
        targets = list(getattr(node, "targets", []) or [])
        if not targets:
            return self.generic_visit(node)

        subscript_targets = [t for t in targets if isinstance(t, ast.Subscript)]
        if not subscript_targets:
            return self.generic_visit(node)

        if len(targets) != 1:
            first_subscript = subscript_targets[0]
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_ASSIGN_CHAIN_FORBIDDEN",
                    message="不支持链式/多目标的列表下标赋值；请拆分为多行（例如：先分别计算值，再逐行写 `目标列表[序号] = 值`）",
                    node=first_subscript,
                )
            )
            return self.generic_visit(node)

        target = targets[0]
        if not isinstance(target, ast.Subscript):
            return self.generic_visit(node)

        rewritten_statement = self._rewrite_list_subscript_assignment(node, target)
        if rewritten_statement is None:
            return self.generic_visit(node)
        return rewritten_statement

    def visit_AugAssign(self, node: ast.AugAssign):  # noqa: N802
        target = getattr(node, "target", None)
        if isinstance(target, ast.Subscript):
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_AUG_ASSIGN_FORBIDDEN",
                    message="不支持对列表下标使用 +=/-=/... 这类增量赋值；请拆分为：取值 → 运算 → `目标列表[序号] = 新值`",
                    node=target,
                )
            )
            return self.generic_visit(node)
        return self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete):  # noqa: N802
        targets = list(getattr(node, "targets", []) or [])
        if not targets:
            return self.generic_visit(node)

        subscript_targets = [t for t in targets if isinstance(t, ast.Subscript)]
        if not subscript_targets:
            return self.generic_visit(node)

        if len(targets) != 1:
            first_subscript = subscript_targets[0]
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_DELETE_MULTIPLE_TARGETS_FORBIDDEN",
                    message="不支持在同一条 del 语句中删除多个列表下标；请拆分为多行 `del 目标列表[序号]`",
                    node=first_subscript,
                )
            )
            return self.generic_visit(node)

        target = targets[0]
        if not isinstance(target, ast.Subscript):
            return self.generic_visit(node)

        rewritten_statement = self._rewrite_list_subscript_delete(node, target)
        if rewritten_statement is None:
            return self.generic_visit(node)
        return rewritten_statement

    def visit_Expr(self, node: ast.Expr):  # noqa: N802
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Call):
            return self.generic_visit(node)

        func = getattr(value, "func", None)
        if not isinstance(func, ast.Attribute):
            return self.generic_visit(node)

        method_name = str(getattr(func, "attr", "") or "")
        if method_name not in {_LIST_METHOD_INSERT_NAME, _LIST_METHOD_CLEAR_NAME, _LIST_METHOD_EXTEND_NAME}:
            return self.generic_visit(node)

        rewritten_statement = self._rewrite_list_method_call_expr(node, value, method_name)
        if rewritten_statement is None:
            return self.generic_visit(node)
        return rewritten_statement

    def visit_List(self, node: ast.List):  # noqa: N802
        # 空列表 / 超长 / starred：直接报错，不改写（保持原节点以便错误定位更直观）
        if not self._is_list_literal_valid(node):
            self._report_list_literal_issue(node)
            return self.generic_visit(node)

        return self._rewrite_list_literal_to_build_list_call(node)

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

    def _is_list_literal_valid(self, node: ast.List) -> bool:
        elements = list(getattr(node, "elts", []) or [])
        if len(elements) == 0:
            return False
        if len(elements) > self.max_elements:
            return False
        for element in elements:
            if isinstance(element, ast.Starred):
                return False
        return True

    def _report_list_literal_issue(self, node: ast.List) -> None:
        elements = list(getattr(node, "elts", []) or [])
        if len(elements) == 0:
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_EMPTY_LIST_LITERAL_FORBIDDEN",
                    message="禁止定义空列表字面量 []",
                    node=node,
                )
            )
            return
        if len(elements) > self.max_elements:
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_LITERAL_TOO_LONG",
                    message=f"列表字面量元素数量为 {len(elements)}，超过上限 {self.max_elements}；请拆分为多段或改写为节点逻辑",
                    node=node,
                )
            )
            return
        for element in elements:
            if isinstance(element, ast.Starred):
                self.issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_LITERAL_STARRED_NOT_SUPPORTED",
                        message="列表字面量不支持使用 * 展开语法（例如 [*xs]）；请显式写出元素或改用节点逻辑",
                        node=node,
                    )
                )
                return
        # 兜底：未知原因视为不支持
        self.issues.append(
            ListLiteralRewriteIssue(
                code="CODE_LIST_LITERAL_UNSUPPORTED",
                message="该列表字面量写法暂不支持转换为【拼装列表】节点",
                node=node,
            )
        )

    def _rewrite_list_literal_to_build_list_call(self, node: ast.List) -> ast.Call:
        # 先递归访问元素，支持嵌套列表字面量：[[1,2],[3,4]] 会变成 拼装列表(..., 拼装列表(...), 拼装列表(...))
        rewritten_elements: List[ast.expr] = []
        for element in list(getattr(node, "elts", []) or []):
            visited_element = self.visit(element)
            if isinstance(visited_element, ast.expr):
                rewritten_elements.append(visited_element)
            elif isinstance(element, ast.expr):
                rewritten_elements.append(element)

        call_node = ast.Call(
            func=ast.Name(id=BUILD_LIST_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr(), *rewritten_elements],
            keywords=[],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    def _rewrite_list_subscript_assignment(
        self,
        assign_stmt: ast.Assign,
        target: ast.Subscript,
    ) -> Optional[ast.stmt]:
        list_expr = getattr(target, "value", None)
        if not isinstance(list_expr, ast.Name):
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_TARGET_MUST_BE_NAME",
                    message="列表下标赋值仅支持变量名形式：`目标列表[序号] = 值`；不支持属性/表达式作为目标列表",
                    node=target,
                )
            )
            return None

        index_expr = self._extract_subscript_index_expr(target)
        if index_expr is None:
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_INDEX_UNSUPPORTED",
                    message="该列表下标写法暂不支持转换为节点逻辑（仅支持单个下标，不支持切片/多维索引）",
                    node=target,
                )
            )
            return None

        rewritten_index_expr = self.visit(index_expr)
        if isinstance(rewritten_index_expr, ast.expr):
            index_expr = rewritten_index_expr

        value_expr = getattr(assign_stmt, "value", None)
        if not isinstance(value_expr, ast.expr):
            return None
        rewritten_value_expr = self.visit(value_expr)
        if isinstance(rewritten_value_expr, ast.expr):
            value_expr = rewritten_value_expr

        call_node = ast.Call(
            func=ast.Name(id=LIST_SET_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="列表", value=ast.Name(id=list_expr.id, ctx=ast.Load())),
                ast.keyword(arg="序号", value=index_expr),
                ast.keyword(arg="值", value=value_expr),
            ],
        )
        new_stmt = ast.Expr(value=call_node)
        ast.copy_location(new_stmt, assign_stmt)
        new_stmt.end_lineno = getattr(assign_stmt, "end_lineno", getattr(new_stmt, "lineno", None))
        return new_stmt

    def _rewrite_list_subscript_delete(
        self,
        delete_stmt: ast.Delete,
        target: ast.Subscript,
    ) -> Optional[ast.stmt]:
        list_expr = getattr(target, "value", None)
        if not isinstance(list_expr, ast.Name):
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_TARGET_MUST_BE_NAME",
                    message="del 列表下标仅支持变量名形式：`del 目标列表[序号]`；不支持属性/表达式作为目标列表",
                    node=target,
                )
            )
            return None

        index_expr = self._extract_subscript_index_expr(target)
        if index_expr is None:
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_SUBSCRIPT_INDEX_UNSUPPORTED",
                    message="该 del 列表下标写法暂不支持转换为节点逻辑（仅支持单个下标，不支持切片/多维索引）",
                    node=target,
                )
            )
            return None

        rewritten_index_expr = self.visit(index_expr)
        if isinstance(rewritten_index_expr, ast.expr):
            index_expr = rewritten_index_expr

        call_node = ast.Call(
            func=ast.Name(id=LIST_DELETE_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="列表", value=ast.Name(id=list_expr.id, ctx=ast.Load())),
                ast.keyword(arg="移除序号", value=index_expr),
            ],
        )
        new_stmt = ast.Expr(value=call_node)
        ast.copy_location(new_stmt, delete_stmt)
        new_stmt.end_lineno = getattr(delete_stmt, "end_lineno", getattr(new_stmt, "lineno", None))
        return new_stmt

    def _rewrite_list_method_call_expr(
        self,
        expr_stmt: ast.Expr,
        call_node: ast.Call,
        method_name: str,
    ) -> Optional[ast.stmt]:
        func = getattr(call_node, "func", None)
        if not isinstance(func, ast.Attribute):
            return None

        list_expr = getattr(func, "value", None)
        if not isinstance(list_expr, ast.Name):
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_METHOD_TARGET_MUST_BE_NAME",
                    message=f"列表方法 `{method_name}()` 语法糖仅支持变量名形式：`目标列表.{method_name}(...)`；不支持属性/表达式作为目标列表",
                    node=func,
                )
            )
            return None

        positional_args = list(getattr(call_node, "args", []) or [])
        keywords = list(getattr(call_node, "keywords", []) or [])
        if keywords:
            self.issues.append(
                ListLiteralRewriteIssue(
                    code="CODE_LIST_METHOD_KEYWORD_ARGS_FORBIDDEN",
                    message=f"列表方法 `{method_name}()` 不支持关键字参数写法；请使用位置参数（例如 `目标列表.{method_name}(... )`）",
                    node=call_node,
                )
            )
            return None

        rewritten_args: List[ast.expr] = []
        for arg in positional_args:
            visited_arg = self.visit(arg)
            if isinstance(visited_arg, ast.expr):
                rewritten_args.append(visited_arg)
            else:
                rewritten_args.append(arg)
        positional_args = rewritten_args

        if method_name == _LIST_METHOD_INSERT_NAME:
            if len(positional_args) != 2:
                self.issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_METHOD_INSERT_ARGS_INVALID",
                        message="仅支持 `目标列表.insert(序号, 值)` 形式（必须恰好 2 个位置参数）",
                        node=call_node,
                    )
                )
                return None
            index_expr, value_expr = positional_args
            new_call_node = ast.Call(
                func=ast.Name(id=LIST_INSERT_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="列表", value=ast.Name(id=list_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="插入序号", value=index_expr),
                    ast.keyword(arg="插入值", value=value_expr),
                ],
            )
        elif method_name == _LIST_METHOD_CLEAR_NAME:
            if positional_args:
                self.issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_METHOD_CLEAR_ARGS_INVALID",
                        message="仅支持 `目标列表.clear()` 形式（不允许传参）",
                        node=call_node,
                    )
                )
                return None
            new_call_node = ast.Call(
                func=ast.Name(id=LIST_CLEAR_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="列表", value=ast.Name(id=list_expr.id, ctx=ast.Load())),
                ],
            )
        elif method_name == _LIST_METHOD_EXTEND_NAME:
            if len(positional_args) != 1:
                self.issues.append(
                    ListLiteralRewriteIssue(
                        code="CODE_LIST_METHOD_EXTEND_ARGS_INVALID",
                        message="仅支持 `目标列表.extend(接入列表)` 形式（必须恰好 1 个位置参数）",
                        node=call_node,
                    )
                )
                return None
            other_list_expr = positional_args[0]
            new_call_node = ast.Call(
                func=ast.Name(id=LIST_EXTEND_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="目标列表", value=ast.Name(id=list_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="接入的列表", value=other_list_expr),
                ],
            )
        else:
            return None

        new_stmt = ast.Expr(value=new_call_node)
        ast.copy_location(new_stmt, expr_stmt)
        new_stmt.end_lineno = getattr(expr_stmt, "end_lineno", getattr(new_stmt, "lineno", None))
        return new_stmt

    def _extract_subscript_index_expr(self, node: ast.Subscript) -> Optional[ast.expr]:
        slice_node = getattr(node, "slice", None)
        if isinstance(slice_node, ast.Slice):
            return None
        if isinstance(slice_node, ast.Tuple):
            return None
        if isinstance(slice_node, ast.expr):
            return slice_node
        return None

    def _next_temp_list_var_name(self, lineno: Optional[int]) -> str:
        line_part = int(lineno) if isinstance(lineno, int) and lineno > 0 else 0
        while True:
            candidate = f"__auto_list_literal_for_{line_part}_{self._temp_counter}"
            self._temp_counter += 1
            if candidate in self.used_names:
                continue
            self.used_names.add(candidate)
            return candidate


