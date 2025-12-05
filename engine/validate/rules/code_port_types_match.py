from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text
from .node_index import (
    node_function_names,
    input_types_by_func,
    output_types_by_func,
    input_generic_constraints_by_func,
    input_enum_options_by_func,
)
from engine.nodes.port_type_system import can_connect_ports, FLOW_PORT_TYPE, ANY_PORT_TYPE, GENERIC_PORT_TYPE


_CONST_TYPE_MAP: Dict[type, str] = {
    int: "整数",
    float: "浮点数",
    str: "字符串",
    bool: "布尔值",
}


class PortTypesMatchRule(ValidationRule):
    """端口类型匹配校验
    
    能力：
    - 常量 → 中文类型映射（int/float/str/bool）
    - 嵌套节点单输出类型推断（仅当唯一非流程输出）
    - 变量类型追踪（字符串注解形式：“整数/字符串列表/实体”等）
    - 泛型输出：要求变量赋值时显式注解（否则报错）
    """

    rule_id = "engine_code_port_types_match"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        func_names = node_function_names(ctx.workspace_path)
        in_types = input_types_by_func(ctx.workspace_path)
        out_types = output_types_by_func(ctx.workspace_path)
        in_constraints = input_generic_constraints_by_func(ctx.workspace_path)
        enum_options = input_enum_options_by_func(ctx.workspace_path)

        issues: List[EngineIssue] = []

        for _, method in _iter_methods(tree):
            annotated_vars: Set[str] = _collect_annotated_vars(method)
            var_types: Dict[str, str] = _collect_var_types(method, func_names, out_types)

            # 1) 泛型输出需注解（仅针对简单“单变量 = 调用()”的赋值）
            for node in ast.walk(method):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    target_name = _single_target_name(node.targets)
                    if not target_name:
                        continue
                    f = node.value.func
                    if isinstance(f, ast.Name) and (f.id in out_types):
                        outs = _unique_data_output_type(out_types.get(f.id, []))
                        if outs == GENERIC_PORT_TYPE and (target_name not in annotated_vars):
                            issues.append(self._issue(
                                file_path,
                                node,
                                "CODE_GENERIC_OUTPUT_NEEDS_ANNOTATION",
                                f"{line_span_text(node)}: 函数 '{f.id}' 的输出为『泛型』，"
                                f"变量 '{target_name}' 需要显式中文类型注解（例如：x: \"整数\" = ...）以确定端口类型"
                            ))

            # 2) 端口类型匹配
            for call in _iter_calls_to_nodes(method, func_names):
                func_name = call.func.id  # 已保证是 ast.Name
                expect_map = in_types.get(func_name, {})
                if not expect_map:
                    continue
                for kw in getattr(call, "keywords", []) or []:
                    port_name = getattr(kw, "arg", None)
                    if not isinstance(port_name, str):
                        continue
                    expected = expect_map.get(port_name)
                    if not isinstance(expected, str):
                        continue
                    # 流程端口不在本规则检查范围
                    if expected == FLOW_PORT_TYPE:
                        continue
                    actual = self._infer_expr_type(kw.value, var_types, func_names, out_types)
                    if not actual:
                        # 无法推断类型时暂不报错，由运行时或后续规则处理
                        continue
                    n_actual = _normalize_type(actual)
                    n_expected = _normalize_type(expected)
                    allowed_types = (
                        (in_constraints.get(func_name, {}) or {}).get(port_name)
                        if func_name in in_constraints
                        else None
                    )
                    if allowed_types:
                        if not _is_type_allowed_by_constraints(n_actual, allowed_types):
                            allowed_display = "、".join(allowed_types)
                            issues.append(self._issue(
                                file_path,
                                kw.value,
                                "PORT_GENERIC_CONSTRAINT_VIOLATION",
                                f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                f"仅允许类型『{allowed_display}』，实际传入类型『{actual}』"
                            ))
                            continue
                    # 宽松兼容 + 枚举字面量校验：
                    # 当期望为『枚举』且传入是字符串常量：
                    # - 若节点定义为该端口声明了枚举候选项，则要求字面量必须落在候选集合内；
                    # - 若未声明候选项，则保持旧行为：仅按类型层面放行该字符串常量。
                    if (n_expected == "枚举") and isinstance(kw.value, ast.Constant) and isinstance(getattr(kw.value, "value", None), str):
                        enum_for_func = enum_options.get(func_name) or {}
                        enum_candidates = enum_for_func.get(port_name)
                        literal_value = str(getattr(kw.value, "value", ""))
                        if isinstance(enum_candidates, list) and len(enum_candidates) > 0:
                            if literal_value not in enum_candidates:
                                allowed_display = "、".join(enum_candidates)
                                issues.append(self._issue(
                                    file_path,
                                    kw.value,
                                    "ENUM_LITERAL_NOT_IN_OPTIONS",
                                    f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                    f"期望枚举值之一『{allowed_display}』，实际传入『{literal_value}』"
                                ))
                            # 无论枚举值是否匹配，均不再进入后续类型连线校验
                            continue
                        # 未配置候选项时，保持旧的“字符串常量视为可接受”的行为
                        continue
                    if not can_connect_ports(n_actual, n_expected):
                        issues.append(self._issue(
                            file_path,
                            kw.value,
                            "PORT_TYPE_MISMATCH",
                            f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                            f"期望类型『{expected}』，实际传入类型『{actual}』，请使用匹配的节点或显式转换/注解"
                        ))

        return issues

    def _infer_expr_type(
        self,
        expr: ast.AST,
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
    ) -> str:
        # 常量
        if isinstance(expr, ast.Constant):
            py_type = type(getattr(expr, "value", None))
            return _CONST_TYPE_MAP.get(py_type, "")
        # 变量
        if isinstance(expr, ast.Name):
            return var_types.get(expr.id, "")
        # 调用（仅支持节点函数名调用）
        if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
            fname = expr.func.id
            if fname in func_names:
                return _unique_data_output_type(out_types.get(fname, []))
        return ""

    def _issue(self, file_path: Path, at: ast.AST, code: str, msg: str) -> EngineIssue:
        return EngineIssue(
            level=self.default_level,
            category=self.category,
            code=code,
            message=msg,
            file=str(file_path),
            line_span=line_span_text(at),
        )


