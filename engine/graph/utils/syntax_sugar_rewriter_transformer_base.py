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


class _GraphCodeSyntaxSugarTransformerBase:
    def __init__(
        self,
        *,
        scope: str,
        list_var_names: Set[str],
        dict_var_names: Set[str],
        used_names: Set[str],
        list_var_type_by_name: Dict[str, str],
        var_type_by_name: Dict[str, str],
        enable_shared_composite_sugars: bool = False,
    ):
        self.scope = _normalize_scope(scope)
        self.list_var_names = set(list_var_names or set())
        self.dict_var_names = set(dict_var_names or set())
        self.used_names: Set[str] = set(used_names or set())
        self.list_var_type_by_name: Dict[str, str] = dict(list_var_type_by_name or {})
        self.var_type_by_name: Dict[str, str] = dict(var_type_by_name or {})
        self.issues: List[SyntaxSugarRewriteIssue] = []
        self._temp_counter = 1
        self.enable_shared_composite_sugars: bool = bool(enable_shared_composite_sugars)

        # 共享复合节点自动注入需求：{alias: class_name}
        # 由各 visit_* 在需要时填充，rewrite_graph_code_syntax_sugars 会把它注入到 class.__init__。
        self.required_shared_composites: Dict[str, str] = {}

    def _require_shared_composite(self, *, alias: str, class_name: str) -> None:
        alias_text = str(alias or "").strip()
        class_text = str(class_name or "").strip()
        if not alias_text or not class_text:
            return
        self.required_shared_composites.setdefault(alias_text, class_text)

    def _shared_composite_instance_call(
        self,
        *,
        alias: str,
        method_name: str,
        keywords: List[ast.keyword],
        source_node: ast.AST,
    ) -> ast.Call:
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr=alias, ctx=ast.Load()),
                attr=method_name,
                ctx=ast.Load(),
            ),
            args=[],
            keywords=keywords,
        )
        ast.copy_location(call_node, source_node)
        call_node.end_lineno = getattr(source_node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    def _get_var_type_text(self, name_id: str) -> str:
        return str(self.var_type_by_name.get(str(name_id or ""), "") or "").strip()

    def _is_vector_expr(self, expr: ast.AST) -> bool:
        """判断表达式是否可稳定视为“三维向量”。

        约定：仅在类型信息足够确定时才返回 True，避免把普通数值表达式误判为向量。
        """
        if isinstance(expr, ast.Name):
            return self._get_var_type_text(expr.id) == "三维向量"
        if isinstance(expr, ast.Call):
            func = getattr(expr, "func", None)
            if isinstance(func, ast.Name):
                # 常见“返回三维向量”的节点调用（按节点库命名）
                return func.id in {
                    "创建三维向量",
                    "三维向量加法",
                    "三维向量减法",
                    "三维向量外积",
                    "三维向量缩放",
                    "三维向量旋转",
                    "三维向量归一化",
                }
        return False

    def _is_bool_expr(self, expr: ast.AST) -> bool:
        """判断表达式是否可稳定视为“布尔值”。

        约定：只在“类型信息或节点调用语义足够明确”时返回 True，避免把按位异或/向量外积误判为逻辑异或。
        """
        if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), bool):
            return True
        if isinstance(expr, ast.Name):
            return self._get_var_type_text(expr.id) == "布尔值"
        if isinstance(expr, ast.Call):
            func = getattr(expr, "func", None)
            if isinstance(func, ast.Name):
                call_name = func.id
                if call_name in {
                    LOGIC_AND_NODE_CALL_NAME,
                    LOGIC_OR_NODE_CALL_NAME,
                    LOGIC_NOT_NODE_CALL_NAME,
                    "逻辑异或运算",
                    LIST_CONTAINS_NODE_CALL_NAME,
                    DICT_CONTAINS_KEY_NODE_CALL_NAME,
                    EQUAL_NODE_CALL_NAME,
                }:
                    return True

                compare_node_names: Set[str] = set()
                for compare_op in (ast.Gt(), ast.GtE(), ast.Lt(), ast.LtE()):
                    compare_name = _numeric_compare_node_name(self.scope, compare_op)
                    if compare_name:
                        compare_node_names.add(compare_name)
                if call_name in compare_node_names:
                    return True
        return False

    def _is_int_constant(self, expr: Optional[ast.AST], expected_value: int) -> bool:
        if not isinstance(expr, ast.Constant):
            return False
        value = getattr(expr, "value", None)
        return isinstance(value, int) and (not isinstance(value, bool)) and value == expected_value

    def _is_same_expr(self, left: ast.AST, right: ast.AST) -> bool:
        return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)

    def _is_name_used_in_any_stmt(self, name_id: str, statements: List[ast.stmt]) -> bool:
        for stmt in list(statements or []):
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Name) and sub.id == name_id:
                    return True
        return False

    def _try_extract_end_and_start_from_end_minus_start_plus_one(
        self,
        expr: ast.AST,
    ) -> Optional[Tuple[ast.expr, ast.expr]]:
        """从 `(结束位 - 起始位 + 1)` 形态提取 (结束位, 起始位)。"""
        if not isinstance(expr, ast.BinOp):
            return None
        if not isinstance(getattr(expr, "op", None), ast.Add):
            return None
        right_expr = getattr(expr, "right", None)
        if not self._is_int_constant(right_expr, 1):
            return None
        left_expr = getattr(expr, "left", None)
        if not (isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.Sub)):
            return None
        end_expr = getattr(left_expr, "left", None)
        start_expr = getattr(left_expr, "right", None)
        if isinstance(end_expr, ast.expr) and isinstance(start_expr, ast.expr):
            return end_expr, start_expr
        return None

    def _try_extract_end_and_start_from_bit_range_mask_expr(self, expr: ast.AST) -> Optional[Tuple[ast.expr, ast.expr]]:
        """从 `((1 << (结束位 - 起始位 + 1)) - 1)` 形态提取 (结束位, 起始位)。"""
        if not (isinstance(expr, ast.BinOp) and isinstance(getattr(expr, "op", None), ast.Sub)):
            return None
        right_expr = getattr(expr, "right", None)
        if not self._is_int_constant(right_expr, 1):
            return None
        left_expr = getattr(expr, "left", None)
        if not (isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.LShift)):
            return None
        one_expr = getattr(left_expr, "left", None)
        if not self._is_int_constant(one_expr, 1):
            return None
        length_expr = getattr(left_expr, "right", None)
        if not isinstance(length_expr, ast.AST):
            return None
        return self._try_extract_end_and_start_from_end_minus_start_plus_one(length_expr)

    def _try_extract_start_and_end_from_shifted_bit_range_mask_expr(self, expr: ast.AST) -> Optional[Tuple[ast.expr, ast.expr]]:
        """从 `(((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)` 形态提取 (起始位, 结束位)。"""
        if not (isinstance(expr, ast.BinOp) and isinstance(getattr(expr, "op", None), ast.LShift)):
            return None
        mask_inner_expr = getattr(expr, "left", None)
        start_expr = getattr(expr, "right", None)
        if not isinstance(mask_inner_expr, ast.AST):
            return None
        if not isinstance(start_expr, ast.expr):
            return None
        extracted = self._try_extract_end_and_start_from_bit_range_mask_expr(mask_inner_expr)
        if extracted is None:
            return None
        end_expr, start_expr_in_len = extracted
        if not self._is_same_expr(start_expr, start_expr_in_len):
            return None
        return start_expr, end_expr

    def _try_rewrite_bit_read_to_node_call(self, node: ast.BinOp) -> Optional[ast.expr]:
        """按位读出折叠（仅 server，且仅严格 AST 形态匹配）。"""
        op = getattr(node, "op", None)
        left_expr = getattr(node, "left", None)
        right_expr = getattr(node, "right", None)
        if not isinstance(left_expr, ast.expr) or not isinstance(right_expr, ast.expr):
            return None

        # 形态1：((值 >> 起始位) & ((1 << (结束位 - 起始位 + 1)) - 1))
        if isinstance(op, ast.BitAnd) and isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.RShift):
            value_expr = getattr(left_expr, "left", None)
            start_expr = getattr(left_expr, "right", None)
            if isinstance(value_expr, ast.expr) and isinstance(start_expr, ast.expr):
                extracted = self._try_extract_end_and_start_from_bit_range_mask_expr(right_expr)
                if extracted is not None:
                    end_expr, start_expr_in_len = extracted
                    if self._is_same_expr(start_expr, start_expr_in_len):
                        visited_value = self.visit(value_expr)
                        if isinstance(visited_value, ast.expr):
                            value_expr = visited_value
                        visited_start = self.visit(start_expr)
                        if isinstance(visited_start, ast.expr):
                            start_expr = visited_start
                        visited_end = self.visit(end_expr)
                        if isinstance(visited_end, ast.expr):
                            end_expr = visited_end

                        call_expr = ast.Call(
                            func=ast.Name(id="按位读出", ctx=ast.Load()),
                            args=[_build_self_game_expr()],
                            keywords=[
                                ast.keyword(arg="值", value=value_expr),
                                ast.keyword(arg="读出起始位", value=start_expr),
                                ast.keyword(arg="读出结束位", value=end_expr),
                            ],
                        )
                        ast.copy_location(call_expr, node)
                        call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                        return call_expr

        # 形态2：(((值 & (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)) >> 起始位))
        if isinstance(op, ast.RShift) and isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.BitAnd):
            start_expr = right_expr
            value_expr = getattr(left_expr, "left", None)
            mask_expr = getattr(left_expr, "right", None)
            if isinstance(start_expr, ast.expr) and isinstance(value_expr, ast.expr) and isinstance(mask_expr, ast.AST):
                extracted = self._try_extract_start_and_end_from_shifted_bit_range_mask_expr(mask_expr)
                if extracted is not None:
                    mask_start_expr, end_expr = extracted
                    if self._is_same_expr(start_expr, mask_start_expr):
                        visited_value = self.visit(value_expr)
                        if isinstance(visited_value, ast.expr):
                            value_expr = visited_value
                        visited_start = self.visit(start_expr)
                        if isinstance(visited_start, ast.expr):
                            start_expr = visited_start
                        visited_end = self.visit(end_expr)
                        if isinstance(visited_end, ast.expr):
                            end_expr = visited_end

                        call_expr = ast.Call(
                            func=ast.Name(id="按位读出", ctx=ast.Load()),
                            args=[_build_self_game_expr()],
                            keywords=[
                                ast.keyword(arg="值", value=value_expr),
                                ast.keyword(arg="读出起始位", value=start_expr),
                                ast.keyword(arg="读出结束位", value=end_expr),
                            ],
                        )
                        ast.copy_location(call_expr, node)
                        call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
                        return call_expr

        return None

    def _try_rewrite_bit_write_inline_to_node_call(self, node: ast.BinOp) -> Optional[ast.expr]:
        """按位写入折叠（仅 server，且仅严格 AST 形态匹配，mask 内联版）。"""
        if not isinstance(getattr(node, "op", None), ast.BitOr):
            return None

        left_expr = getattr(node, "left", None)
        right_expr = getattr(node, "right", None)
        if not isinstance(left_expr, ast.expr) or not isinstance(right_expr, ast.expr):
            return None
        if not (isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.BitAnd)):
            return None
        if not (isinstance(right_expr, ast.BinOp) and isinstance(getattr(right_expr, "op", None), ast.LShift)):
            return None

        target_expr = getattr(left_expr, "left", None)
        invert_expr = getattr(left_expr, "right", None)
        write_value_expr = getattr(right_expr, "left", None)
        start_expr = getattr(right_expr, "right", None)
        if not (isinstance(target_expr, ast.expr) and isinstance(write_value_expr, ast.expr) and isinstance(start_expr, ast.expr)):
            return None
        if not (isinstance(invert_expr, ast.UnaryOp) and isinstance(getattr(invert_expr, "op", None), ast.Invert)):
            return None
        mask_operand = getattr(invert_expr, "operand", None)
        if not isinstance(mask_operand, ast.AST):
            return None

        extracted = self._try_extract_start_and_end_from_shifted_bit_range_mask_expr(mask_operand)
        if extracted is None:
            return None
        mask_start_expr, end_expr = extracted
        if not self._is_same_expr(start_expr, mask_start_expr):
            return None

        visited_target = self.visit(target_expr)
        if isinstance(visited_target, ast.expr):
            target_expr = visited_target
        visited_write_value = self.visit(write_value_expr)
        if isinstance(visited_write_value, ast.expr):
            write_value_expr = visited_write_value
        visited_start = self.visit(start_expr)
        if isinstance(visited_start, ast.expr):
            start_expr = visited_start
        visited_end = self.visit(end_expr)
        if isinstance(visited_end, ast.expr):
            end_expr = visited_end

        call_expr = ast.Call(
            func=ast.Name(id="按位写入", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="被写入值", value=target_expr),
                ast.keyword(arg="写入值", value=write_value_expr),
                ast.keyword(arg="写入起始位", value=start_expr),
                ast.keyword(arg="写入结束位", value=end_expr),
            ],
        )
        ast.copy_location(call_expr, node)
        call_expr.end_lineno = getattr(node, "end_lineno", getattr(call_expr, "lineno", None))
        return call_expr

    def _try_extract_mask_assignment_info(self, stmt: ast.stmt) -> Optional[Tuple[str, ast.expr, ast.expr]]:
        """从 `mask = (((1 << (结束位 - 起始位 + 1)) - 1) << 起始位)` 形态提取 (mask_name, 起始位, 结束位)。"""
        mask_name: Optional[str] = None
        value_expr: Optional[ast.AST] = None

        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                return None
            mask_name = targets[0].id
            value_expr = getattr(stmt, "value", None)
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if not isinstance(target, ast.Name):
                return None
            mask_name = target.id
            value_expr = getattr(stmt, "value", None)
        else:
            return None

        if not isinstance(mask_name, str) or not mask_name:
            return None
        if not isinstance(value_expr, ast.AST):
            return None

        extracted = self._try_extract_start_and_end_from_shifted_bit_range_mask_expr(value_expr)
        if extracted is None:
            return None
        start_expr, end_expr = extracted
        return mask_name, start_expr, end_expr

    def _try_extract_bit_write_expr_using_mask_name(
        self,
        expr: ast.AST,
        *,
        mask_name: str,
    ) -> Optional[Tuple[ast.expr, ast.expr, ast.expr]]:
        """从 `(被写入值 & ~mask) | (写入值 << 起始位)` 形态提取 (被写入值, 写入值, 起始位)。"""
        if not (isinstance(expr, ast.BinOp) and isinstance(getattr(expr, "op", None), ast.BitOr)):
            return None
        left_expr = getattr(expr, "left", None)
        right_expr = getattr(expr, "right", None)
        if not (isinstance(left_expr, ast.BinOp) and isinstance(getattr(left_expr, "op", None), ast.BitAnd)):
            return None
        if not (isinstance(right_expr, ast.BinOp) and isinstance(getattr(right_expr, "op", None), ast.LShift)):
            return None

        target_expr = getattr(left_expr, "left", None)
        invert_expr = getattr(left_expr, "right", None)
        write_value_expr = getattr(right_expr, "left", None)
        start_expr = getattr(right_expr, "right", None)
        if not (isinstance(target_expr, ast.expr) and isinstance(write_value_expr, ast.expr) and isinstance(start_expr, ast.expr)):
            return None
        if not (isinstance(invert_expr, ast.UnaryOp) and isinstance(getattr(invert_expr, "op", None), ast.Invert)):
            return None
        mask_operand = getattr(invert_expr, "operand", None)
        if not (isinstance(mask_operand, ast.Name) and mask_operand.id == mask_name):
            return None
        return target_expr, write_value_expr, start_expr

    def _try_fold_bit_write_two_step_pair(
        self,
        mask_stmt: ast.stmt,
        write_stmt: ast.stmt,
        remaining_stmts: List[ast.stmt],
    ) -> Optional[ast.stmt]:
        """按位写入折叠（仅 server，严格两步模板）：mask = ...; 结果 = (被写入值 & ~mask) | (写入值 << 起始位)。"""
        extracted_mask = self._try_extract_mask_assignment_info(mask_stmt)
        if extracted_mask is None:
            return None
        mask_name, expected_start_expr, end_expr = extracted_mask
        if self._is_name_used_in_any_stmt(mask_name, remaining_stmts):
            return None

        write_value_expr: Optional[ast.AST] = None
        if isinstance(write_stmt, ast.Assign):
            write_value_expr = getattr(write_stmt, "value", None)
        elif isinstance(write_stmt, ast.AnnAssign):
            write_value_expr = getattr(write_stmt, "value", None)
        else:
            return None
        if not isinstance(write_value_expr, ast.AST):
            return None

        extracted_write = self._try_extract_bit_write_expr_using_mask_name(write_value_expr, mask_name=mask_name)
        if extracted_write is None:
            return None
        target_expr, write_value, start_expr = extracted_write
        if not self._is_same_expr(start_expr, expected_start_expr):
            return None

        call_expr = ast.Call(
            func=ast.Name(id="按位写入", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="被写入值", value=target_expr),
                ast.keyword(arg="写入值", value=write_value),
                ast.keyword(arg="写入起始位", value=start_expr),
                ast.keyword(arg="写入结束位", value=end_expr),
            ],
        )
        ast.copy_location(call_expr, write_value_expr)
        call_expr.end_lineno = getattr(write_value_expr, "end_lineno", getattr(call_expr, "lineno", None))

        if isinstance(write_stmt, ast.Assign):
            write_stmt.value = call_expr  # type: ignore[assignment]
            return write_stmt
        if isinstance(write_stmt, ast.AnnAssign):
            write_stmt.value = call_expr  # type: ignore[assignment]
            return write_stmt
        return None

    def _try_extract_timestamp_expr_from_datetime_fromtimestamp_call(self, expr: ast.AST) -> Optional[ast.expr]:
        """尝试从 `datetime.fromtimestamp(ts)` / `datetime.datetime.fromtimestamp(ts)` 提取时间戳表达式 ts。"""
        if not isinstance(expr, ast.Call):
            return None
        func_node = getattr(expr, "func", None)
        if not isinstance(func_node, ast.Attribute):
            return None
        if str(getattr(func_node, "attr", "") or "") != "fromtimestamp":
            return None

        positional_args = list(getattr(expr, "args", []) or [])
        keywords = list(getattr(expr, "keywords", []) or [])
        if keywords:
            return None
        if len(positional_args) != 1:
            return None
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            return None

        base = getattr(func_node, "value", None)
        if isinstance(base, ast.Name) and base.id == "datetime":
            return positional_args[0]
        if isinstance(base, ast.Attribute) and base.attr == "datetime":
            base_value = getattr(base, "value", None)
            if isinstance(base_value, ast.Name) and base_value.id == "datetime":
                return positional_args[0]
        return None

    def _try_extract_timestamp_expr_from_datetime_fromtimestamp_method_call(
        self,
        expr: ast.AST,
        *,
        method_name: str,
    ) -> Optional[ast.expr]:
        """尝试从 `datetime.fromtimestamp(ts).<method>()` 形式提取 ts。"""
        if not isinstance(expr, ast.Call):
            return None
        positional_args = list(getattr(expr, "args", []) or [])
        keywords = list(getattr(expr, "keywords", []) or [])
        if positional_args or keywords:
            return None
        func_node = getattr(expr, "func", None)
        if not (isinstance(func_node, ast.Attribute) and str(getattr(func_node, "attr", "") or "") == method_name):
            return None
        base_expr = getattr(func_node, "value", None)
        if not isinstance(base_expr, ast.AST):
            return None
        return self._try_extract_timestamp_expr_from_datetime_fromtimestamp_call(base_expr)

    def _try_extract_datetime_constructor_six_args(self, expr: ast.AST) -> Optional[Tuple[ast.expr, ast.expr, ast.expr, ast.expr, ast.expr, ast.expr]]:
        """尝试从 `datetime(y,m,d,h,mi,s)` / `datetime.datetime(...)` 提取 6 个位置参数。"""
        if not isinstance(expr, ast.Call):
            return None
        func_node = getattr(expr, "func", None)
        is_datetime_constructor = False
        if isinstance(func_node, ast.Name) and func_node.id == "datetime":
            is_datetime_constructor = True
        if isinstance(func_node, ast.Attribute) and func_node.attr == "datetime":
            func_base = getattr(func_node, "value", None)
            if isinstance(func_base, ast.Name) and func_base.id == "datetime":
                is_datetime_constructor = True
        if not is_datetime_constructor:
            return None

        positional_args = list(getattr(expr, "args", []) or [])
        keywords = list(getattr(expr, "keywords", []) or [])
        if keywords:
            return None
        if len(positional_args) != 6:
            return None
        if any(isinstance(arg, ast.Starred) for arg in positional_args):
            return None
        if not all(isinstance(arg, ast.expr) for arg in positional_args):
            return None
        return (
            positional_args[0],
            positional_args[1],
            positional_args[2],
            positional_args[3],
            positional_args[4],
            positional_args[5],
        )

    def _try_rewrite_time_time_call(self, node: ast.Call) -> Optional[ast.expr]:
        """time.time() -> 【查询时间戳（UTC+0时区）】（仅 server）。"""
        func_node = getattr(node, "func", None)
        if not isinstance(func_node, ast.Attribute):
            return None
        if str(getattr(func_node, "attr", "") or "") != "time":
            return None
        base_expr = getattr(func_node, "value", None)
        if not (isinstance(base_expr, ast.Name) and base_expr.id == "time"):
            return None

        positional_args = list(getattr(node, "args", []) or [])
        keywords = list(getattr(node, "keywords", []) or [])
        if positional_args or keywords:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_TIME_TIME_CALL_ARGS_INVALID",
                    message="time.time() 语法糖不支持任何入参（请使用 `time.time()`）。",
                    node=node,
                )
            )
            return None

        if self.scope != "server":
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_TIME_TIME_NOT_SUPPORTED_IN_CLIENT",
                    message="time.time() 语法糖仅在 server 作用域支持（会改写为【查询时间戳（UTC+0时区）】）。client 侧缺少等价节点。",
                    node=node,
                )
            )
            return None

        call_node = ast.Call(
            func=ast.Name(id="查询时间戳_UTC_0时区", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[],
        )
        ast.copy_location(call_node, node)
        call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
        return call_node

    def _try_rewrite_datetime_calls(self, node: ast.Call) -> Optional[ast.expr]:
        """datetime 相关语法糖（仅 server）：fromtimestamp/weekday/isoweekday/timestamp。"""
        func_node = getattr(node, "func", None)
        if not isinstance(func_node, ast.Attribute):
            return None
        method_name = str(getattr(func_node, "attr", "") or "")

        # datetime.fromtimestamp(ts) / datetime.datetime.fromtimestamp(ts)
        if method_name == "fromtimestamp":
            timestamp_expr = self._try_extract_timestamp_expr_from_datetime_fromtimestamp_call(node)
            if timestamp_expr is None:
                return None

            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DATETIME_FROMTIMESTAMP_NOT_SUPPORTED_IN_CLIENT",
                        message="datetime.fromtimestamp(ts) 语法糖仅在 server 作用域支持（会改写为【根据时间戳计算格式化时间】）。client 侧缺少等价节点。",
                        node=node,
                    )
                )
                return None

            visited_timestamp = self.visit(timestamp_expr)
            if isinstance(visited_timestamp, ast.expr):
                timestamp_expr = visited_timestamp

            call_node = ast.Call(
                func=ast.Name(id="根据时间戳计算格式化时间", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="时间戳", value=timestamp_expr)],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        # datetime.fromtimestamp(ts).isoweekday() -> 根据时间戳计算星期几(ts)
        if method_name == "isoweekday":
            timestamp_expr = self._try_extract_timestamp_expr_from_datetime_fromtimestamp_method_call(node, method_name="isoweekday")
            if timestamp_expr is None:
                return None

            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DATETIME_ISOWEEKDAY_NOT_SUPPORTED_IN_CLIENT",
                        message="datetime.fromtimestamp(ts).isoweekday() 语法糖仅在 server 作用域支持（会改写为【根据时间戳计算星期几】）。",
                        node=node,
                    )
                )
                return None

            visited_timestamp = self.visit(timestamp_expr)
            if isinstance(visited_timestamp, ast.expr):
                timestamp_expr = visited_timestamp

            call_node = ast.Call(
                func=ast.Name(id="根据时间戳计算星期几", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="时间戳", value=timestamp_expr)],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        # datetime.fromtimestamp(ts).weekday() -> 根据时间戳计算星期几(ts) - 1
        if method_name == "weekday":
            timestamp_expr = self._try_extract_timestamp_expr_from_datetime_fromtimestamp_method_call(node, method_name="weekday")
            if timestamp_expr is None:
                return None

            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DATETIME_WEEKDAY_NOT_SUPPORTED_IN_CLIENT",
                        message="datetime.fromtimestamp(ts).weekday() 语法糖仅在 server 作用域支持（会改写为【根据时间戳计算星期几】再减 1）。",
                        node=node,
                    )
                )
                return None

            visited_timestamp = self.visit(timestamp_expr)
            if isinstance(visited_timestamp, ast.expr):
                timestamp_expr = visited_timestamp

            isoweekday_call = ast.Call(
                func=ast.Name(id="根据时间戳计算星期几", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="时间戳", value=timestamp_expr)],
            )
            ast.copy_location(isoweekday_call, node)

            weekday_call = ast.Call(
                func=ast.Name(id="减法运算", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="左值", value=isoweekday_call),
                    ast.keyword(arg="右值", value=ast.Constant(value=1)),
                ],
            )
            ast.copy_location(weekday_call, node)
            weekday_call.end_lineno = getattr(node, "end_lineno", getattr(weekday_call, "lineno", None))
            return weekday_call

        # datetime(...).timestamp() -> 根据格式化时间计算时间戳
        if method_name == "timestamp":
            positional_args = list(getattr(node, "args", []) or [])
            keywords = list(getattr(node, "keywords", []) or [])
            if positional_args or keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DATETIME_TIMESTAMP_CALL_ARGS_INVALID",
                        message="datetime(...).timestamp() 语法糖不支持任何入参（请使用 `datetime(...).timestamp()`）。",
                        node=node,
                    )
                )
                return None

            base_expr = getattr(func_node, "value", None)
            if not isinstance(base_expr, ast.AST):
                return None
            datetime_args = self._try_extract_datetime_constructor_six_args(base_expr)
            if datetime_args is None:
                return None

            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DATETIME_TIMESTAMP_NOT_SUPPORTED_IN_CLIENT",
                        message="datetime(...).timestamp() 语法糖仅在 server 作用域支持（会改写为【根据格式化时间计算时间戳】）。client 侧缺少等价节点。",
                        node=node,
                    )
                )
                return None

            year_expr, month_expr, day_expr, hour_expr, minute_expr, second_expr = datetime_args
            visited_year = self.visit(year_expr)
            if isinstance(visited_year, ast.expr):
                year_expr = visited_year
            visited_month = self.visit(month_expr)
            if isinstance(visited_month, ast.expr):
                month_expr = visited_month
            visited_day = self.visit(day_expr)
            if isinstance(visited_day, ast.expr):
                day_expr = visited_day
            visited_hour = self.visit(hour_expr)
            if isinstance(visited_hour, ast.expr):
                hour_expr = visited_hour
            visited_minute = self.visit(minute_expr)
            if isinstance(visited_minute, ast.expr):
                minute_expr = visited_minute
            visited_second = self.visit(second_expr)
            if isinstance(visited_second, ast.expr):
                second_expr = visited_second

            call_node = ast.Call(
                func=ast.Name(id="根据格式化时间计算时间戳", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="年", value=year_expr),
                    ast.keyword(arg="月", value=month_expr),
                    ast.keyword(arg="日", value=day_expr),
                    ast.keyword(arg="时", value=hour_expr),
                    ast.keyword(arg="分", value=minute_expr),
                    ast.keyword(arg="秒", value=second_expr),
                ],
            )
            ast.copy_location(call_node, node)
            call_node.end_lineno = getattr(node, "end_lineno", getattr(call_node, "lineno", None))
            return call_node

        return None

    def _next_temp_enumerate_length_var_name(self, lineno: Optional[int]) -> str:
        line_part = int(lineno) if isinstance(lineno, int) and lineno > 0 else 0
        while True:
            candidate = f"__auto_enumerate_length_for_{line_part}_{self._temp_counter}"
            self._temp_counter += 1
            if candidate in self.used_names:
                continue
            self.used_names.add(candidate)
            return candidate

    def _next_temp_min_max_list_var_name(self, lineno: Optional[int]) -> str:
        """为 client 的 max(a,b)/min(a,b) 改写生成临时列表变量名。

        背景：client 侧用“拼装列表 → 获取列表最大值/最小值”表达两值 max/min；
        但拼装列表输出为“泛型列表”，若没有中间带注解的列表变量承接，会触发结构校验
        的“端口类型未实例化（仍为泛型）”。
        """
        line_part = int(lineno) if isinstance(lineno, int) and lineno > 0 else 0
        while True:
            candidate = f"__auto_min_max_list_for_{line_part}_{self._temp_counter}"
            self._temp_counter += 1
            if candidate in self.used_names:
                continue
            self.used_names.add(candidate)
            return candidate

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


    def _is_simple_builtin_call(self, expr: ast.AST, *, builtin_name: str) -> bool:
        if not isinstance(expr, ast.Call):
            return False
        func = getattr(expr, "func", None)
        return isinstance(func, ast.Name) and func.id == builtin_name

    def _name_has_any_hint(self, name_text: str, *, hints: Tuple[str, ...]) -> bool:
        normalized_name = str(name_text or "")
        for hint_text in tuple(hints or ()):
            if hint_text and hint_text in normalized_name:
                return True
        return False

    def _pick_clamp_bound_and_input(
        self,
        *,
        first_expr: ast.expr,
        second_expr: ast.expr,
        bound_name_hints: Tuple[str, ...],
    ) -> Tuple[Optional[ast.expr], Optional[ast.expr]]:
        """从两个入参中选择 (bound_expr, input_expr)。

        约定：为了避免错误改写，仅在“可判定”的情况下返回；否则返回 (None, None)。

        判定策略（从强到弱）：
        - 名称提示：若恰好一个参数是变量名且名称包含 bound_name_hints，则认为该参数为 bound；
        - 常量提示：若不存在名称提示且恰好一个参数是数值常量，则认为该常量为 bound。
        """
        first_is_bound_by_name = isinstance(first_expr, ast.Name) and self._name_has_any_hint(
            first_expr.id,
            hints=bound_name_hints,
        )
        second_is_bound_by_name = isinstance(second_expr, ast.Name) and self._name_has_any_hint(
            second_expr.id,
            hints=bound_name_hints,
        )
        if first_is_bound_by_name != second_is_bound_by_name:
            if first_is_bound_by_name:
                return first_expr, second_expr
            return second_expr, first_expr

        # 若名称提示无法判定，则仅在“恰好一个是数值常量”时尝试判定 bound
        first_is_numeric_constant = isinstance(first_expr, ast.Constant) and isinstance(getattr(first_expr, "value", None), (int, float))
        second_is_numeric_constant = isinstance(second_expr, ast.Constant) and isinstance(getattr(second_expr, "value", None), (int, float))
        if first_is_numeric_constant != second_is_numeric_constant:
            if first_is_numeric_constant:
                return first_expr, second_expr
            return second_expr, first_expr

        return None, None

    def _try_rewrite_server_clamp_min_max(self, node: ast.Call) -> Optional[ast.Call]:
        """将常见 clamp 习惯写法改写为【范围限制运算】（server 单节点）。

        支持（忽略 max/min 入参顺序差异）：
        - max(下限, min(上限, 输入))
        - min(上限, max(下限, 输入))

        注意：
        - 为避免错误改写，仅在能可靠识别“上限/下限”与“输入”时生效；
        - 若无法判定，则保持原表达式结构，由后续 max/min 两值语法糖改写为【取较大值/取较小值】（server）或
          “拼装列表+获取列表最大/最小值”（client/兜底）。
        """
        if self.scope != "server":
            return None

        func = getattr(node, "func", None)
        if not (isinstance(func, ast.Name) and func.id in {"max", "min"}):
            return None

        keywords = list(getattr(node, "keywords", []) or [])
        positional_args = list(getattr(node, "args", []) or [])
        if keywords or len(positional_args) != 2:
            return None
        if any(isinstance(argument, ast.Starred) for argument in positional_args):
            return None

        outer_builtin_name = func.id
        expected_inner_builtin_name = "min" if outer_builtin_name == "max" else "max"

        first_arg_expr, second_arg_expr = positional_args
        inner_call_expr: Optional[ast.Call] = None
        outer_bound_expr: Optional[ast.expr] = None
        if self._is_simple_builtin_call(first_arg_expr, builtin_name=expected_inner_builtin_name):
            inner_call_expr = first_arg_expr  # type: ignore[assignment]
            outer_bound_expr = second_arg_expr
        elif self._is_simple_builtin_call(second_arg_expr, builtin_name=expected_inner_builtin_name):
            inner_call_expr = second_arg_expr  # type: ignore[assignment]
            outer_bound_expr = first_arg_expr
        else:
            return None

        inner_keywords = list(getattr(inner_call_expr, "keywords", []) or [])
        inner_positional_args = list(getattr(inner_call_expr, "args", []) or [])
        if inner_keywords or len(inner_positional_args) != 2:
            return None
        if any(isinstance(argument, ast.Starred) for argument in inner_positional_args):
            return None

        inner_first_expr, inner_second_expr = inner_positional_args

        upper_hints = ("上限", "最大", "阈值", "upper", "max", "limit", "cap")
        lower_hints = ("下限", "最小", "lower", "min", "minimum")
        bound_hints = upper_hints if outer_builtin_name == "max" else lower_hints

        inner_bound_expr, input_expr = self._pick_clamp_bound_and_input(
            first_expr=inner_first_expr,
            second_expr=inner_second_expr,
            bound_name_hints=bound_hints,
        )
        if input_expr is None or inner_bound_expr is None or outer_bound_expr is None:
            return None

        if outer_builtin_name == "max":
            lower_bound_expr = outer_bound_expr
            upper_bound_expr = inner_bound_expr
        else:
            upper_bound_expr = outer_bound_expr
            lower_bound_expr = inner_bound_expr

        visited_input_expr = self.visit(input_expr)
        if isinstance(visited_input_expr, ast.expr):
            input_expr = visited_input_expr
        visited_lower_bound_expr = self.visit(lower_bound_expr)
        if isinstance(visited_lower_bound_expr, ast.expr):
            lower_bound_expr = visited_lower_bound_expr
        visited_upper_bound_expr = self.visit(upper_bound_expr)
        if isinstance(visited_upper_bound_expr, ast.expr):
            upper_bound_expr = visited_upper_bound_expr

        clamp_call = ast.Call(
            func=ast.Name(id="范围限制运算", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="输入", value=input_expr),
                ast.keyword(arg="下限", value=lower_bound_expr),
                ast.keyword(arg="上限", value=upper_bound_expr),
            ],
        )
        ast.copy_location(clamp_call, node)
        clamp_call.end_lineno = getattr(node, "end_lineno", getattr(clamp_call, "lineno", None))
        return clamp_call

