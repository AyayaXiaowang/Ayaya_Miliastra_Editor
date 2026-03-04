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


class _GraphCodeSyntaxSugarTransformerStmtMixin:
    def visit_AnnAssign(self, node: ast.AnnAssign):  # noqa: N802
        """三维向量字面量语法糖：

        - `向量: "三维向量" = (x, y, z)` / `[x, y, z]`
          → `向量: "三维向量" = 创建三维向量(self.game, X分量=x, Y分量=y, Z分量=z)`

        说明：
        - 仅在中文类型注解明确为“三维向量”时启用，避免把普通 tuple/list 误判为向量。
        - 兼容列表字面量已被重写为 `拼装列表(self.game, x, y, z)` 的场景。
        """
        target = getattr(node, "target", None)
        annotation = getattr(node, "annotation", None)
        value_expr = getattr(node, "value", None)

        # 先递归处理子表达式，保证向量分量内的语法糖一致
        if isinstance(value_expr, ast.expr):
            visited_value_expr = self.visit(value_expr)
            if isinstance(visited_value_expr, ast.expr):
                value_expr = visited_value_expr
                node.value = value_expr  # type: ignore[assignment]

        # client 的 max(a, b)/min(a, b) 会被改写为：获取列表最大值/最小值(列表=拼装列表(a, b))
        # 但拼装列表的输出为“泛型列表”，若没有中间带注解的列表变量承接，会触发结构校验的
        # “端口类型未实例化（仍为泛型）”。因此在 AnnAssign 场景下插入一个临时列表变量来实例化类型。
        if self.scope == "client" and isinstance(value_expr, ast.Call):
            call_func = getattr(value_expr, "func", None)
            if isinstance(call_func, ast.Name) and call_func.id in {LIST_MAX_VALUE_NODE_CALL_NAME, LIST_MIN_VALUE_NODE_CALL_NAME}:
                list_kw: Optional[ast.keyword] = next(
                    (kw for kw in list(getattr(value_expr, "keywords", []) or []) if getattr(kw, "arg", None) == "列表"),
                    None,
                )
                list_expr = getattr(list_kw, "value", None) if list_kw is not None else None
                if isinstance(list_expr, ast.Call):
                    list_func = getattr(list_expr, "func", None)
                    if isinstance(list_func, ast.Name) and list_func.id == "拼装列表":
                        element_type_text = ""
                        if isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str):
                            element_type_text = str(annotation.value).strip()

                        if element_type_text not in {"整数", "浮点数"}:
                            # 兜底：尝试从入参变量注解推断（仅当两侧一致且为数值类型）
                            arg_exprs = list(getattr(list_expr, "args", []) or [])
                            if arg_exprs and isinstance(arg_exprs[0], ast.Attribute):
                                if (
                                    isinstance(getattr(arg_exprs[0], "value", None), ast.Name)
                                    and arg_exprs[0].value.id == "self"
                                    and str(getattr(arg_exprs[0], "attr", "") or "") == "game"
                                ):
                                    arg_exprs = arg_exprs[1:]
                            if len(arg_exprs) >= 2 and all(isinstance(x, ast.Name) for x in arg_exprs[:2]):
                                left_t = self._get_var_type_text(arg_exprs[0].id)
                                right_t = self._get_var_type_text(arg_exprs[1].id)
                                if left_t and left_t == right_t and left_t in {"整数", "浮点数"}:
                                    element_type_text = left_t

                        if element_type_text in {"整数", "浮点数"} and isinstance(target, ast.Name):
                            list_type_text = f"{element_type_text}列表"
                            temp_list_name = self._next_temp_min_max_list_var_name(getattr(node, "lineno", None))

                            list_assign = ast.AnnAssign(
                                target=ast.Name(id=temp_list_name, ctx=ast.Store()),
                                annotation=ast.Constant(value=list_type_text),
                                value=list_expr,
                                simple=1,
                            )
                            ast.copy_location(list_assign, node)
                            list_assign.end_lineno = getattr(node, "end_lineno", getattr(list_assign, "lineno", None))

                            list_kw.value = ast.Name(id=temp_list_name, ctx=ast.Load())
                            ast.copy_location(list_kw.value, list_expr)
                            list_kw.value.end_lineno = getattr(list_expr, "end_lineno", getattr(list_kw.value, "lineno", None))  # type: ignore[attr-defined]

                            node.value = value_expr  # type: ignore[assignment]
                            return [list_assign, node]

        if not isinstance(target, ast.Name):
            return self.generic_visit(node)
        if not (isinstance(annotation, ast.Constant) and isinstance(getattr(annotation, "value", None), str)):
            return self.generic_visit(node)
        if str(annotation.value).strip() != "三维向量":
            return self.generic_visit(node)
        if not isinstance(value_expr, ast.expr):
            return node

        components: Optional[Tuple[ast.expr, ast.expr, ast.expr]] = None
        if isinstance(value_expr, ast.Tuple) and isinstance(getattr(value_expr, "ctx", None), ast.Load):
            elements = list(getattr(value_expr, "elts", []) or [])
            if len(elements) == 3 and all(isinstance(e, ast.expr) for e in elements):
                components = (elements[0], elements[1], elements[2])  # type: ignore[assignment]
        elif isinstance(value_expr, ast.List) and isinstance(getattr(value_expr, "ctx", None), ast.Load):
            elements = list(getattr(value_expr, "elts", []) or [])
            if len(elements) == 3 and all(isinstance(e, ast.expr) for e in elements):
                components = (elements[0], elements[1], elements[2])  # type: ignore[assignment]
        elif isinstance(value_expr, ast.Call):
            call_func = getattr(value_expr, "func", None)
            call_args = list(getattr(value_expr, "args", []) or [])
            call_keywords = list(getattr(value_expr, "keywords", []) or [])
            # 兼容列表字面量重写后的形态：拼装列表(self.game, x, y, z)
            if isinstance(call_func, ast.Name) and call_func.id == "拼装列表" and not call_keywords and len(call_args) == 4:
                second, third, fourth = call_args[1], call_args[2], call_args[3]
                if all(isinstance(e, ast.expr) for e in (second, third, fourth)):
                    components = (second, third, fourth)

        if components is None:
            return node

        x_expr, y_expr, z_expr = components
        create_call = ast.Call(
            func=ast.Name(id="创建三维向量", ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="X分量", value=x_expr),
                ast.keyword(arg="Y分量", value=y_expr),
                ast.keyword(arg="Z分量", value=z_expr),
            ],
        )
        ast.copy_location(create_call, value_expr)
        create_call.end_lineno = getattr(value_expr, "end_lineno", getattr(create_call, "lineno", None))
        node.value = create_call  # type: ignore[assignment]
        return node

    # ------------------------------
    # 语句级改写
    # ------------------------------

    def visit_For(self, node: ast.For):  # noqa: N802
        """enumerate 语法糖：for idx, item in enumerate(列表变量): ...

        约定：
        - 仅支持 enumerate(列表变量) 形式（必须恰好 1 个位置参数且不含关键字参数）；
        - 列表必须是变量名（不允许表达式/属性/调用）。

        改写为：
        - __auto_len: "整数" = len(列表变量)
        - for idx in range(__auto_len):
              item = 列表变量[idx]
              <原循环体>
        """
        iter_expr = getattr(node, "iter", None)
        if not isinstance(iter_expr, ast.Call):
            return self.generic_visit(node)

        iter_func = getattr(iter_expr, "func", None)
        if not (isinstance(iter_func, ast.Name) and iter_func.id == "enumerate"):
            return self.generic_visit(node)

        positional_args = list(getattr(iter_expr, "args", []) or [])
        keywords = list(getattr(iter_expr, "keywords", []) or [])
        if keywords or len(positional_args) != 1:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_CALL_ARGS_INVALID",
                    message="enumerate(...) 语法糖仅支持 1 个位置参数且不支持关键字参数；请写为 `for 序号, 元素 in enumerate(列表变量):`",
                    node=iter_expr,
                )
            )
            return self.generic_visit(node)

        list_expr = positional_args[0]
        if not isinstance(list_expr, ast.Name):
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_CONTAINER_MUST_BE_NAME",
                    message="enumerate(...) 的入参必须是列表变量名；请先赋值到变量（并尽量带中文类型注解）再迭代",
                    node=list_expr,
                )
            )
            return self.generic_visit(node)

        list_type_text = str(self.list_var_type_by_name.get(list_expr.id, "") or "").strip()
        if not list_type_text:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_LIST_TYPE_REQUIRED",
                    message="enumerate(...) 语法糖要求列表变量具备显式中文类型注解（例如：列表: \"整数列表\" = ...）；否则无法推断元素类型并会削弱端口类型校验",
                    node=list_expr,
                )
            )
            return self.generic_visit(node)
        element_type_text = list_type_text[:-2].strip() if list_type_text.endswith("列表") else ""
        if not element_type_text:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_LIST_TYPE_REQUIRED",
                    message=f"无法从列表类型『{list_type_text}』推断元素类型；请改用形如 \"整数列表\"/\"浮点数列表\"/\"实体列表\" 的列表类型注解",
                    node=list_expr,
                )
            )
            return self.generic_visit(node)

        target_expr = getattr(node, "target", None)
        if not isinstance(target_expr, (ast.Tuple, ast.List)):
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_TARGET_UNSUPPORTED",
                    message="enumerate(...) 的 for 目标必须为二元拆分赋值：`for 序号, 元素 in enumerate(列表变量):`",
                    node=node,
                )
            )
            return self.generic_visit(node)

        target_elts = list(getattr(target_expr, "elts", []) or [])
        if len(target_elts) != 2 or not all(isinstance(elt, ast.Name) for elt in target_elts):
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_TARGET_UNSUPPORTED",
                    message="enumerate(...) 的 for 目标必须为二元变量名拆分赋值：`for 序号, 元素 in enumerate(列表变量):`",
                    node=target_expr,
                )
            )
            return self.generic_visit(node)

        index_var_name = target_elts[0].id
        element_var_name = target_elts[1].id
        if not index_var_name or not element_var_name:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_ENUMERATE_TARGET_UNSUPPORTED",
                    message="enumerate(...) 的 for 目标变量名不能为空",
                    node=target_expr,
                )
            )
            return self.generic_visit(node)

        length_var_name = self._next_temp_enumerate_length_var_name(getattr(node, "lineno", None))
        base_lineno = int(getattr(node, "lineno", 0) or 0)

        length_assign = ast.AnnAssign(
            target=ast.Name(id=length_var_name, ctx=ast.Store()),
            annotation=ast.Constant(value="整数"),
            value=ast.Call(
                func=ast.Name(id="len", ctx=ast.Load()),
                args=[ast.Name(id=list_expr.id, ctx=ast.Load())],
                keywords=[],
            ),
            simple=1,
        )
        ast.copy_location(length_assign, node)
        if base_lineno > 0:
            length_assign.lineno = base_lineno
            length_assign.end_lineno = base_lineno
        length_assign.end_lineno = getattr(node, "end_lineno", getattr(length_assign, "lineno", None))
        visited_length_assign = self.visit(length_assign)
        length_assign_stmt = visited_length_assign if isinstance(visited_length_assign, ast.stmt) else length_assign

        range_call = ast.Call(
            func=ast.Name(id="range", ctx=ast.Load()),
            args=[ast.Name(id=length_var_name, ctx=ast.Load())],
            keywords=[],
        )
        ast.copy_location(range_call, node)
        if base_lineno > 0:
            range_call.lineno = base_lineno + 1
            range_call.end_lineno = base_lineno + 1
        range_call.end_lineno = getattr(node, "end_lineno", getattr(range_call, "lineno", None))

        element_assign = ast.AnnAssign(
            target=ast.Name(id=element_var_name, ctx=ast.Store()),
            annotation=ast.Constant(value=element_type_text),
            value=ast.Subscript(
                value=ast.Name(id=list_expr.id, ctx=ast.Load()),
                slice=ast.Name(id=index_var_name, ctx=ast.Load()),
                ctx=ast.Load(),
            ),
            simple=1,
        )
        ast.copy_location(element_assign, node)
        element_assign.end_lineno = getattr(node, "end_lineno", getattr(element_assign, "lineno", None))
        visited_element_assign = self.visit(element_assign)
        element_assign_stmt = visited_element_assign if isinstance(visited_element_assign, ast.stmt) else element_assign

        # 递归处理原循环体（保持语法糖一致视图）
        rewritten_body = self._visit_stmt_list(getattr(node, "body", []) or [])
        rewritten_orelse = self._visit_stmt_list(getattr(node, "orelse", []) or [])

        new_for = ast.For(
            target=ast.Name(id=index_var_name, ctx=ast.Store()),
            iter=range_call,
            body=[element_assign_stmt, *rewritten_body],
            orelse=rewritten_orelse,
            type_comment=getattr(node, "type_comment", None),
        )
        ast.copy_location(new_for, node)
        if base_lineno > 0:
            new_for.lineno = base_lineno + 1
        new_for.end_lineno = getattr(node, "end_lineno", getattr(new_for, "lineno", None))

        return [length_assign_stmt, new_for]

    def visit_Assign(self, node: ast.Assign):  # noqa: N802
        targets = list(getattr(node, "targets", []) or [])
        if not targets:
            return self.generic_visit(node)

        # 三维向量赋值语法糖（无注解赋值，但变量类型已由 AnnAssign 声明过）：
        # - `向量 = (x, y, z)` / `[x, y, z]` / `拼装列表(self.game, x, y, z)` -> `向量 = 创建三维向量(...)`
        if len(targets) == 1 and isinstance(targets[0], ast.Name) and self._get_var_type_text(targets[0].id) == "三维向量":
            value_expr = getattr(node, "value", None)
            if isinstance(value_expr, ast.expr):
                visited_value_expr = self.visit(value_expr)
                if isinstance(visited_value_expr, ast.expr):
                    value_expr = visited_value_expr
                    node.value = value_expr  # type: ignore[assignment]

            if not isinstance(value_expr, ast.expr):
                return node

            components: Optional[Tuple[ast.expr, ast.expr, ast.expr]] = None
            if isinstance(value_expr, ast.Tuple) and isinstance(getattr(value_expr, "ctx", None), ast.Load):
                elements = list(getattr(value_expr, "elts", []) or [])
                if len(elements) == 3 and all(isinstance(e, ast.expr) for e in elements):
                    components = (elements[0], elements[1], elements[2])  # type: ignore[assignment]
            elif isinstance(value_expr, ast.List) and isinstance(getattr(value_expr, "ctx", None), ast.Load):
                elements = list(getattr(value_expr, "elts", []) or [])
                if len(elements) == 3 and all(isinstance(e, ast.expr) for e in elements):
                    components = (elements[0], elements[1], elements[2])  # type: ignore[assignment]
            elif isinstance(value_expr, ast.Call):
                call_func = getattr(value_expr, "func", None)
                call_args = list(getattr(value_expr, "args", []) or [])
                call_keywords = list(getattr(value_expr, "keywords", []) or [])
                if isinstance(call_func, ast.Name) and call_func.id == "拼装列表" and not call_keywords and len(call_args) == 4:
                    second, third, fourth = call_args[1], call_args[2], call_args[3]
                    if all(isinstance(e, ast.expr) for e in (second, third, fourth)):
                        components = (second, third, fourth)

            if components is not None:
                x_expr, y_expr, z_expr = components
                create_call = ast.Call(
                    func=ast.Name(id="创建三维向量", ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[
                        ast.keyword(arg="X分量", value=x_expr),
                        ast.keyword(arg="Y分量", value=y_expr),
                        ast.keyword(arg="Z分量", value=z_expr),
                    ],
                )
                ast.copy_location(create_call, value_expr)
                create_call.end_lineno = getattr(value_expr, "end_lineno", getattr(create_call, "lineno", None))
                node.value = create_call  # type: ignore[assignment]
                return node

        # 仅处理单目标下标赋值：字典[键] = 值
        subscript_targets = [t for t in targets if isinstance(t, ast.Subscript)]
        if not subscript_targets:
            return self.generic_visit(node)

        if len(targets) != 1:
            first_subscript = subscript_targets[0]
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_SUBSCRIPT_ASSIGN_CHAIN_FORBIDDEN",
                    message="不支持链式/多目标的下标赋值；请拆分为多行（例如：先分别计算值，再逐行写 `容器[键] = 值`）",
                    node=first_subscript,
                )
            )
            return self.generic_visit(node)

        target = targets[0]
        if not isinstance(target, ast.Subscript):
            return self.generic_visit(node)

        container_expr = getattr(target, "value", None)
        if not isinstance(container_expr, ast.Name):
            return self.generic_visit(node)

        container_name = container_expr.id
        if not _is_dict_var_name(container_name, self.dict_var_names):
            # 非字典：保持原样，交给列表重写/其他规则处理
            return self.generic_visit(node)

        index_expr = _extract_subscript_index_expr(target)
        if index_expr is None:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_DICT_SUBSCRIPT_INDEX_UNSUPPORTED",
                    message="该字典下标写法暂不支持转换为节点逻辑（仅支持单个键访问，不支持切片/多维索引）",
                    node=target,
                )
            )
            return self.generic_visit(node)

        value_expr = getattr(node, "value", None)
        if not isinstance(value_expr, ast.expr):
            return self.generic_visit(node)

        visited_index = self.visit(index_expr)
        if isinstance(visited_index, ast.expr):
            index_expr = visited_index

        visited_value = self.visit(value_expr)
        if isinstance(visited_value, ast.expr):
            value_expr = visited_value

        call_node = ast.Call(
            func=ast.Name(id=DICT_SET_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="字典", value=ast.Name(id=container_name, ctx=ast.Load())),
                ast.keyword(arg="键", value=index_expr),
                ast.keyword(arg="值", value=value_expr),
            ],
        )
        new_stmt = ast.Expr(value=call_node)
        ast.copy_location(new_stmt, node)
        new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
        return new_stmt

    def visit_Delete(self, node: ast.Delete):  # noqa: N802
        targets = list(getattr(node, "targets", []) or [])
        if not targets:
            return self.generic_visit(node)

        # 仅处理单目标：del 字典[键]
        subscript_targets = [t for t in targets if isinstance(t, ast.Subscript)]
        if not subscript_targets:
            return self.generic_visit(node)

        if len(targets) != 1:
            first_subscript = subscript_targets[0]
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_SUBSCRIPT_DELETE_MULTIPLE_TARGETS_FORBIDDEN",
                    message="不支持在同一条 del 语句中删除多个下标；请拆分为多行 `del 容器[键]`",
                    node=first_subscript,
                )
            )
            return self.generic_visit(node)

        target = targets[0]
        if not isinstance(target, ast.Subscript):
            return self.generic_visit(node)

        container_expr = getattr(target, "value", None)
        if not isinstance(container_expr, ast.Name):
            return self.generic_visit(node)

        container_name = container_expr.id
        if not _is_dict_var_name(container_name, self.dict_var_names):
            return self.generic_visit(node)

        index_expr = _extract_subscript_index_expr(target)
        if index_expr is None:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_DICT_SUBSCRIPT_INDEX_UNSUPPORTED",
                    message="该 del 字典下标写法暂不支持转换为节点逻辑（仅支持单个键访问，不支持切片/多维索引）",
                    node=target,
                )
            )
            return self.generic_visit(node)

        visited_index = self.visit(index_expr)
        if isinstance(visited_index, ast.expr):
            index_expr = visited_index

        call_node = ast.Call(
            func=ast.Name(id=DICT_DELETE_ITEM_NODE_CALL_NAME, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="字典", value=ast.Name(id=container_name, ctx=ast.Load())),
                ast.keyword(arg="键", value=index_expr),
            ],
        )
        new_stmt = ast.Expr(value=call_node)
        ast.copy_location(new_stmt, node)
        new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
        return new_stmt

    def visit_AugAssign(self, node: ast.AugAssign):  # noqa: N802
        target = getattr(node, "target", None)
        if not isinstance(target, ast.Name):
            return self.generic_visit(node)

        op = getattr(node, "op", None)
        if not isinstance(op, ast.operator):
            return self.generic_visit(node)

        # 列表原地拼接：目标列表 += 接入列表（仅 server；保持与【拼接列表】执行节点语义一致）
        if isinstance(op, ast.Add) and target.id in self.list_var_names:
            value_expr = getattr(node, "value", None)
            if not isinstance(value_expr, ast.expr):
                return self.generic_visit(node)
            visited_value = self.visit(value_expr)
            if isinstance(visited_value, ast.expr):
                value_expr = visited_value

            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_INPLACE_ADD_NOT_SUPPORTED_IN_CLIENT",
                        message="列表增量拼接 `目标列表 += 接入列表` 语法糖仅在 server 作用域支持（会改写为【拼接列表】执行节点）。",
                        node=node,
                    )
                )
                return node

            concat_call = ast.Call(
                func=ast.Name(id="拼接列表", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="目标列表", value=ast.Name(id=target.id, ctx=ast.Load())),
                    ast.keyword(arg="接入的列表", value=value_expr),
                ],
            )
            new_stmt = ast.Expr(value=concat_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        node_name = _arith_node_name(op)
        if node_name is None:
            self.issues.append(
                SyntaxSugarRewriteIssue(
                    code="CODE_AUG_ASSIGN_OP_UNSUPPORTED",
                    message="不支持该增量赋值运算；仅支持 +=, -=, *=, /=",
                    node=node,
                )
            )
            return self.generic_visit(node)

        value_expr = getattr(node, "value", None)
        if not isinstance(value_expr, ast.expr):
            return self.generic_visit(node)
        visited_value = self.visit(value_expr)
        if isinstance(visited_value, ast.expr):
            value_expr = visited_value

        call_expr = ast.Call(
            func=ast.Name(id=node_name, ctx=ast.Load()),
            args=[_build_self_game_expr()],
            keywords=[
                ast.keyword(arg="左值", value=ast.Name(id=target.id, ctx=ast.Load())),
                ast.keyword(arg="右值", value=value_expr),
            ],
        )
        new_assign = ast.Assign(
            targets=[ast.Name(id=target.id, ctx=ast.Store())],
            value=call_expr,
        )
        ast.copy_location(new_assign, node)
        new_assign.end_lineno = getattr(node, "end_lineno", getattr(new_assign, "lineno", None))
        return new_assign

    def visit_Expr(self, node: ast.Expr):  # noqa: N802
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Call):
            return self.generic_visit(node)

        func = getattr(value, "func", None)
        if isinstance(func, ast.Name) and func.id == "print":
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_PRINT_NOT_SUPPORTED_IN_CLIENT",
                        message="print(...) 语法糖仅在 server 作用域支持（会改写为【打印字符串】执行节点）。client 侧缺少等价节点。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            positional_args = list(getattr(value, "args", []) or [])
            keywords = list(getattr(value, "keywords", []) or [])
            if keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_PRINT_KEYWORD_ARGS_FORBIDDEN",
                        message="print(...) 语法糖不支持关键字参数（例如 sep/end/file/flush）；请使用单一位置参数写法 `print(x)`。",
                        node=value,
                    )
                )
                return self.generic_visit(node)
            if any(isinstance(arg, ast.Starred) for arg in positional_args):
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_PRINT_UNPACK_FORBIDDEN",
                        message="print(...) 语法糖不支持 * 展开入参；请先把值落到变量再打印。",
                        node=value,
                    )
                )
                return self.generic_visit(node)
            if len(positional_args) != 1:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_PRINT_ARGS_INVALID",
                        message="print(...) 语法糖仅支持 1 个位置参数（例如 `print(x)`）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            visited_arg = self.visit(positional_args[0])
            if isinstance(visited_arg, ast.expr):
                arg_expr = visited_arg
            else:
                arg_expr = positional_args[0]

            # 若入参明显为字符串则直接传入；否则尝试通过【数据类型转换】转换为字符串。
            is_string_expr = False
            if isinstance(arg_expr, ast.Constant) and isinstance(getattr(arg_expr, "value", None), str):
                is_string_expr = True
            elif isinstance(arg_expr, ast.Name):
                is_string_expr = self._get_var_type_text(arg_expr.id) == "字符串"

            string_expr: ast.expr
            if is_string_expr:
                string_expr = arg_expr
            else:
                string_expr = ast.Call(
                    func=ast.Name(id=TYPE_CONVERSION_NODE_CALL_NAME, ctx=ast.Load()),
                    args=[_build_self_game_expr()],
                    keywords=[ast.keyword(arg="输入", value=arg_expr)],
                )
                ast.copy_location(string_expr, arg_expr)

            print_call = ast.Call(
                func=ast.Name(id="打印字符串", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="字符串", value=string_expr)],
            )
            new_stmt = ast.Expr(value=print_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        if not isinstance(func, ast.Attribute):
            return self.generic_visit(node)

        method_name = str(getattr(func, "attr", "") or "")
        target_container_expr = getattr(func, "value", None)
        if not isinstance(target_container_expr, ast.Name):
            # 统一用现有“方法调用禁用”规则报错即可：这里不重复上报
            return self.generic_visit(node)

        positional_args = list(getattr(value, "args", []) or [])
        keywords = list(getattr(value, "keywords", []) or [])

        if method_name == "append":
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_APPEND_NOT_SUPPORTED_IN_CLIENT",
                        message="列表方法 `append(值)` 语法糖仅在 server 作用域支持（会改写为【对列表插入值】执行节点）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            if target_container_expr.id not in self.list_var_names:
                # 非“明确列表变量名”不做改写，交由方法调用禁用规则提示
                return self.generic_visit(node)

            if keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_METHOD_APPEND_KEYWORD_ARGS_FORBIDDEN",
                        message="列表方法 `append()` 不支持关键字参数写法；请使用位置参数（例如 `目标列表.append(值)`）",
                        node=value,
                    )
                )
                return self.generic_visit(node)
            if len(positional_args) != 1:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_METHOD_APPEND_ARGS_INVALID",
                        message="仅支持 `目标列表.append(值)` 形式（必须恰好 1 个位置参数）",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            visited_value_arg = self.visit(positional_args[0])
            if isinstance(visited_value_arg, ast.expr):
                value_arg_expr = visited_value_arg
            else:
                value_arg_expr = positional_args[0]

            # 方案A（不新增节点，且尽量单节点）：append(x) -> 对列表插入值(列表=目标列表, 插入序号=大常量, 插入值=x)
            # 说明：Python list.insert(i, x) 在 i >= len(list) 时等价于 append(x)。
            insert_call = ast.Call(
                func=ast.Name(id="对列表插入值", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="列表", value=ast.Name(id=target_container_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="插入序号", value=ast.Constant(value=2147483647)),
                    ast.keyword(arg="插入值", value=value_arg_expr),
                ],
            )
            new_stmt = ast.Expr(value=insert_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        if method_name == "pop" and target_container_expr.id in self.list_var_names:
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_POP_NOT_SUPPORTED_IN_CLIENT",
                        message="列表方法 `pop(序号)` 语法糖仅在 server 作用域支持（会改写为【对列表移除值】执行节点）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            if keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_METHOD_POP_KEYWORD_ARGS_FORBIDDEN",
                        message="列表方法 `pop()` 不支持关键字参数写法；请使用位置参数（例如 `目标列表.pop(序号)`）",
                        node=value,
                    )
                )
                return self.generic_visit(node)
            if len(positional_args) != 1:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_METHOD_POP_ARGS_INVALID",
                        message="仅支持 `目标列表.pop(序号)` 形式（必须恰好 1 个位置参数）；如需删除末尾元素，请改用 `del 目标列表[len(目标列表) - 1]` 或显式传入序号变量。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            visited_index_arg = self.visit(positional_args[0])
            if isinstance(visited_index_arg, ast.expr):
                index_arg_expr = visited_index_arg
            else:
                index_arg_expr = positional_args[0]

            remove_call = ast.Call(
                func=ast.Name(id="对列表移除值", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="列表", value=ast.Name(id=target_container_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="移除序号", value=index_arg_expr),
                ],
            )
            new_stmt = ast.Expr(value=remove_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        if method_name == "sort":
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_SORT_NOT_SUPPORTED_IN_CLIENT",
                        message="列表方法 `sort(...)` 语法糖仅在 server 作用域支持（会改写为【列表排序】执行节点）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            if target_container_expr.id not in self.list_var_names:
                # 非“明确列表变量名”不做改写，交由方法调用禁用规则提示
                return self.generic_visit(node)

            if positional_args:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_LIST_METHOD_SORT_POSITIONAL_ARGS_FORBIDDEN",
                        message="列表方法 `sort()` 不支持位置参数；仅允许 `目标列表.sort()` 或 `目标列表.sort(reverse=True/False)`",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            sorting_mode = "排序规则_顺序"
            if keywords:
                if len(keywords) != 1 or keywords[0].arg != "reverse":
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_LIST_METHOD_SORT_KEYWORDS_UNSUPPORTED",
                            message="列表方法 `sort()` 仅支持关键字参数 reverse=True/False；不支持 key 等参数",
                            node=value,
                        )
                    )
                    return self.generic_visit(node)
                reverse_value_expr = keywords[0].value
                if not (isinstance(reverse_value_expr, ast.Constant) and isinstance(getattr(reverse_value_expr, "value", None), bool)):
                    self.issues.append(
                        SyntaxSugarRewriteIssue(
                            code="CODE_LIST_METHOD_SORT_REVERSE_MUST_BE_BOOL_CONST",
                            message="列表方法 `sort(reverse=...)` 的 reverse 参数必须为布尔常量 True/False；如需运行期决定排序方式，请改用显式分支分别调用【列表排序】",
                            node=keywords[0],
                        )
                    )
                    return self.generic_visit(node)
                if reverse_value_expr.value is True:  # type: ignore[attr-defined]
                    sorting_mode = "排序规则_逆序"

            sort_call = ast.Call(
                func=ast.Name(id="列表排序", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="列表", value=ast.Name(id=target_container_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="排序方式", value=ast.Constant(value=sorting_mode)),
                ],
            )
            new_stmt = ast.Expr(value=sort_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        if method_name == "pop" and _is_dict_var_name(target_container_expr.id, self.dict_var_names):
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DICT_POP_NOT_SUPPORTED_IN_CLIENT",
                        message="字典方法 `pop(键)` 语法糖仅在 server 作用域支持（会改写为【以键对字典移除键值对】执行节点）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            if keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DICT_METHOD_POP_KEYWORD_ARGS_FORBIDDEN",
                        message="字典方法 `pop()` 不支持关键字参数写法；请使用位置参数（例如 `目标字典.pop(键)`）",
                        node=value,
                    )
                )
                return self.generic_visit(node)
            if len(positional_args) != 1:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DICT_METHOD_POP_ARGS_INVALID",
                        message="仅支持 `目标字典.pop(键)` 形式（必须恰好 1 个位置参数）；如需默认值，请改用 if 分支或拆解为多步节点逻辑。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            visited_key_arg = self.visit(positional_args[0])
            if isinstance(visited_key_arg, ast.expr):
                key_arg_expr = visited_key_arg
            else:
                key_arg_expr = positional_args[0]

            remove_call = ast.Call(
                func=ast.Name(id="以键对字典移除键值对", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[
                    ast.keyword(arg="字典", value=ast.Name(id=target_container_expr.id, ctx=ast.Load())),
                    ast.keyword(arg="键", value=key_arg_expr),
                ],
            )
            new_stmt = ast.Expr(value=remove_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        if method_name == "clear":
            if self.scope != "server":
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DICT_CLEAR_NOT_SUPPORTED_IN_CLIENT",
                        message="字典方法 `clear()` 语法糖仅在 server 作用域支持（会改写为【清空字典】执行节点）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            if not _is_dict_var_name(target_container_expr.id, self.dict_var_names):
                return self.generic_visit(node)

            if positional_args or keywords:
                self.issues.append(
                    SyntaxSugarRewriteIssue(
                        code="CODE_DICT_METHOD_CLEAR_ARGS_FORBIDDEN",
                        message="仅支持 `目标字典.clear()`（不支持任何入参）。",
                        node=value,
                    )
                )
                return self.generic_visit(node)

            clear_call = ast.Call(
                func=ast.Name(id="清空字典", ctx=ast.Load()),
                args=[_build_self_game_expr()],
                keywords=[ast.keyword(arg="字典", value=ast.Name(id=target_container_expr.id, ctx=ast.Load()))],
            )
            new_stmt = ast.Expr(value=clear_call)
            ast.copy_location(new_stmt, node)
            new_stmt.end_lineno = getattr(node, "end_lineno", getattr(new_stmt, "lineno", None))
            return new_stmt

        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
        """在函数粒度做少量“严格模板折叠”，避免引入跨语句数据流追踪。"""
        if self.scope == "server":
            statements = list(getattr(node, "body", []) or [])
            new_body: List[ast.stmt] = []
            index = 0
            while index < len(statements):
                if index + 1 < len(statements):
                    folded = self._try_fold_bit_write_two_step_pair(
                        statements[index],
                        statements[index + 1],
                        statements[index + 2 :],
                    )
                    if folded is not None:
                        new_body.append(folded)
                        index += 2
                        continue
                new_body.append(statements[index])
                index += 1
            node.body = new_body  # type: ignore[assignment]
        return self.generic_visit(node)

