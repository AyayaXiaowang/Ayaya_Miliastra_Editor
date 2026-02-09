from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.utils.metadata_extractor import extract_metadata_from_docstring

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text


class CompositeNodeNameLengthRule(ValidationRule):
    """复合节点名称规范：控制 UI 展示长度，避免过长标题影响可读性。

    说明：
    - 不关心名称是否使用 `_` 分段，也不限制段数；
    - 只约束“字数”（按字符计数，不包含 `_` 与空白），避免资源库与节点标题区显示过长。
    """

    rule_id = "engine_composite_node_name_length"
    category = "复合节点"
    default_level = "error"

    max_total_length: int = 12

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if (not ctx.is_composite) or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        doc_node = tree.body[0] if tree.body and isinstance(tree.body[0], ast.Expr) else tree
        docstring = ast.get_docstring(tree) or ""
        meta = extract_metadata_from_docstring(docstring)

        node_name = str(getattr(meta, "node_name", "") or "").strip()
        if not node_name:
            return []

        issues: List[EngineIssue] = []

        # “字数”计数：不统计下划线与空白，避免把分隔符当作字数导致误判。
        normalized_name = "".join(str(node_name).split())
        counted_name = normalized_name.replace("_", "")
        counted_length = len(counted_name)
        if counted_length > int(self.max_total_length):
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="COMPOSITE_NODE_NAME_TOO_LONG",
                    message=(
                        f"复合节点名称字数不允许超过 {int(self.max_total_length)} 个字（不统计 '_' 与空白）。\n"
                        f"当前 node_name='{node_name}'（计数字符='{counted_name}'，字数={counted_length}）"
                    ),
                    file=str(file_path),
                    line_span=line_span_text(doc_node),
                )
            )

        return issues


__all__ = ["CompositeNodeNameLengthRule"]


