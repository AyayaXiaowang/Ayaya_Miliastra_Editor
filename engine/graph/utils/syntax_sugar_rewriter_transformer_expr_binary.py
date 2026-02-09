from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from .syntax_sugar_rewriter_ast_helpers import (
    _build_positive_mod_expr,
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


class _GraphCodeSyntaxSugarTransformerExprBinaryMixin:
    # ------------------------------
    # 表达式级改写
    # ------------------------------

    def visit_BinOp(self, node: ast.BinOp):  # noqa: N802
        left_expr = getattr(node, "left", None)
        right_expr = getattr(node, "right", None)
        if not isinstance(left_expr, ast.expr) or not isinstance(right_expr, ast.expr):
            return self.generic_visit(node)

        op = getattr(node, "op", None)
        if isinstance(op, ast.Add):
            # datetime.fromtimestamp(ts).weekday() + 1 -> 根据时间戳计算星期几(ts)
            timestamp_expr: Optional[ast.expr] = None

            if (
                isinstance(left_expr, ast.Constant)
                and isinstance(getattr(left_expr, "value", None), int)
                and (not isinstance(getattr(left_expr, "value", None), bool))
                and left_expr.value == 1  # type: ignore[attr-defined]
            ):
                timestamp_expr = self._try_extract_timestamp_expr_from_datetime_fromtimestamp_method_call(
                    right_expr,
                    method_name="weekday",
                )
            elif (
                isinstance(right_expr, ast.Constant)
                and isinstance(getattr(right_expr, "value", None), int)
                and (not isinstance(getattr(right_expr, "value", None), bool))
                and right_expr.value == 1  # type: ignore[attr-defined]
            ):
                timestamp_expr = self._try_extract_timestamp_expr_from_datetime_fromtimestamp_method_call(
                    left_expr,
                    method_name="weekday",
                )

            if timestamp_expr is not None:
                if self.scope != "server":
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_DATETIME_WEEKDAY_PLUS_ONE_NOT_SUPPORTED_IN_CLIENT",
                            message="datetime.fromtimestamp(ts).weekday() + 1 语法糖仅在 server 作用域支持（会改写为【根据时间戳计算星期几】）。",
                            node=node,
                        )
                    )
                else:
                    visited_timestamp = self.visit(timestamp_expr)
                    if isinstance(visited_timestamp, ast.expr):
                        timestamp_expr = visited_timestamp

                    call_expr = ast.Call(
                        func=ast.Name(id="根据时间戳计算星期几", ctx=ast.Load()),
                        args=[_build_self_game_expr()],
                        keywords=[ast.keyword(arg="时间戳", value=timestamp_expr)],
                    )
                    ast.copy_location(call_expr, node)
                    call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                    return call_expr

        # 位读写折叠（仅 server，且仅严格 AST 形态匹配；必须在子表达式被改写前执行）
        if self.scope == "server":
            rewritten_bit_read = self._try_rewrite_bit_read_to_node_call(node)
            if rewritten_bit_read is not None:
                return rewritten_bit_read
            rewritten_bit_write = self._try_rewrite_bit_write_inline_to_node_call(node)
            if rewritten_bit_write is not None:
                return rewritten_bit_write

        # 先处理子表达式
        visited_left = self.visit(left_expr)
        if isinstance(visited_left, ast.expr):
            left_expr = visited_left
        visited_right = self.visit(right_expr)
        if isinstance(visited_right, ast.expr):
            right_expr = visited_right

        if not isinstance(op, ast.operator):
            return node

        # 把已改写过的子表达式写回，确保在“不支持/不改写”路径下不会丢失子节点改写结果
        node.left = left_expr  # type: ignore[assignment]
        node.right = right_expr  # type: ignore[assignment]

        left_is_vector = self._is_vector_expr(left_expr)
        right_is_vector = self._is_vector_expr(right_expr)

        # 三维向量运算符语法糖（尽量单节点，且仅在能稳定判定为向量时才改写）
        if isinstance(op, ast.Add) and left_is_vector and right_is_vector:
            call_expr = ast.Call(
                func=ast.Name(id="三维向量加法", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="三维向量1", value=left_expr),
                    ast.keyword(arg="三维向量2", value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        if isinstance(op, ast.Sub) and left_is_vector and right_is_vector:
            call_expr = ast.Call(
                func=ast.Name(id="三维向量减法", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="三维向量1", value=left_expr),
                    ast.keyword(arg="三维向量2", value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        if isinstance(op, ast.MatMult) and left_is_vector and right_is_vector:
            call_expr = ast.Call(
                func=ast.Name(id="三维向量内积", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="三维向量1", value=left_expr),
                    ast.keyword(arg="三维向量2", value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        if isinstance(op, ast.BitXor) and left_is_vector and right_is_vector:
            call_expr = ast.Call(
                func=ast.Name(id="三维向量外积", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="三维向量1", value=left_expr),
                    ast.keyword(arg="三维向量2", value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        # 布尔异或（逻辑异或）：仅当左右两侧都能稳定识别为“布尔值”时才改写，避免与按位异或/向量外积产生歧义。
        if isinstance(op, ast.BitXor) and self._is_bool_expr(left_expr) and self._is_bool_expr(right_expr):
            input_port_1, input_port_2 = _logic_binary_input_port_names(self.scope)
            call_expr = ast.Call(
                func=ast.Name(id="逻辑异或运算", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg=input_port_1, value=left_expr),
                    ast.keyword(arg=input_port_2, value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        if isinstance(op, ast.Mult) and (left_is_vector != right_is_vector):
            vector_expr = left_expr if left_is_vector else right_expr
            scale_expr: ast.expr = right_expr if left_is_vector else left_expr
            if isinstance(scale_expr, ast.Constant) and isinstance(getattr(scale_expr, "value", None), int) and not isinstance(
                getattr(scale_expr, "value", None),
                bool,
            ):
                converted = ast.Constant(value=float(scale_expr.value))  # type: ignore[attr-defined]
                ast.copy_location(converted, scale_expr)
                scale_expr = converted

            call_expr = ast.Call(
                func=ast.Name(id="三维向量缩放", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="三维向量", value=vector_expr),
                    ast.keyword(arg="缩放倍率", value=scale_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        node_name = _arith_node_name(op)
        if node_name is not None:
            call_expr = ast.Call(
                func=ast.Name(id=node_name, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="左值", value=left_expr),
                    ast.keyword(arg="右值", value=right_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        # 扩展（仅 server）：模/幂/位运算
        if self.scope == "server":
            if isinstance(op, ast.Mod):
                # 正模语法糖（server）：
                # - 普通节点图：优先改写为共享复合节点调用（避免在业务脚本里展开多步运算）
                # - 复合节点文件内部：禁止嵌套复合节点，因此回退为节点链模板
                if self.enable_shared_composite_sugars:
                    class_name = "整数_正模运算"
                    alias = "_共享复合_整数_正模运算"
                    self._require_shared_composite(alias=alias, class_name=class_name)
                    return self._shared_composite_instance_call(
                        alias=alias,
                        method_name="计算",
                        keywords=[
                            ast.keyword(arg="被模数", value=left_expr),
                            ast.keyword(arg="模数", value=right_expr),
                        ],
                        source_node=node,
                    )

                # 回退：节点链模板 ((a % m) + m) % m
                return _build_positive_mod_expr(left_expr, right_expr, source_node=node)
            if isinstance(op, ast.Pow):
                call_expr = ast.Call(
                    func=ast.Name(id="幂运算", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="底数", value=left_expr),
                        ast.keyword(arg="指数", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr
            if isinstance(op, ast.BitAnd):
                call_expr = ast.Call(
                    func=ast.Name(id="按位与", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="值1", value=left_expr),
                        ast.keyword(arg="值2", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr
            if isinstance(op, ast.BitOr):
                call_expr = ast.Call(
                    func=ast.Name(id="按位或", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="值1", value=left_expr),
                        ast.keyword(arg="值2", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr
            if isinstance(op, ast.BitXor):
                call_expr = ast.Call(
                    func=ast.Name(id="按位异或", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="值1", value=left_expr),
                        ast.keyword(arg="值2", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr
            if isinstance(op, ast.LShift):
                call_expr = ast.Call(
                    func=ast.Name(id="左移运算", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="值", value=left_expr),
                        ast.keyword(arg="左移位数", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr
            if isinstance(op, ast.RShift):
                call_expr = ast.Call(
                    func=ast.Name(id="右移运算", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="值", value=left_expr),
                        ast.keyword(arg="右移位数", value=right_expr),
                    ],
                )
                ast.copy_location(call_expr, node)
                call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                return call_expr

            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_BIN_OP_UNSUPPORTED",
                    message="不支持该二元运算符；server 语法糖仅支持 +、-、*、/、%、**、&、|、^、<<、>>（请改用对应运算节点或拆分为多步）",
                    node=node,
                )
            )
            return node

        self.issues.append(
            SyntaxSugarRewriteIssue(
                code="CODE_BIN_OP_UNSUPPORTED",
                message="不支持该二元运算符；client 语法糖仅支持 +、-、*、/（其余运算请改用可用节点或放到 server 处理）",
                node=node,
            )
        )
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp):  # noqa: N802
        operand_expr = getattr(node, "operand", None)
        if not isinstance(operand_expr, ast.expr):
            return self.generic_visit(node)

        visited_operand = self.visit(operand_expr)
        if isinstance(visited_operand, ast.expr):
            operand_expr = visited_operand
            node.operand = operand_expr  # type: ignore[assignment]

        op = getattr(node, "op", None)
        if isinstance(op, ast.Invert):
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_BIT_INVERT_NOT_SUPPORTED_IN_CLIENT",
                        message="按位取补运算 `~x` 语法糖仅在 server 作用域支持（会改写为【按位取补运算】）。",
                        node=node,
                    )
                )
                return node

            call_expr = ast.Call(
                func=ast.Name(id="按位取补运算", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="值", value=operand_expr)],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        # 逻辑非：not 条件 -> 【逻辑非运算】
        if isinstance(op, ast.Not):
            not_port_name = _logic_not_input_port_name(self.scope)
            call_expr = ast.Call(
                func=ast.Name(id=LOGIC_NOT_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg=not_port_name, value=operand_expr)],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        # 一元正号：+x -> x
        if isinstance(op, ast.UAdd):
            return operand_expr

        # 一元负号：-x -> 0 - x（改写为【减法运算】，避免保留 UnaryOp）
        if isinstance(op, ast.USub):
            zero_value: ast.Constant
            if isinstance(operand_expr, ast.Constant) and isinstance(getattr(operand_expr, "value", None), float):
                zero_value = ast.Constant(value=0.0)
            elif isinstance(operand_expr, ast.Name) and self._get_var_type_text(operand_expr.id) == "浮点数":
                zero_value = ast.Constant(value=0.0)
            else:
                zero_value = ast.Constant(value=0)
            ast.copy_location(zero_value, node)

            call_expr = ast.Call(
                func=ast.Name(id=SUBTRACT_NODE_CALL_NAME, ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="左值", value=zero_value),
                    ast.keyword(arg="右值", value=operand_expr),
                ],
            )
            ast.copy_location(call_expr, node)
            call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
            return call_expr

        return node

