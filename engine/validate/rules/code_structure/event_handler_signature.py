from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple

from engine.signal import get_default_signal_repository

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    line_span_text,
)
from ..node_index import builtin_event_param_names_by_event, builtin_event_param_types_by_event
from engine.nodes.port_type_system import GENERIC_PORT_TYPE


def _normalize_event_name_for_handler(event_name: str) -> str:
    """将事件名规约为可用于 Python 方法名后缀的形式。"""
    return str(event_name or "").replace("/", "或")


class EventHandlerSignatureRule(ValidationRule):
    """内置事件回调签名校验：

    当 `register_event_handler` 注册的是**内置事件**（来自事件节点列表）且回调为标准命名
    `on_<事件名>` 时，校验对应方法的参数列表必须与该事件节点的输出端口一致（剔除所有流程端口）。

    背景：
    - 运行时事件派发以 keyword 形式传参时，缺参/错名会直接导致 `unexpected keyword argument` 或缺参异常；
    - 事件节点的输出端口就是回调参数的权威定义，Graph Code 不应自行删改或改名。
    """

    rule_id = "engine_code_event_handler_signature"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        scope = infer_graph_scope(ctx)
        builtin_event_params = builtin_event_param_names_by_event(ctx.workspace_path, scope)
        builtin_event_param_types = builtin_event_param_types_by_event(ctx.workspace_path, scope)
        signal_repo = get_default_signal_repository()
        issues: List[EngineIssue] = []

        for class_node in (getattr(tree, "body", []) or []):
            if not isinstance(class_node, ast.ClassDef):
                continue

            method_defs: Dict[str, ast.FunctionDef] = {}
            for item in (getattr(class_node, "body", []) or []):
                if isinstance(item, ast.FunctionDef) and isinstance(getattr(item, "name", None), str):
                    method_defs[item.name] = item

            for method in method_defs.values():
                for call_node in ast.walk(method):
                    if not isinstance(call_node, ast.Call):
                        continue
                    if not _is_register_event_handler_call(call_node):
                        continue

                    event_arg_node = _extract_event_arg_node(call_node)
                    event_name = _extract_event_name_from_value(event_arg_node, module_constant_strings)
                    if not event_name:
                        continue

                    # 信号事件：不在本规则范围（信号使用信号参数名规则与其它规则约束）
                    if event_name.startswith("signal_"):
                        continue
                    if signal_repo.resolve_id_by_name(event_name):
                        continue

                    expected_param_names = builtin_event_params.get(event_name)
                    if expected_param_names is None:
                        # 非内置事件（未知事件名）由 EventNameRule 报错；这里不重复报。
                        continue
                    expected_param_types = builtin_event_param_types.get(event_name) or {}

                    handler_arg_node = _extract_handler_arg_node(call_node)
                    if handler_arg_node is None:
                        continue

                    handler_name = _extract_handler_symbol_name(handler_arg_node)
                    if not handler_name:
                        continue

                    expected_handler_name = f"on_{_normalize_event_name_for_handler(event_name)}"
                    if handler_name != expected_handler_name:
                        # 回调命名不匹配由 EventHandlerNameRule 报错；这里不重复报。
                        continue

                    handler_def = method_defs.get(handler_name)
                    if handler_def is None:
                        # 回调不是本类方法（或未定义）；不在本规则范围。
                        continue

                    actual_param_names, signature_notes = _extract_callback_param_names(handler_def)
                    if signature_notes:
                        message = (
                            f"{line_span_text(handler_def)}: 内置事件 '{event_name}' 的回调 '{handler_name}' "
                            f"签名不允许使用 {', '.join(signature_notes)}；必须显式声明事件参数。"
                            f"期望参数（剔除流程端口，{len(expected_param_names)}个）: {expected_param_names}；"
                            f"当前参数: {actual_param_names}。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                handler_def,
                                "CODE_EVENT_HANDLER_SIGNATURE_MISMATCH",
                                message,
                            )
                        )
                        continue

                    expected_set = set(expected_param_names)
                    actual_set = set(actual_param_names)
                    missing = [name for name in expected_param_names if name not in actual_set]
                    extra = [name for name in actual_param_names if name not in expected_set]
                    if missing or extra:
                        missing_text = f"缺少: {missing}；" if missing else ""
                        extra_text = f"多余/不匹配: {extra}；" if extra else ""
                        message = (
                            f"{line_span_text(handler_def)}: 内置事件 '{event_name}' 的回调 '{handler_name}' "
                            f"参数列表必须与事件节点输出端口一致（剔除流程端口）。"
                            f"期望参数（{len(expected_param_names)}个）: {expected_param_names}；"
                            f"当前参数（{len(actual_param_names)}个）: {actual_param_names}；"
                            f"{missing_text}{extra_text}"
                            f"请以事件节点定义的输出端口为准修正回调函数参数名与数量。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                handler_def,
                                "CODE_EVENT_HANDLER_SIGNATURE_MISMATCH",
                                message,
                            )
                        )
                        continue

                    # 2) 泛型输出端口：即便用户不使用，也必须在代码里显式绑定为具体类型。
                    generic_param_names = [
                        param_name
                        for param_name in expected_param_names
                        if str(expected_param_types.get(param_name, "") or "").strip() == GENERIC_PORT_TYPE
                    ]
                    if generic_param_names:
                        explicit_param_types, conflicts = _collect_explicit_types_for_params(handler_def)
                        for generic_param_name in generic_param_names:
                            resolved_type = str(explicit_param_types.get(generic_param_name, "") or "").strip()
                            if (not resolved_type) or resolved_type == GENERIC_PORT_TYPE:
                                message = (
                                    f"{line_span_text(handler_def)}: 内置事件 '{event_name}' 的回调 '{handler_name}' "
                                    f"参数 '{generic_param_name}' 对应事件端口类型为『泛型』，必须在代码中显式注解为具体中文类型，"
                                    "即便该参数在方法体内未被使用。"
                                    "可选修复方式："
                                    f"1) 在回调签名中直接注解：`{generic_param_name}: \"整数\"`；"
                                    f"2) 在方法体内增加占位注解：`{generic_param_name}_占位: \"整数\" = {generic_param_name}`（或对同名变量自注解）。"
                                    "禁止保留为 \"泛型\"，否则无法确定该事件的泛型端口类型。"
                                )
                                issues.append(
                                    create_rule_issue(
                                        self,
                                        file_path,
                                        handler_def,
                                        "CODE_EVENT_GENERIC_OUTPUT_NEEDS_EXPLICIT_TYPE",
                                        message,
                                    )
                                )
                        for param_name, type_names in conflicts.items():
                            if param_name not in generic_param_names:
                                continue
                            joined_types = "、".join(type_names)
                            message = (
                                f"{line_span_text(handler_def)}: 内置事件 '{event_name}' 的回调 '{handler_name}' "
                                f"参数 '{param_name}' 被显式绑定了多个不同的类型（{joined_types}），"
                                "泛型端口只能绑定为单一具体类型，请统一注解。"
                            )
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    handler_def,
                                    "CODE_EVENT_GENERIC_OUTPUT_TYPE_CONFLICT",
                                    message,
                                )
                            )

        return issues


