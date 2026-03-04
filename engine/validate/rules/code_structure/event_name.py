from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List

from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.signal import get_default_signal_repository
from engine.utils.resource_library_layout import find_containing_resource_root

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
)
from ..node_index import event_node_names
from .resource_scope_utils import (
    relative_path_text,
    resource_root_id,
    try_build_graph_resource_scope,
)


class EventNameRule(ValidationRule):
    """事件名合法性校验：register_event_handler 注册的事件名必须来源于事件节点或信号。

    额外约束：
    - 在 `register_handlers` 方法中调用 `register_event_handler` 时，事件名参数必须是字符串字面量。
      这是为了与导出链路保持一致：当前导出器仅在该位置识别字面量事件名以稳定推导【监听信号】入口。
    """

    rule_id = "engine_code_event_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        scope = infer_graph_scope(ctx)
        valid_event_names = event_node_names(ctx.workspace_path, scope)
        signal_repo = get_default_signal_repository()
        definition_schema_view = get_default_definition_schema_view()
        signal_sources = definition_schema_view.get_all_signal_definition_sources()
        graph_scope = try_build_graph_resource_scope(ctx.workspace_path, file_path)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue

                func = getattr(node, "func", None)
                is_attr_call = (
                    isinstance(func, ast.Attribute)
                    and getattr(func, "attr", "") == "register_event_handler"
                )
                is_name_call = isinstance(func, ast.Name) and func.id == "register_event_handler"
                if not (is_attr_call or is_name_call):
                    continue

                event_arg_node = None
                positional_args = getattr(node, "args", []) or []
                if positional_args:
                    event_arg_node = positional_args[0]
                else:
                    for keyword in getattr(node, "keywords", []) or []:
                        if keyword.arg in {"event", "event_name"}:
                            event_arg_node = keyword.value
                            break

                if event_arg_node is None:
                    continue

                # 导出链路兼容约束：
                # `register_handlers` 内的 register_event_handler 需要“可静态解析的事件名”，
                # 否则 Graph Code -> GraphModel 时无法稳定识别为【监听信号】事件入口。
                if (
                    getattr(method, "name", "") == "register_handlers"
                    and not _is_static_event_name_node(event_arg_node, module_constant_strings)
                ):
                    message = (
                        f"{line_span_text(event_arg_node)}: register_handlers 中调用 register_event_handler 时，"
                        "事件名必须可静态解析（字符串字面量或模块顶层字符串常量）。"
                        "当前写法会导致导出链路无法稳定识别监听信号入口，请改为：\n"
                        "- 直接写字面量，例如：\"关卡大厅_结算成功\"\n"
                        "- 或引用模块顶层常量，例如：事件名常量 = \"关卡大厅_结算成功\" 后传入事件名常量。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            event_arg_node,
                            "CODE_REGISTER_EVENT_NAME_NOT_LITERAL",
                            message,
                        )
                    )
                    continue

                event_name = _extract_event_name_from_value(
                    event_arg_node,
                    module_constant_strings,
                )
                if not event_name:
                    continue

                # 信号 ID（signal_xxx）作为事件名时放行；若其定义不在“当前项目/共享”范围内则报错。
                if event_name.startswith("signal_"):
                    if graph_scope is not None:
                        payload = signal_repo.get_payload(event_name)
                        if payload is not None:
                            signal_display_name = str(payload.get("signal_name") or event_name).strip() or event_name
                            cross_issue = _maybe_collect_cross_project_signal_issue(
                                rule=self,
                                file_path=file_path,
                                at=event_arg_node,
                                graph_scope=graph_scope,
                                signal_id=event_name,
                                signal_display_name=signal_display_name,
                                signal_sources=signal_sources,
                            )
                            if cross_issue is not None:
                                issues.append(cross_issue)
                    continue

                # 显示名称为已知信号名时同样视为合法，解析为 ID 的职责交给信号系统与图解析器。
                resolved_signal_id = signal_repo.resolve_id_by_name(event_name)
                if resolved_signal_id:
                    if graph_scope is not None:
                        payload = signal_repo.get_payload(resolved_signal_id) or {}
                        signal_display_name = (
                            str(payload.get("signal_name") or event_name).strip() or event_name
                        )
                        cross_issue = _maybe_collect_cross_project_signal_issue(
                            rule=self,
                            file_path=file_path,
                            at=event_arg_node,
                            graph_scope=graph_scope,
                            signal_id=resolved_signal_id,
                            signal_display_name=signal_display_name,
                            signal_sources=signal_sources,
                        )
                        if cross_issue is not None:
                            issues.append(cross_issue)
                    continue

                if event_name in valid_event_names:
                    continue

                message = (
                    f"{line_span_text(event_arg_node)}: 事件名 '{event_name}' 不在当前引擎事件节点列表中；"
                    f"请检查是否拼写错误，或改为使用已有事件/信号（例如通过【监听信号】节点绑定信号后使用信号ID）。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        event_arg_node,
                        "CODE_UNKNOWN_EVENT_NAME",
                        message,
                    )
                )

        return issues


