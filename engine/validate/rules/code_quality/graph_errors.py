"""GraphModel/结构校验错误提升规则（M2/M3）。"""

from __future__ import annotations

import re
from typing import List, Set

from engine.graph.graph_code_parser import validate_graph_model

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from .graph_model_utils import _get_or_parse_graph_model

_IR_ERROR_LINE_NO_PATTERN = re.compile(r"行(?P<line_no>\d+)")
_GRAPH_VALIDATE_LINE_SPAN_PATTERN = re.compile(r"第(?P<lo>\d+)~(?P<hi>\d+)行")


def _extract_line_span_from_ir_error_text(error_text: str) -> str:
    """从 IR 错误文本中尽力提取行号（用于 issue 的 line_span）。

    约定：
    - IR 层错误通常使用 `行{n}: ...` 格式；
    - 若无法提取则返回空字符串（由上层按“文件级错误”展示）。
    """

    text = str(error_text or "").strip()
    if not text:
        return ""
    match = _IR_ERROR_LINE_NO_PATTERN.search(text)
    if match is None:
        return ""
    return str(match.group("line_no") or "").strip()


def _extract_line_span_from_graph_validate_error_text(error_text: str) -> str:
    """从 validate_graph_model 的错误文本中尽力提取行范围（用于 issue.line_span）。

    约定：validate_graph_model 产出的错误通常在末尾带 "(第X~Y行)"。
    """

    text = str(error_text or "").strip()
    if not text:
        return ""
    match = _GRAPH_VALIDATE_LINE_SPAN_PATTERN.search(text)
    if match is None:
        return ""
    lo = str(match.group("lo") or "").strip()
    hi = str(match.group("hi") or "").strip()
    if not lo or not hi:
        return ""
    return f"{lo}~{hi}"


class IrModelingErrorsRule(ValidationRule):
    """将 IR 解析阶段收集到的“无法可靠建模”错误提升为 validate 的 error。

    背景：
    - validate 阶段会关闭 strict fail-closed 以便“尽力解析”，但这类 IR 错误会导致 UI 严格模式拒绝加载；
    - 因此 validate 必须将其作为 error 暴露出来，避免“校验通过但 UI 无法显示”的漂移。
    """

    rule_id = "engine_ir_modeling_errors"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        ir_errors = graph_model.metadata.get("ir_errors")
        if not isinstance(ir_errors, list):
            return []

        unique_error_texts: List[str] = []
        seen_error_texts: Set[str] = set()
        for raw in ir_errors:
            error_text = str(raw or "").strip()
            if not error_text:
                continue
            if error_text in seen_error_texts:
                continue
            seen_error_texts.add(error_text)
            unique_error_texts.append(error_text)

        issues: List[EngineIssue] = []
        for error_text in unique_error_texts:
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="IR_MODELING_ERROR",
                    message=error_text,
                    file=str(ctx.file_path),
                    line_span=_extract_line_span_from_ir_error_text(error_text),
                )
            )
        return issues


class GraphStructuralErrorsRule(ValidationRule):
    """将图结构校验（validate_graph_model）错误提升为 validate 的 error。

    背景：
    - UI/资源加载常用 strict fail-closed：会在解析后执行 validate_graph_model，结构错误将直接拒绝加载；
    - validate_files 默认走“尽力解析”（strict=False），此前不会执行 validate_graph_model，
      导致出现“validate_file 通过但 UI 严格模式拒绝加载”的漂移；
    - 本规则补齐该差距：在 validate 阶段对可解析的 GraphModel 执行一次结构校验，并输出为 error。

    对齐 strict 行为：
    - 若 IR 已产出 `ir_errors`，strict 会优先拒绝解析并不再执行 validate_graph_model；
      因此本规则在存在 ir_errors 时跳过结构校验，避免噪声与重复报错。
    """

    rule_id = "engine_code_graph_structural_errors"
    category = "节点图结构"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        ir_errors = graph_model.metadata.get("ir_errors")
        if isinstance(ir_errors, list) and any(str(x or "").strip() for x in ir_errors):
            return []

        # 使用 include_composite=True 的节点库口径与 GraphCodeParser 一致，避免复合节点端口类型缺失
        from engine.nodes.node_registry import get_node_registry
        from ...comprehensive_graph_checks import describe_graph_error

        node_library = ctx.node_library
        if not node_library:
            registry = get_node_registry(ctx.workspace_path, include_composite=True)
            node_library = registry.get_library()
            ctx.node_library = node_library

        structural_errors = validate_graph_model(
            graph_model,
            workspace_path=ctx.workspace_path,
            node_library=node_library,
        )
        if not structural_errors:
            return []

        issues: List[EngineIssue] = []
        for error_text in structural_errors:
            category, suggestion, code = describe_graph_error(str(error_text or ""))
            message = str(error_text or "").strip()
            if suggestion:
                message = f"{message}\n建议：{suggestion}"
            span = _extract_line_span_from_graph_validate_error_text(str(error_text or ""))
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=category or self.category,
                    code=code or "CONNECTION_STRUCTURE",
                    message=message,
                    file=str(ctx.file_path),
                    line_span=(span or None),
                )
            )
        return issues