def _is_register_event_handler_call(call_node: ast.Call) -> bool:
    func = getattr(call_node, "func", None)
    is_attr_call = isinstance(func, ast.Attribute) and getattr(func, "attr", "") == "register_event_handler"
    is_name_call = isinstance(func, ast.Name) and getattr(func, "id", "") == "register_event_handler"
    return bool(is_attr_call or is_name_call)


def _extract_event_arg_node(call_node: ast.Call) -> ast.AST | None:
    positional_args = getattr(call_node, "args", []) or []
    if positional_args:
        return positional_args[0]
    for keyword in (getattr(call_node, "keywords", []) or []):
        if keyword.arg in {"event", "event_name"}:
            return keyword.value
    return None


def _extract_handler_arg_node(call_node: ast.Call) -> ast.AST | None:
    positional_args = getattr(call_node, "args", []) or []
    if len(positional_args) >= 2:
        return positional_args[1]
    for keyword in (getattr(call_node, "keywords", []) or []):
        if keyword.arg in {"handler", "callback", "func"}:
            return keyword.value
    return None


def _extract_handler_symbol_name(node: ast.AST) -> str:
    """从 handler AST 节点提取“符号名”。

    - `self.on_实体创建时` → `on_实体创建时`
    - `on_实体创建时` → `on_实体创建时`
    - 其他表达式返回空字符串（由调用方决定如何展示）
    """
    if isinstance(node, ast.Attribute) and isinstance(getattr(node, "attr", None), str):
        return node.attr
    if isinstance(node, ast.Name) and isinstance(getattr(node, "id", None), str):
        return node.id
    return ""


