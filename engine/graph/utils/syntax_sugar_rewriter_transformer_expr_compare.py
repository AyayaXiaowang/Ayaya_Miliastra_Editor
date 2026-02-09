from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from .syntax_sugar_rewriter_ast_helpers import (
    _build_self_game_expr,
    _extract_subscript_index_expr,
    _is_dict_var_name,
)
from .syntax_sugar_rewriter_constants import (
    ABS_NODE_CALL_NAME,
    ADD_NODE_CALL_NAME,
    DICT_CONTAINS_KEY_NODE_CALL_NAME,
    DICT_DELETE_ITEM_NODE_CALL_NAME,
    DICT_GET_ITEM_NODE_CALL_NAME,
    DICT_LENGTH_NODE_CALL_NAME,
    DICT_SET_ITEM_NODE_CALL_NAME,
    DIVIDE_NODE_CALL_NAME,
    EQUAL_NODE_CALL_NAME,
    INTEGER_ROUNDING_NODE_CALL_NAME,
    LOGIC_NOT_NODE_CALL_NAME,
    LIST_CONTAINS_NODE_CALL_NAME,
    LIST_GET_ITEM_NODE_CALL_NAME,
    LIST_LENGTH_NODE_CALL_NAME,
    LIST_MAX_VALUE_NODE_CALL_NAME,
    LIST_MIN_VALUE_NODE_CALL_NAME,
    LOGIC_AND_NODE_CALL_NAME,
    LOGIC_OR_NODE_CALL_NAME,
    MULTIPLY_NODE_CALL_NAME,
    ROUNDING_MODE_CEIL,
    ROUNDING_MODE_FLOOR,
    ROUNDING_MODE_ROUND,
    SUBTRACT_NODE_CALL_NAME,
    TYPE_CONVERSION_NODE_CALL_NAME,
    _arith_node_name,
    _list_get_list_port_name,
    _list_length_list_port_name,
    _logic_binary_input_port_names,
    _logic_not_input_port_name,
    _normalize_scope,
    _numeric_compare_node_name,
)
from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue


