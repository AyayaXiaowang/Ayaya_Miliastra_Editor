"""未使用的数据/查询输出检测规则（warning）。"""

from __future__ import annotations

import ast
from bisect import bisect_right
from pathlib import Path
from typing import Dict, List, Set, Tuple

from engine.utils.graph.graph_utils import is_flow_port_name

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import get_cached_module, infer_graph_scope, iter_class_methods
from ..node_index import data_query_node_names, flow_node_names, callable_node_defs_by_name


class UnusedQueryOutputRule(ValidationRule):
    """未使用的数据/查询输出

    检测“查询/运算类节点”的输出被变量接收，但该语句产生的所有数据输出都未被后续**流程消费**的情况。

    说明：
    - 多输出节点在 Graph Code 中通常需要用拆分赋值形式表达（端口按输出顺序绑定），因此**不要求**每个输出都被使用；
      但至少应有一个输出最终被“流程节点/控制结构”消费，否则该节点等同于纯数据孤立链路，属于冗余。
    支持两种赋值形式：
    - 简单赋值：x = 查询(...)
    - 带类型注解的赋值：x: "类型" = 查询(...)
    """

    rule_id = "engine_code_unused_query_output"
    category = "代码规范"
    default_level = "warning"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        query_funcs = data_query_node_names(ctx.workspace_path, scope)
        flow_funcs = flow_node_names(ctx.workspace_path, scope)
        callable_nodes = callable_node_defs_by_name(ctx.workspace_path, scope)
        issues: List[EngineIssue] = []

        # client 过滤器节点图：return 值本身代表“图输出”，应视为有效的“流程消费点”。
        # 否则会把“用于计算返回值的纯数据链路”误判为冗余（例如：return 条件判断结果）。
        is_client_filter_graph = False
        if scope == "client" and isinstance(ctx.file_path, Path):
            normalized_path = ctx.file_path.as_posix()
            is_client_filter_graph = (
                ("/节点图/client/布尔过滤器节点图/" in normalized_path)
                or ("/节点图/client/整数过滤器节点图/" in normalized_path)
                or ("/节点图/client/本地过滤器节点图/" in normalized_path)
            )

        def _is_pure_alias_assignment(node: ast.AST) -> bool:
            """识别纯别名赋值：dest = src（两侧均为简单变量名）。"""
            if isinstance(node, ast.Assign):
                if (
                    isinstance(getattr(node, "value", None), ast.Name)
                    and isinstance(getattr(node, "targets", None), list)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                ):
                    return True
            if isinstance(node, ast.AnnAssign):
                if (
                    isinstance(getattr(node, "target", None), ast.Name)
                    and isinstance(getattr(node, "value", None), ast.Name)
                ):
                    return True
            return False

        class _MeaningfulNameLoadCollector(ast.NodeVisitor):
            """收集“有意义的变量读取（Load）”。

            规则：
            - 纯别名赋值（dest = src）不算“使用 src”，因为它只是中转；
              只有当 dest 后续被真正使用时，才会通过别名传播回 src。
            """

            def __init__(self) -> None:
                self.load_lines_by_name: Dict[str, Set[int]] = {}

            def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
                if _is_pure_alias_assignment(node):
                    return
                self.generic_visit(node)

            def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
                if _is_pure_alias_assignment(node):
                    return
                self.generic_visit(node)

            def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
                if isinstance(getattr(node, "ctx", None), ast.Load):
                    name_text = str(getattr(node, "id", "") or "")
                    line_no = getattr(node, "lineno", 0) or 0
                    if name_text and isinstance(line_no, int) and line_no > 0:
                        self.load_lines_by_name.setdefault(name_text, set()).add(line_no)

        class _StoreNameCollector(ast.NodeVisitor):
            """收集变量被赋值（Store）的行号，用于判断别名链在使用点是否仍有效。"""

            def __init__(self) -> None:
                self.store_lines_by_name: Dict[str, List[int]] = {}

            def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
                if isinstance(getattr(node, "ctx", None), ast.Store):
                    name_text = str(getattr(node, "id", "") or "")
                    line_no = getattr(node, "lineno", 0) or 0
                    if name_text and isinstance(line_no, int) and line_no > 0:
                        self.store_lines_by_name.setdefault(name_text, []).append(line_no)

        def _has_store_between(
            sorted_store_lines: List[int],
            *,
            start_line_exclusive: int,
            end_line_exclusive: int,
        ) -> bool:
            """判断 (start, end) 区间内是否存在对同名变量的再次赋值。"""
            if not sorted_store_lines:
                return False
            start = int(start_line_exclusive)
            end = int(end_line_exclusive)
            if end <= start:
                return False
            index = bisect_right(sorted_store_lines, start)
            return index < len(sorted_store_lines) and sorted_store_lines[index] < end

        def _collect_target_names(target_expr: object) -> List[str]:
            """提取赋值目标中的变量名。

            支持：
            - Name：x = ...
            - Tuple：a, b, c = ...
            """
            if isinstance(target_expr, ast.Name):
                return [target_expr.id]
            if isinstance(target_expr, ast.Tuple):
                names: List[str] = []
                for element in list(getattr(target_expr, "elts", []) or []):
                    if isinstance(element, ast.Name) and isinstance(element.id, str) and element.id:
                        names.append(element.id)
                return names
            return []

        class _LoadNameCollector(ast.NodeVisitor):
            """收集表达式中被读取（Load）的变量名。

            关键行为：
            - 跳过 Call.func（函数名），避免把节点函数名当作“变量使用”。
            """

            _IGNORED: Set[str] = {"self", "game", "owner_entity"}

            def __init__(self) -> None:
                self.names: Set[str] = set()

            def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
                for arg in list(getattr(node, "args", []) or []):
                    self.visit(arg)
                for kw in list(getattr(node, "keywords", []) or []):
                    value = getattr(kw, "value", None)
                    if isinstance(value, ast.AST):
                        self.visit(value)

            def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
                if not isinstance(getattr(node, "ctx", None), ast.Load):
                    return
                name_text = str(getattr(node, "id", "") or "").strip()
                if not name_text or name_text in self._IGNORED:
                    return
                self.names.add(name_text)

        def _collect_load_names(expr: ast.AST) -> Set[str]:
            collector = _LoadNameCollector()
            collector.visit(expr)
            return collector.names

        def _collect_imported_symbol_to_module(module_ast: ast.AST) -> Dict[str, str]:
            mapping: Dict[str, str] = {}
            for node in ast.walk(module_ast):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module_name = str(getattr(node, "module", "") or "").strip()
                if not module_name:
                    continue
                for alias in list(getattr(node, "names", []) or []):
                    name = str(getattr(alias, "name", "") or "").strip()
                    asname = str(getattr(alias, "asname", "") or "").strip()
                    symbol = asname or name
                    if symbol and module_name:
                        mapping[symbol] = module_name
            return mapping

        def _resolve_assets_module_to_file(*, module_name: str) -> Path | None:
            text = str(module_name or "").strip()
            if not text:
                return None
            parts = [p for p in text.split(".") if p]
            if not parts:
                return None
            candidate = ctx.workspace_path / "assets"
            for p in parts:
                candidate = candidate / p
            candidate = candidate.with_suffix(".py")
            return candidate if candidate.exists() else None

        def _collect_flow_methods_from_composite_file(*, composite_file: Path, class_name: str) -> Set[str]:
            try:
                source = composite_file.read_text(encoding="utf-8-sig")
            except Exception:
                return set()
            try:
                module_ast = ast.parse(source, filename=str(composite_file))
            except SyntaxError:
                return set()

            def _is_flow_decorator(dec: ast.AST) -> bool:
                if isinstance(dec, ast.Call):
                    func = getattr(dec, "func", None)
                    if isinstance(func, ast.Name):
                        return str(func.id or "").strip() in {"flow_entry", "event_handler"}
                if isinstance(dec, ast.Name):
                    return str(dec.id or "").strip() in {"flow_entry", "event_handler"}
                return False

            for node in ast.walk(module_ast):
                if not isinstance(node, ast.ClassDef):
                    continue
                if str(getattr(node, "name", "") or "") != str(class_name or ""):
                    continue
                method_names: Set[str] = set()
                for body_item in list(getattr(node, "body", []) or []):
                    if not isinstance(body_item, ast.FunctionDef):
                        continue
                    decorators = list(getattr(body_item, "decorator_list", []) or [])
                    if any(_is_flow_decorator(d) for d in decorators):
                        name_text = str(getattr(body_item, "name", "") or "").strip()
                        if name_text:
                            method_names.add(name_text)
                return method_names
            return set()

        imported_symbol_to_module = _collect_imported_symbol_to_module(tree)
        composite_flow_methods_cache: Dict[Tuple[str, str], Set[str]] = {}

        def _get_flow_methods_for_composite_class(class_name: str) -> Set[str]:
            module_name = imported_symbol_to_module.get(class_name, "")
            composite_file = _resolve_assets_module_to_file(module_name=str(module_name))
            if composite_file is None:
                return set()
            cache_key = (str(composite_file), str(class_name))
            cached = composite_flow_methods_cache.get(cache_key)
            if cached is not None:
                return cached
            methods = _collect_flow_methods_from_composite_file(composite_file=composite_file, class_name=class_name)
            composite_flow_methods_cache[cache_key] = methods
            return methods

        class_methods = list(iter_class_methods(tree))
        composite_flow_methods_by_self_attr: Dict[str, Set[str]] = {}
        init_method = next(
            (m for _, m in class_methods if isinstance(m, ast.FunctionDef) and str(getattr(m, "name", "")) == "__init__"),
            None,
        )
        if init_method is not None:
            for node in ast.walk(init_method):
                if not isinstance(node, ast.Assign):
                    continue
                targets = list(getattr(node, "targets", []) or [])
                if len(targets) != 1:
                    continue
                target = targets[0]
                if not (isinstance(target, ast.Attribute) and isinstance(getattr(target, "value", None), ast.Name)):
                    continue
                if str(getattr(target.value, "id", "") or "").strip() != "self":
                    continue
                self_attr = str(getattr(target, "attr", "") or "").strip()
                value = getattr(node, "value", None)
                if not (isinstance(value, ast.Call) and isinstance(getattr(value, "func", None), ast.Name)):
                    continue
                class_name = str(getattr(value.func, "id", "") or "").strip()
                if not self_attr or not class_name:
                    continue
                composite_flow_methods_by_self_attr[self_attr] = _get_flow_methods_for_composite_class(class_name)

        for _, method in class_methods:
            assigned_query_calls: List[Tuple[str, List[str], int]] = []
            alias_edges: List[Tuple[str, str, int]] = []
            call_assignment_edges: List[Tuple[str, str, int]] = []

            # 收集：简单赋值（x = 查询(...)）和带类型注解的赋值（x: "类型" = 查询(...)）
            for node in ast.walk(method):
                # 简单赋值：x = 查询(...)
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    fname = getattr(getattr(node.value, "func", None), "id", None)
                    if isinstance(fname, str) and (fname in query_funcs):
                        # 仅处理单一 targets（避免 a=b=查询(...) 的歧义）
                        if len(list(getattr(node, "targets", []) or [])) == 1:
                            targets_expr = node.targets[0]
                            names = _collect_target_names(targets_expr)
                            lineno = getattr(node, "lineno", 0) or 0
                            if names and isinstance(lineno, int) and lineno > 0:
                                assigned_query_calls.append((fname, names, lineno))

                # 带类型注解的赋值：x: "类型" = 查询(...)
                if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
                    fname = getattr(getattr(node.value, "func", None), "id", None)
                    if isinstance(fname, str) and (fname in query_funcs):
                        target = node.target
                        if isinstance(target, ast.Name):
                            lineno = getattr(node, "lineno", 0) or 0
                            if isinstance(lineno, int) and lineno > 0 and isinstance(target.id, str) and target.id:
                                assigned_query_calls.append((fname, [target.id], lineno))

                # 纯别名赋值（用于“使用传播”）：dest = src
                if _is_pure_alias_assignment(node):
                    lineno = getattr(node, "lineno", 0) or 0
                    if not isinstance(lineno, int) or lineno <= 0:
                        continue
                    if isinstance(node, ast.Assign):
                        dest = node.targets[0]
                        src = node.value
                        if isinstance(dest, ast.Name) and isinstance(src, ast.Name):
                            alias_edges.append((dest.id, src.id, lineno))
                    elif isinstance(node, ast.AnnAssign):
                        dest = node.target
                        src = node.value
                        if isinstance(dest, ast.Name) and isinstance(src, ast.Name):
                            alias_edges.append((dest.id, src.id, lineno))

                # 赋值=节点调用：记录“目标变量 ← 输入变量”的依赖边，用于将“流程消费”沿数据链回溯到上游
                #
                # 说明：
                # - 只处理 RHS 为 Call 且 func 为 Name 的节点调用（Graph Code 形态）；
                # - 对多输出拆分赋值：每个输出变量都保守地依赖于该调用的所有输入变量；
                # - 这不是精确建模，只用于静态提示“纯数据链是否最终进入流程”。
                if isinstance(node, ast.Assign) and isinstance(getattr(node, "value", None), ast.Call):
                    call_expr = node.value
                    func = getattr(call_expr, "func", None)
                    if isinstance(func, ast.Name):
                        call_name = str(func.id or "").strip()
                        if call_name and (call_name in callable_nodes):
                            lineno = getattr(node, "lineno", 0) or 0
                            if isinstance(lineno, int) and lineno > 0 and len(node.targets) == 1:
                                targets = _collect_target_names(node.targets[0])
                                if targets:
                                    assignment_input_names: Set[str] = set()
                                    for arg in list(getattr(call_expr, "args", []) or []):
                                        if isinstance(arg, ast.AST):
                                            assignment_input_names.update(_collect_load_names(arg))
                                    for kw in list(getattr(call_expr, "keywords", []) or []):
                                        value = getattr(kw, "value", None)
                                        if isinstance(value, ast.AST):
                                            assignment_input_names.update(_collect_load_names(value))
                                    for dest_name in targets:
                                        for src_name in assignment_input_names:
                                            if src_name != dest_name:
                                                call_assignment_edges.append((dest_name, src_name, lineno))

                if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "value", None), ast.Call):
                    call_expr = node.value
                    func = getattr(call_expr, "func", None)
                    if isinstance(func, ast.Name):
                        call_name = str(func.id or "").strip()
                        if call_name and (call_name in callable_nodes):
                            lineno = getattr(node, "lineno", 0) or 0
                            if isinstance(lineno, int) and lineno > 0:
                                targets = _collect_target_names(node.target)
                                if targets:
                                    ann_assignment_input_names: Set[str] = set()
                                    for arg in list(getattr(call_expr, "args", []) or []):
                                        if isinstance(arg, ast.AST):
                                            ann_assignment_input_names.update(_collect_load_names(arg))
                                    for kw in list(getattr(call_expr, "keywords", []) or []):
                                        value = getattr(kw, "value", None)
                                        if isinstance(value, ast.AST):
                                            ann_assignment_input_names.update(_collect_load_names(value))
                                    for dest_name in targets:
                                        for src_name in ann_assignment_input_names:
                                            if src_name != dest_name:
                                                call_assignment_edges.append((dest_name, src_name, lineno))

            # 收集“赋值（Store）”行号，用于判断别名链在某个 use_line 时是否仍然有效
            store_collector = _StoreNameCollector()
            store_collector.visit(method)
            store_lines_by_name: Dict[str, List[int]] = dict(store_collector.store_lines_by_name)
            for name_text, lines in list(store_lines_by_name.items()):
                if not lines:
                    continue
                lines.sort()
                store_lines_by_name[name_text] = lines

            # 1) 收集“流程消费点”：变量出现在“流程节点调用的入参”或控制语句条件/迭代器中
            #
            # - “流程节点”：节点函数名在节点库中且存在流程端口（含复合节点带流程口）
            # - 控制语句：if/match/for/while 本身会生成流程结构，因此其表达式视为流程消费点
            flow_consumed_lines_by_name: Dict[str, Set[int]] = {}

            def _is_self_attr_chain(expr: ast.AST) -> bool:
                """判断表达式是否为 `self.x.y...` 的属性链。"""
                current: ast.AST | None = expr
                while current is not None:
                    if isinstance(current, ast.Name):
                        return str(current.id or "").strip() == "self"
                    if isinstance(current, ast.Attribute):
                        current = current.value
                        continue
                    return False
                return False

            for ast_node in ast.walk(method):
                # A) 流程节点调用：collect args/kw.value 的 load names
                if isinstance(ast_node, ast.Call):
                    func = getattr(ast_node, "func", None)
                    call_name: str | None = None
                    is_flow_call = False
                    if isinstance(func, ast.Name):
                        call_name = str(func.id or "").strip()
                        is_flow_call = bool(call_name) and (call_name in flow_funcs)
                    elif isinstance(func, ast.Attribute) and _is_self_attr_chain(func.value):
                        call_name = str(func.attr or "").strip()
                        base = getattr(func, "value", None)
                        self_attr_name: str | None = None
                        if isinstance(base, ast.Attribute) and isinstance(getattr(base, "value", None), ast.Name):
                            if str(getattr(base.value, "id", "") or "").strip() == "self":
                                self_attr_name = str(getattr(base, "attr", "") or "").strip() or None
                        if self_attr_name and call_name:
                            flow_methods = composite_flow_methods_by_self_attr.get(self_attr_name, set())
                            is_flow_call = call_name in flow_methods

                    if is_flow_call:
                        use_line = getattr(ast_node, "lineno", 0) or 0
                        if isinstance(use_line, int) and use_line > 0:
                            flow_input_names: Set[str] = set()
                            for arg in list(getattr(ast_node, "args", []) or []):
                                if isinstance(arg, ast.AST):
                                    flow_input_names.update(_collect_load_names(arg))
                            for kw in list(getattr(ast_node, "keywords", []) or []):
                                value = getattr(kw, "value", None)
                                if isinstance(value, ast.AST):
                                    flow_input_names.update(_collect_load_names(value))
                            for name_text in flow_input_names:
                                flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)

                # B) 控制语句：if/while/match/for
                if isinstance(ast_node, ast.If):
                    use_line = getattr(ast_node, "lineno", 0) or 0
                    if isinstance(use_line, int) and use_line > 0 and isinstance(ast_node.test, ast.AST):
                        for name_text in _collect_load_names(ast_node.test):
                            flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)
                if isinstance(ast_node, ast.While):
                    use_line = getattr(ast_node, "lineno", 0) or 0
                    if isinstance(use_line, int) and use_line > 0 and isinstance(ast_node.test, ast.AST):
                        for name_text in _collect_load_names(ast_node.test):
                            flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)
                if isinstance(ast_node, ast.Match):
                    use_line = getattr(ast_node, "lineno", 0) or 0
                    subject = getattr(ast_node, "subject", None)
                    if isinstance(use_line, int) and use_line > 0 and isinstance(subject, ast.AST):
                        for name_text in _collect_load_names(subject):
                            flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)
                if isinstance(ast_node, ast.For):
                    use_line = getattr(ast_node, "lineno", 0) or 0
                    iterator = getattr(ast_node, "iter", None)
                    if isinstance(use_line, int) and use_line > 0 and isinstance(iterator, ast.AST):
                        for name_text in _collect_load_names(iterator):
                            flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)

                # C) client 过滤器图：return 表达式也视为“流程消费点”（图输出）
                if is_client_filter_graph and isinstance(ast_node, ast.Return):
                    use_line = getattr(ast_node, "lineno", 0) or 0
                    value_expr = getattr(ast_node, "value", None)
                    if isinstance(use_line, int) and use_line > 0 and isinstance(value_expr, ast.AST):
                        for name_text in _collect_load_names(value_expr):
                            flow_consumed_lines_by_name.setdefault(name_text, set()).add(use_line)

            # 2) 通过“别名赋值/数据节点赋值”将流程消费回溯到更早的变量
            for _ in range(32):
                changed = False
                # 2.1) 别名：dest = src
                for dest_name, src_name, alias_line in alias_edges:
                    dest_use_lines = flow_consumed_lines_by_name.get(dest_name)
                    if not dest_use_lines:
                        continue
                    dest_store_lines = store_lines_by_name.get(dest_name, [])
                    for use_line in list(dest_use_lines):
                        if use_line <= alias_line:
                            continue
                        if _has_store_between(
                            dest_store_lines,
                            start_line_exclusive=alias_line,
                            end_line_exclusive=use_line,
                        ):
                            continue
                        src_use_lines = flow_consumed_lines_by_name.get(src_name)
                        if src_use_lines is None:
                            flow_consumed_lines_by_name[src_name] = {use_line}
                            changed = True
                        else:
                            before = len(src_use_lines)
                            src_use_lines.add(use_line)
                            if len(src_use_lines) != before:
                                changed = True

                # 2.2) 数据节点赋值：dest = 某节点调用(...src...)
                for dest_name, src_name, assign_line in call_assignment_edges:
                    dest_use_lines = flow_consumed_lines_by_name.get(dest_name)
                    if not dest_use_lines:
                        continue
                    dest_store_lines = store_lines_by_name.get(dest_name, [])
                    for use_line in list(dest_use_lines):
                        if use_line <= assign_line:
                            continue
                        if _has_store_between(
                            dest_store_lines,
                            start_line_exclusive=assign_line,
                            end_line_exclusive=use_line,
                        ):
                            continue
                        src_use_lines = flow_consumed_lines_by_name.get(src_name)
                        if src_use_lines is None:
                            flow_consumed_lines_by_name[src_name] = {use_line}
                            changed = True
                        else:
                            before = len(src_use_lines)
                            src_use_lines.add(use_line)
                            if len(src_use_lines) != before:
                                changed = True

                if not changed:
                    break

            for call_name, target_names, assigned_line in assigned_query_calls:
                has_any_used_output = False
                for name in list(target_names):
                    use_lines = flow_consumed_lines_by_name.get(name, set())
                    store_lines = store_lines_by_name.get(name, [])
                    if any(
                        isinstance(x, int)
                        and x > assigned_line
                        and (not _has_store_between(store_lines, start_line_exclusive=assigned_line, end_line_exclusive=x))
                        for x in use_lines
                    ):
                        has_any_used_output = True
                        break

                if not has_any_used_output:
                    targets_preview = "、".join(list(target_names)[:6])
                    if len(target_names) > 6:
                        targets_preview += "…"
                    issues.append(
                        EngineIssue(
                            level=self.default_level,
                            category=self.category,
                            code="CODE_UNUSED_QUERY_OUTPUT",
                            message=(
                                f"查询/运算节点『{call_name}』的输出已被接收（{targets_preview}），"
                                "但后续未将该语句产生的任何数据输出用于流程（事件/执行节点/带流程口复合节点或 if/match/for/while 控制结构）；"
                                "该节点可能是多余的纯数据孤立链路。\n"
                                "修复建议：请至少让其中一个输出进入后续流程（作为执行节点入参、分支条件、循环迭代器等），"
                                "否则建议删除该语句以减少无意义的孤立节点。"
                            ),
                            file=str(file_path),
                            line_span=str(assigned_line),
                        )
                    )

        return issues