def _extract_callback_param_names(handler_def: ast.FunctionDef) -> Tuple[List[str], List[str]]:
    """返回 (参数名列表, 不支持语法提示列表)。

    说明：
    - 参数名列表：剔除 self 后的“显式可 keyword 绑定”的参数名（普通参数 + keyword-only 参数）。
    - 不支持语法：位置专用参数（/）、*args、**kwargs。
    """
    args = getattr(handler_def, "args", None)
    if args is None:
        return [], ["无法解析函数参数"]

    notes: List[str] = []
    posonly = list(getattr(args, "posonlyargs", []) or [])
    if posonly:
        notes.append("位置专用参数（/）")
    if getattr(args, "vararg", None) is not None:
        notes.append("*args")
    if getattr(args, "kwarg", None) is not None:
        notes.append("**kwargs")

    regular_args = [str(arg.arg) for arg in (getattr(args, "args", []) or []) if isinstance(getattr(arg, "arg", None), str)]
    if regular_args and regular_args[0] == "self":
        regular_args = regular_args[1:]
    kwonly_args = [str(arg.arg) for arg in (getattr(args, "kwonlyargs", []) or []) if isinstance(getattr(arg, "arg", None), str)]

    return (regular_args + kwonly_args), notes


def _collect_module_constant_strings(tree: ast.AST) -> Dict[str, str]:
    """收集模块顶层的字符串常量声明，支持普通与注解赋值。"""
    constant_strings: Dict[str, str] = {}
    module_body = getattr(tree, "body", []) or []
    for node in module_body:
        target_names: List[str] = []
        value_node = None
        if isinstance(node, ast.Assign):
            value_node = getattr(node, "value", None)
            for target in getattr(node, "targets", []) or []:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            value_node = getattr(node, "value", None)
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name):
                target_names.append(target.id)
        if not target_names or not isinstance(value_node, ast.Constant):
            continue
        if not isinstance(getattr(value_node, "value", None), str):
            continue
        constant_text = value_node.value.strip()
        if not constant_text:
            continue
        for target_name in target_names:
            if target_name and target_name not in constant_strings:
                constant_strings[target_name] = constant_text
    return constant_strings


def _extract_event_name_from_value(value_node: ast.AST | None, constant_strings: Dict[str, str]) -> str:
    """解析事件名参数的取值：直接字面量或顶层命名常量。"""
    if isinstance(value_node, ast.Constant) and isinstance(getattr(value_node, "value", None), str):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


def _collect_explicit_types_for_params(handler_def: ast.FunctionDef) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """收集回调方法内对“参数值”的显式类型绑定。

    允许两种写法（均要求中文类型注解为字符串常量，且不得为“泛型”）：
    1) 直接在形参上写注解：`def on_事件(..., 参数: "整数")`
    2) 通过注解赋值把参数“接到”一个带类型的变量：`占位: "整数" = 参数`

    返回：
    - types: {参数名: 类型名}
    - conflicts: {参数名: [冲突类型名...]}（同一参数被绑定到多个不同类型）
    """
    explicit_types: Dict[str, str] = {}
    conflicts: Dict[str, List[str]] = {}

    args = getattr(handler_def, "args", None)
    if args is not None:
        all_args: List[ast.arg] = []
        all_args.extend(list(getattr(args, "args", []) or []))
        all_args.extend(list(getattr(args, "kwonlyargs", []) or []))
        for arg in all_args:
            if not isinstance(arg, ast.arg) or not isinstance(getattr(arg, "arg", None), str):
                continue
            param_name = arg.arg
            if param_name == "self":
                continue
            annotation_node = getattr(arg, "annotation", None)
            if isinstance(annotation_node, ast.Constant) and isinstance(getattr(annotation_node, "value", None), str):
                type_text = annotation_node.value.strip()
                if (not type_text) or type_text == GENERIC_PORT_TYPE:
                    continue
                existing = explicit_types.get(param_name)
                if existing is None:
                    explicit_types[param_name] = type_text
                elif existing != type_text:
                    conflicts.setdefault(param_name, sorted({existing, type_text}))

    for node in ast.walk(handler_def):
        if not isinstance(node, ast.AnnAssign):
            continue
        annotation_node = getattr(node, "annotation", None)
        value_node = getattr(node, "value", None)
        if not (isinstance(annotation_node, ast.Constant) and isinstance(getattr(annotation_node, "value", None), str)):
            continue
        if not isinstance(value_node, ast.Name):
            continue
        type_text = str(annotation_node.value).strip()
        if (not type_text) or type_text == GENERIC_PORT_TYPE:
            continue
        source_param_name = str(value_node.id)

        existing = explicit_types.get(source_param_name)
        if existing is None:
            explicit_types[source_param_name] = type_text
        elif existing != type_text:
            conflicts.setdefault(source_param_name, sorted({existing, type_text}))

    return explicit_types, conflicts


__all__ = ["EventHandlerSignatureRule"]