class _GraphCodeSyntaxSugarTransformerExprCompareMixin:
    def visit_Compare(self, node: ast.Compare):  # noqa: N802
        # 先处理子表达式
        left_expr = getattr(node, "left", None)
        if isinstance(left_expr, ast.expr):
            visited_left = self.visit(left_expr)
            if isinstance(visited_left, ast.expr):
                node.left = visited_left  # type: ignore[assignment]

        comparators = list(getattr(node, "comparators", []) or [])
        rewritten_comparators: List[ast.expr] = []
        for comp in comparators:
            visited_comp = self.visit(comp)
            if isinstance(visited_comp, ast.expr):
                rewritten_comparators.append(visited_comp)
            else:
                rewritten_comparators.append(comp)
        node.comparators = rewritten_comparators  # type: ignore[assignment]

        ops = list(getattr(node, "ops", []) or [])
        if len(ops) != 1 or len(node.comparators) != 1:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_COMPARE_CHAIN_FORBIDDEN",
                    message="不支持链式比较（例如 a < b < c 或 x in a in b）；请拆分为多个布尔变量并用【逻辑与运算/逻辑或运算】组合",
                    node=node,
                )
            )
            return node

        op = ops[0]
        right_expr = node.comparators[0]
        left_expr = node.left

        # == / !=
        if isinstance(op, (ast.Eq, ast.NotEq)):
            eq_call = ast.Call(
                func=ast.Name(id=EQUAL_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="输入1", value=left_expr),
                    ast.keyword(arg="输入2", value=right_expr),
                ],
            )
            ast.copy_location(eq_call, node)
            eq_call.end_lineno = getattr(node, "end_lineno", getattr(eq_call, "lineno", None))
            if isinstance(op, ast.Eq):
                return eq_call
            not_port_name = _logic_not_input_port_name(self.scope)
            not_call = ast.Call(
                func=ast.Name(id=LOGIC_NOT_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg=not_port_name, value=eq_call)],
            )
            ast.copy_location(not_call, node)
            not_call.end_lineno = getattr(node, "end_lineno", getattr(not_call, "lineno", None))
            return not_call

        # 数值比较：>, <, >=, <=（按 scope 映射节点名）
        numeric_node_name = _numeric_compare_node_name(self.scope, op)
        if numeric_node_name is not None:
            call_node = ast.Call(
                func=ast.Name(id=numeric_node_name, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="左值", value=left_expr),
                    ast.keyword(arg="右值", value=right_expr),
                ],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        # in / not in：按右侧容器类型选择节点
        if isinstance(op, (ast.In, ast.NotIn)):
            # 扩展：支持 `值 in 字典变量.values()` / `键 in 字典变量.keys()`
            # - values(): 单节点等价映射为【查询字典是否包含特定值】
            # - keys(): 等价映射为【查询字典是否包含特定键】（与 `键 in 字典变量` 语义一致）
            dict_container_name: Optional[str] = None
            keys_or_values: Optional[str] = None  # "keys" | "values"

            if isinstance(right_expr, ast.Call):
                right_func = getattr(right_expr, "func", None)
                # 1) 先匹配“已被 visit_Call 重写”的形态：获取字典中键/值组成的列表(...)
                if isinstance(right_func, ast.Name) and right_func.id in {"获取字典中键组成的列表", "获取字典中值组成的列表"}:
                    right_keywords = list(getattr(right_expr, "keywords", []) or [])
                    if len(right_keywords) == 1 and right_keywords[0].arg == "字典":
                        dict_arg = right_keywords[0].value
                        if isinstance(dict_arg, ast.Name):
                            dict_container_name = dict_arg.id
                            keys_or_values = "keys" if right_func.id == "获取字典中键组成的列表" else "values"
                # 2) 再匹配“尚未重写”的形态：字典变量.keys()/values()
                if dict_container_name is None and isinstance(right_func, ast.Attribute):
                    base = getattr(right_func, "value", None)
                    attr_name = str(getattr(right_func, "attr", "") or "")
                    if (
                        isinstance(base, ast.Name)
                        and _is_dict_var_name(base.id, self.dict_var_names)
                        and attr_name in {"keys", "values"}
                    ):
                        dict_container_name = base.id
                        keys_or_values = attr_name

            if dict_container_name and keys_or_values:
                # client 侧 keys()/values() 已在 visit_Call 中给出明确错误：这里不重复上报“in 右侧必须是 Name”
                if self.scope != "server":
                    return node

                if keys_or_values == "values":
                    contains_call = ast.Call(
                        func=ast.Name(id="查询字典是否包含特定值", ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[
                            ast.keyword(arg="字典", value=ast.Name(id=dict_container_name, ctx=ast.Load())),
                            ast.keyword(arg="值", value=left_expr),
                        ],
                    )
                else:
                    contains_call = ast.Call(
                        func=ast.Name(id=DICT_CONTAINS_KEY_NODE_CALL_NAME, ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[
                            ast.keyword(arg="字典", value=ast.Name(id=dict_container_name, ctx=ast.Load())),
                            ast.keyword(arg="键", value=left_expr),
                        ],
                    )

                ast.copy_location(contains_call, node)
                contains_call.end_lineno = getattr(node, "end_lineno", getattr(contains_call, "lineno", None))
                if isinstance(op, ast.In):
                    return contains_call
                not_port_name = _logic_not_input_port_name(self.scope)
                not_call = ast.Call(
                    func=ast.Name(id=LOGIC_NOT_NODE_CALL_NAME, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[ast.keyword(arg=not_port_name, value=contains_call)],
                )
                ast.copy_location(not_call, node)
                not_call.end_lineno = getattr(node, "end_lineno", getattr(not_call, "lineno", None))
                return not_call

            if not isinstance(right_expr, ast.Name):
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_IN_OPERATOR_CONTAINER_MUST_BE_NAME",
                        message="`in`/`not in` 的右侧必须是容器变量名（列表/字典）；请先赋值到带中文类型注解的变量，再进行包含判断",
                        node=node,
                    )
                )
                return node

            container_name = right_expr.id
            if _is_dict_var_name(container_name, self.dict_var_names):
                contains_call = ast.Call(
                    func=ast.Name(id=DICT_CONTAINS_KEY_NODE_CALL_NAME, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="字典", value=ast.Name(id=container_name, ctx=ast.Load())),
                        ast.keyword(arg="键", value=left_expr),
                    ],
                )
            else:
                contains_call = ast.Call(
                    func=ast.Name(id=LIST_CONTAINS_NODE_CALL_NAME, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="列表", value=ast.Name(id=container_name, ctx=ast.Load())),
                        ast.keyword(arg="值", value=left_expr),
                    ],
                )
            ast.copy_location(contains_call, node)
            contains_call.end_lineno = getattr(node, "end_lineno", getattr(contains_call, "lineno", None))
            if isinstance(op, ast.In):
                return contains_call
            not_port_name = _logic_not_input_port_name(self.scope)
            not_call = ast.Call(
                func=ast.Name(id=LOGIC_NOT_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg=not_port_name, value=contains_call)],
            )
            ast.copy_location(not_call, node)
            not_call.end_lineno = getattr(node, "end_lineno", getattr(not_call, "lineno", None))
            return not_call

        # is / is not 暂不支持：保持原样交由规则报错/提醒
        if isinstance(op, (ast.Is, ast.IsNot)):
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_COMPARE_IS_FORBIDDEN",
                    message="禁止使用 Python 的 `is`/`is not` 比较；请改用对应比较节点输出布尔值（或显式的布尔变量）",
                    node=node,
                )
            )
            return node

        # 其余比较暂不支持（例如 in 之外的容器比较、字符串比较等）：保持原样
        self.issues.append(
            SyntaxSugarRewriteIssue(
                code="CODE_COMPARE_UNSUPPORTED",
                message="该比较写法暂不支持转换为节点逻辑；请改用比较类节点输出布尔值，或先拆分为变量后再组合",
                node=node,
            )
        )
        return node

    def visit_BoolOp(self, node: ast.BoolOp):  # noqa: N802
        # 先处理子表达式
        values = list(getattr(node, "values", []) or [])
        rewritten_values: List[ast.expr] = []
        for value_expr in values:
            visited_value = self.visit(value_expr)
            if isinstance(visited_value, ast.expr):
                rewritten_values.append(visited_value)
            else:
                rewritten_values.append(value_expr)
        node.values = rewritten_values  # type: ignore[assignment]

        op = getattr(node, "op", None)
        if not isinstance(op, (ast.And, ast.Or)):
            return node
        if len(node.values) < 2:
            return node

        node_name = LOGIC_AND_NODE_CALL_NAME if isinstance(op, ast.And) else LOGIC_OR_NODE_CALL_NAME
        left_port, right_port = _logic_binary_input_port_names(self.scope)

        folded_expr: ast.expr = node.values[0]
        for value_expr in node.values[1:]:
            folded_expr = ast.Call(
                func=ast.Name(id=node_name, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg=left_port, value=folded_expr),
                    ast.keyword(arg=right_port, value=value_expr),
                ],
            )
            ast.copy_location(folded_expr, node)
            folded_expr.end_lineno = getattr(node, "end_lineno", getattr(folded_expr, "lineno", None))
        return folded_expr


