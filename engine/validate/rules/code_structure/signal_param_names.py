from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.common import (
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
)
from engine.signal import get_default_signal_repository

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    iter_class_methods,
    line_span_text,
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
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)

        # 加载全局信号定义视图（来自代码级 Schema 视图或内置常量）。
        repo = get_default_signal_repository()
        allowed_params_by_id: Dict[str, Set[str]] = repo.get_allowed_param_names_by_id()
        if not allowed_params_by_id:
            return []

        all_signals: Dict[str, Dict] = repo.get_all_payloads()

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
                if func.id != SIGNAL_SEND_NODE_TITLE:
                    continue

                # 提取“信号名”参数的字面量值，用于定位信号定义。
                signal_key = ""
                for kw in getattr(node, "keywords", []) or []:
                    name = kw.arg
                    if name != SIGNAL_NAME_PORT_NAME:
                        continue
                    value = getattr(kw, "value", None)
                    signal_key = _extract_signal_name_from_value(
                        value,
                        module_constant_strings,
                    )
                    break

                if not signal_key:
                    # 未显式指定“信号名”，交由其他规则/运行时处理。
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


__all__ = ["SignalParamNamesRule"]