def _iter_methods(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node, item


def _iter_calls_to_nodes(method: ast.FunctionDef, func_names: Set[str]):
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name):
            if node.func.id in func_names:
                yield node


def _collect_annotated_vars(method: ast.FunctionDef) -> Set[str]:
    annotated: Set[str] = set()
    for node in ast.walk(method):
        if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "target", None), ast.Name):
            if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                annotated.add(node.target.id)
    return annotated


def _collect_var_types(
    method: ast.FunctionDef,
    func_names: Set[str],
    out_types: Dict[str, List[str]],
) -> Dict[str, str]:
    var_types: Dict[str, str] = {}
    # 注解优先：收集注解类型
    for node in ast.walk(method):
        if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "target", None), ast.Name):
            if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                var_types[node.target.id] = str(node.annotation.value)
    # 赋值推断：单输出数据类型
    for node in ast.walk(method):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target_name = _single_target_name(node.targets)
            if not target_name:
                continue
            f = node.value.func
            if isinstance(f, ast.Name) and (f.id in func_names):
                t = _unique_data_output_type(out_types.get(f.id, []))
                if t and t not in (FLOW_PORT_TYPE, ""):
                    var_types.setdefault(target_name, t)
    return var_types


def _single_target_name(targets: List[ast.expr]) -> Optional[str]:
    # 仅支持形如 x = ... 的简单赋值
    if len(targets) != 1:
        return None
    tgt = targets[0]
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None


def _unique_data_output_type(types: List[str]) -> str:
    if not isinstance(types, list):
        return ""
    data_types = [t for t in types if isinstance(t, str) and t and (t != FLOW_PORT_TYPE)]
    if len(data_types) == 1:
        return data_types[0]
    return ""


def _normalize_type(t: str) -> str:
    if not isinstance(t, str):
        return ""
    if t.startswith("泛型"):
        return GENERIC_PORT_TYPE
    return t


def _is_type_allowed_by_constraints(actual: str, allowed: List[str]) -> bool:
    if not isinstance(actual, str):
        return False
    if not isinstance(allowed, list):
        return True
    if actual == GENERIC_PORT_TYPE:
        # 未推断出具体类型时，不在此处阻断，交给后续规则
        return True
    return actual in allowed