__all__ = ["EventNameRule"]


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


def _extract_event_name_from_value(
    value_node: ast.AST | None, constant_strings: Dict[str, str]
) -> str:
    """解析事件名参数的取值：直接字面量或顶层命名常量。"""

    if isinstance(value_node, ast.Constant) and isinstance(
        getattr(value_node, "value", None), str
    ):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


def _is_string_literal_event_name_node(value_node: ast.AST | None) -> bool:
    if not isinstance(value_node, ast.Constant):
        return False
    return isinstance(getattr(value_node, "value", None), str)


def _is_static_event_name_node(value_node: ast.AST | None, constant_strings: Dict[str, str]) -> bool:
    """判断事件名是否可静态解析：字符串字面量或模块顶层字符串常量引用。"""

    if _is_string_literal_event_name_node(value_node):
        return True
    if isinstance(value_node, ast.Name):
        return bool(str(constant_strings.get(value_node.id, "") or "").strip())
    return False


def _maybe_collect_cross_project_signal_issue(
    *,
    rule: ValidationRule,
    file_path: Path,
    at: ast.AST | None,
    graph_scope,
    signal_id: str,
    signal_display_name: str,
    signal_sources: Dict[str, Path],
) -> EngineIssue | None:
    if at is None:
        return None
    if graph_scope is None:
        return None
    source_path = signal_sources.get(str(signal_id))
    if source_path is None:
        return None
    definition_root = find_containing_resource_root(graph_scope.resource_library_root, source_path)
    if definition_root is None:
        return None
    if graph_scope.is_definition_root_allowed(definition_root):
        return None

    definition_owner_id = resource_root_id(
        shared_root_dir=graph_scope.shared_root_dir,
        packages_root_dir=graph_scope.packages_root_dir,
        resource_root_dir=definition_root,
    )
    current_owner_id = graph_scope.graph_owner_root_id
    source_rel = relative_path_text(graph_scope.workspace_path, source_path)
    suggest_dir = relative_path_text(
        graph_scope.workspace_path,
        graph_scope.suggest_current_project_signal_dir(),
    )

    message = (
        f"{line_span_text(at)}: 信号『{signal_display_name}』(ID: {signal_id}) 的定义位于项目存档『{definition_owner_id}』，"
        f"但当前节点图属于项目存档『{current_owner_id}』；禁止跨项目引用信号。"
        f"请在当前项目目录『{suggest_dir}』下新建/补齐该信号定义后再使用。"
        f"（当前定义来源：{source_rel}）"
    )
    return create_rule_issue(
        rule=rule,
        file_path=file_path,
        at=at,
        code="CODE_SIGNAL_OUT_OF_PROJECT_SCOPE",
        message=message,
    )


