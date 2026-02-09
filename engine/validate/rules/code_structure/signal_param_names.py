from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.common import (
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_STATIC_INPUTS,
)
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.signal import get_default_signal_repository
from engine.utils.resource_library_layout import find_containing_resource_root
from engine.validate.node_semantics import SEMANTIC_SIGNAL_SEND, is_semantic_node_call

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
from .resource_scope_utils import (
    relative_path_text,
    resource_root_id,
    try_build_graph_resource_scope,
)


class SignalParamNamesRule(ValidationRule):
    """发送信号：调用中使用的参数名必须出现在信号定义的参数列表中。

    场景：
    - 程序员在 Graph Code 中直接写 `发送信号(self.game, 信号名="xxx", 不存在的参数=1)`。
    - 若 `不存在的参数` 不在信号 `xxx` 的参数定义里，则视为错误，防止“写错参数名但静默被忽略”。
    """

    rule_id = "engine_code_signal_param_names"
    category = "信号系统"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        definition_schema_view = get_default_definition_schema_view()
        signal_sources = definition_schema_view.get_all_signal_definition_sources()
        graph_scope = try_build_graph_resource_scope(ctx.workspace_path, file_path)

        # 加载全局信号定义视图（来自代码级 Schema 视图或内置常量）。
        repo = get_default_signal_repository()
        allowed_params_by_id: Dict[str, Set[str]] = repo.get_allowed_param_names_by_id()

        issues: List[EngineIssue] = []
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                # 仅关心【发送信号】节点调用
                if not is_semantic_node_call(
                    workspace_path=ctx.workspace_path,
                    scope=scope,
                    call_name=func.id,
                    semantic_id=SEMANTIC_SIGNAL_SEND,
                ):
                    continue

                # 提取“信号名”参数的字面量值，用于定位信号定义。
                signal_key = ""
                has_signal_name_kw = False
                for kw in getattr(node, "keywords", []) or []:
                    name = kw.arg
                    if name != SIGNAL_NAME_PORT_NAME:
                        continue
                    has_signal_name_kw = True
                    value = getattr(kw, "value", None)
                    signal_key = _extract_signal_name_from_value(
                        value,
                        module_constant_strings,
                    )
                    break

                if has_signal_name_kw and (not signal_key):
                    msg = (
                        f"{line_span_text(node)}: 【发送信号】的“{SIGNAL_NAME_PORT_NAME}”是静态配置端口，"
                        f"不支持连线/引脚/运行期表达式；必须使用非空字符串字面量，"
                        f"或引用模块顶层字符串常量。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_SIGNAL_NAME_NOT_STATIC",
                            msg,
                        )
                    )
                    continue

                if not signal_key:
                    # 未显式指定“信号名”，交由其他规则/运行时处理（必填入参等）。
                    continue

                # 根据 signal_name 反查信号定义。
                # 约定：Graph Code 中“信号名”参数必须使用『信号名称』，禁止直接填写信号 ID；
                # 若发现填写的是某个 signal_id，则单独报错提示改为使用名称。
                signal_id = ""
                resolved_id = repo.resolve_id_by_name(signal_key)
                if resolved_id:
                    signal_id = resolved_id
                else:
                    # 未匹配到任何名称，进一步判断是否误用 ID。
                    payload = repo.get_payload(signal_key)
                    if payload is not None:
                        signal_display_name = str(payload.get("signal_name") or signal_key).strip() or signal_key
                        if graph_scope is not None:
                            cross_issue = _maybe_collect_cross_project_signal_issue(
                                rule=self,
                                file_path=file_path,
                                at=node,
                                graph_scope=graph_scope,
                                signal_id=signal_key,
                                signal_display_name=signal_display_name,
                                signal_sources=signal_sources,
                            )
                            if cross_issue is not None:
                                issues.append(cross_issue)
                                continue
                        signal_display_name = str(payload.get("signal_name") or signal_key)
                        msg = (
                            f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                            f"是信号 ID，请改为使用该信号的名称 '{signal_display_name}' "
                            f"作为“信号名”参数；信号 ID 仅用于事件名或内部绑定，不应用于 Graph Code。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_SIGNAL_ID_NOT_ALLOWED",
                                msg,
                            )
                        )
                        continue

                    # 兼容：用户可能误把“信号 ID 的前缀（去掉 `__<package_id>` 后缀）”当成信号 ID 使用。
                    # 例如：signal_all_supported_types_example → signal_all_supported_types_example__测试基础内容
                    prefix_candidates: List[str] = []
                    if "__" not in signal_key:
                        prefix = f"{signal_key}__"
                        for candidate_id in repo.get_all_payloads().keys():
                            if isinstance(candidate_id, str) and candidate_id.startswith(prefix):
                                prefix_candidates.append(candidate_id)
                    if prefix_candidates:
                        prefix_candidates.sort(key=lambda x: str(x).casefold())
                        chosen_id = prefix_candidates[0]
                        chosen_payload = repo.get_payload(chosen_id) or {}
                        signal_display_name = (
                            str(chosen_payload.get("signal_name") or chosen_id).strip() or chosen_id
                        )

                        msg = (
                            f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                            f"看起来是信号 ID 的前缀，请改为使用该信号的名称 '{signal_display_name}' "
                            f"作为“信号名”参数；信号 ID 仅用于事件名或内部绑定，不应用于 Graph Code。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_SIGNAL_ID_NOT_ALLOWED",
                                msg,
                            )
                        )
                        continue

                    # 兼容：用户可能误把“信号 ID 的前缀（去掉 `__<package_id>` 后缀）”当成信号 ID 使用。
                    # 例如：signal_all_supported_types_example → signal_all_supported_types_example__测试基础内容
                    prefix_candidates: List[str] = []
                    if "__" not in signal_key:
                        prefix = f"{signal_key}__"
                        for candidate_id in repo.get_all_payloads().keys():
                            if isinstance(candidate_id, str) and candidate_id.startswith(prefix):
                                prefix_candidates.append(candidate_id)
                    if prefix_candidates:
                        prefix_candidates.sort(key=lambda x: str(x).casefold())
                        chosen_id = prefix_candidates[0]
                        chosen_payload = repo.get_payload(chosen_id) or {}
                        signal_display_name = (
                            str(chosen_payload.get("signal_name") or chosen_id).strip() or chosen_id
                        )

                        msg = (
                            f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                            f"看起来是信号 ID 的前缀，请改为使用该信号的名称 '{signal_display_name}' "
                            f"作为“信号名”参数；信号 ID 仅用于事件名或内部绑定，不应用于 Graph Code。"
                        )
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_SIGNAL_ID_NOT_ALLOWED",
                                msg,
                            )
                        )
                        continue

                    msg = (
                        f"{line_span_text(node)}: 【发送信号】的“信号名”参数值 '{signal_key}' "
                        f"在当前信号定义中不存在，请先在信号管理的代码资源中定义该信号，"
                        f"或改用已有信号的名称。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_SIGNAL_UNKNOWN_ID",
                            msg,
                        )
                    )
                    continue

                # 跨项目/共享边界：信号定义必须来自“当前项目存档”或“共享”。
                if graph_scope is not None:
                    payload = repo.get_payload(signal_id) or {}
                    signal_display_name = (
                        str(payload.get("signal_name") or signal_key).strip() or signal_key
                    )
                    cross_issue = _maybe_collect_cross_project_signal_issue(
                        rule=self,
                        file_path=file_path,
                        at=node,
                        graph_scope=graph_scope,
                        signal_id=signal_id,
                        signal_display_name=signal_display_name,
                        signal_sources=signal_sources,
                    )
                    if cross_issue is not None:
                        issues.append(cross_issue)
                        continue

                allowed_params = allowed_params_by_id.get(signal_id, set())
                if not allowed_params:
                    continue

                # 收集调用中实际使用的“数据参数名”：排除静态输入端口（流程入/目标实体/信号名）。
                used_params: Set[str] = set()
                for kw in getattr(node, "keywords", []) or []:
                    name = kw.arg
                    if not isinstance(name, str) or not name:
                        continue
                    if name in static_inputs:
                        continue
                    used_params.add(name)

                extra = used_params - allowed_params
                if not extra:
                    continue

                extra_text = ", ".join(sorted(extra))
                msg = (
                    f"{line_span_text(node)}: 【发送信号】调用中使用了信号定义中不存在的参数: {extra_text}；"
                    f"这些参数在运行时不会收到任何值，请参照信号 '{signal_id}' 的参数列表修正参数名，"
                    f"或在信号管理中补充对应的参数定义。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_SIGNAL_EXTRA_PARAMS",
                        msg,
                    )
                )

        return issues


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


def _extract_signal_name_from_value(
    value_node: ast.AST | None, constant_strings: Dict[str, str]
) -> str:
    """解析“信号名”参数的取值：直接字面量或顶层命名常量。"""
    if isinstance(value_node, ast.Constant) and isinstance(
        getattr(value_node, "value", None), str
    ):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


def _maybe_collect_cross_project_signal_issue(
    *,
    rule: ValidationRule,
    file_path: Path,
    at: ast.AST,
    graph_scope,
    signal_id: str,
    signal_display_name: str,
    signal_sources: Dict[str, Path],
) -> EngineIssue | None:
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
        f"{line_span_text(at)}: 【发送信号】使用的信号『{signal_display_name}』(ID: {signal_id}) 的定义位于项目存档『{definition_owner_id}』，"
        f"但当前节点图属于项目存档『{current_owner_id}』；禁止跨项目引用信号。"
        f"请在当前项目目录『{suggest_dir}』下新建/补齐该信号定义后再使用。"
        f"（当前定义来源：{source_rel}）"
    )
    return create_rule_issue(
        rule,
        file_path,
        at,
        "CODE_SIGNAL_OUT_OF_PROJECT_SCOPE",
        message,
    )


__all__ = ["SignalParamNamesRule"]


