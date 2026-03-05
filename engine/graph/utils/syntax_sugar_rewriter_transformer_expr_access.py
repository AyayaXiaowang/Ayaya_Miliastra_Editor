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


class _GraphCodeSyntaxSugarTransformerExprAccessMixin:
    def visit_Attribute(self, node: ast.Attribute):  # noqa: N802
        """属性访问语法糖（仅在可判定为节点等价物时改写）。

        当前支持：
        - server：`math.pi` -> 【圆周率】
        - server/client：`self.owner_entity` -> 【获取自身实体】
        """
        value_expr = getattr(node, "value", None)
        visited_value_expr = self.visit(value_expr) if isinstance(value_expr, ast.expr) else None
        if isinstance(visited_value_expr, ast.expr):
            node.value = visited_value_expr  # type: ignore[assignment]
            value_expr = visited_value_expr

        # `self.owner_entity`：统一改写为节点调用【获取自身实体】。
        # 目的：
        # - 让“图所属实体”在 UI/IR 中显式表现为一个节点输出（可连线/可搜索/可定位）；
        # - 保持与大量模板中显式写法 `获取自身实体(self.game)` 一致。
        if (
            isinstance(getattr(node, "ctx", None), ast.Load)
            and isinstance(value_expr, ast.Name)
            and value_expr.id == "self"
            and str(getattr(node, "attr", "") or "") == "owner_entity"
        ):
            call_node = ast.Call(
                func=ast.Name(id="获取自身实体", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        if isinstance(value_expr, ast.Name) and value_expr.id == "math" and str(getattr(node, "attr", "") or "") == "pi":
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_MATH_PI_NOT_SUPPORTED_IN_CLIENT",
                        message="math.pi 常量语法糖仅在 server 作用域支持（会改写为【圆周率】查询节点）。client 侧请改用显式常量或放到 server 处理。",
                        node=node,
                    )
                )
                return node

            call_node = ast.Call(
                func=ast.Name(id="圆周率", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        return node

    def visit_Subscript(self, node: ast.Subscript):  # noqa: N802
        # 仅处理读取：值 = 列表[序号] / 值 = 字典[键] / 值 = 列表[start:end]
        if not isinstance(getattr(node, "ctx", None), ast.Load):
            return self.generic_visit(node)

        container_expr = getattr(node, "value", None)
        if not isinstance(container_expr, ast.Name):
            return self.generic_visit(node)

        # 列表切片语法糖：仅 server + 仅整数列表变量 + step 为空/1
        slice_node = getattr(node, "slice", None)
        if self.enable_shared_composite_sugars and self.scope == "server" and isinstance(slice_node, ast.Slice):
            list_type = str(self.list_var_type_by_name.get(container_expr.id, "") or "").strip()
            if list_type == "整数列表":
                # step 只支持 None 或 1
                step_expr = getattr(slice_node, "step", None)
                if step_expr is not None:
                    if not (isinstance(step_expr, ast.Constant) and getattr(step_expr, "value", None) == 1):
                        return self.generic_visit(node)

                lower_expr = getattr(slice_node, "lower", None)
                upper_expr = getattr(slice_node, "upper", None)

                if lower_expr is None:
                    lower_expr = ast.Constant(value=0)
                if upper_expr is None:
                    upper_expr = ast.Call(
                        func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id=container_expr.id, ctx=ast.Load())],
                        keywords=[],
                    )

                visited_lower = self.visit(lower_expr) if isinstance(lower_expr, ast.expr) else None
                visited_upper = self.visit(upper_expr) if isinstance(upper_expr, ast.expr) else None
                if isinstance(visited_lower, ast.expr):
                    lower_expr = visited_lower
                if isinstance(visited_upper, ast.expr):
                    upper_expr = visited_upper

                alias = "_共享复合_整数列表_切片"
                class_name = "整数列表_切片"
                self._require_shared_composite(alias=alias, class_name=class_name)
                return self._shared_composite_instance_call(
                    alias=alias,
                    method_name="切片",
                    keywords=[
                        ast.keyword(arg="输入列表", value=ast.Name(id=container_expr.id, ctx=ast.Load())),
                        ast.keyword(arg="开始序号", value=lower_expr if isinstance(lower_expr, ast.expr) else ast.Constant(value=0)),
                        ast.keyword(
                            arg="结束序号",
                            value=upper_expr if isinstance(upper_expr, ast.expr) else ast.Constant(value=0),
                        ),
                    ],
                    source_node=node,
                )

        index_expr = _extract_subscript_index_expr(node)
        if index_expr is None:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_SUBSCRIPT_INDEX_UNSUPPORTED",
                    message="该下标写法暂不支持转换为节点逻辑（仅支持单个下标/键访问，不支持切片/多维索引）",
                    node=node,
                )
            )
            return self.generic_visit(node)

        visited_index = self.visit(index_expr)
        if isinstance(visited_index, ast.expr):
            index_expr = visited_index

        container_name = container_expr.id
        if _is_dict_var_name(container_name, self.dict_var_names):
            call_node = ast.Call(
                func=ast.Name(id=DICT_GET_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="字典", value=ast.Name(id=container_name, ctx=ast.Load())),
                    ast.keyword(arg="键", value=index_expr),
                ],
            )
        else:
            list_port_name = _list_get_list_port_name(self.scope)
            call_node = ast.Call(
                func=ast.Name(id=LIST_GET_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg=list_port_name, value=ast.Name(id=container_name, ctx=ast.Load())),
                    ast.keyword(arg="序号", value=index_expr),
                ],
            )

        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

