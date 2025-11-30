from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, line_span_text
from engine.nodes.node_registry import get_node_registry


class CompositeTypesAndNestingRule(ValidationRule):
    """复合节点：参数/返回中文类型、流程入必填、禁止复合嵌套"""

    rule_id = "engine_composite_types_and_nesting"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if not ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        # 建立复合节点名称集合（用于嵌套检测）
        registry = get_node_registry(ctx.workspace_path, include_composite=True)
        lib = registry.get_library()
        composite_names: Set[str] = {nd.name for _, nd in lib.items() if getattr(nd, "is_composite", False)}

        # 找到顶层可导出函数（按常规：文件内第一个顶层 FunctionDef）
        comp_func = _find_top_level_function(tree)
        if comp_func is None:
            return issues

        # 1) 参数/返回类型：必须为中文字符串注解
        for arg in (comp_func.args.args or []):
            if arg.arg == "game":
                # 运行时对象，不强制中文注解
                continue
            ann = getattr(arg, "annotation", None)
            if not (isinstance(ann, ast.Constant) and isinstance(getattr(ann, "value", None), str)):
                issues.append(EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="COMPOSITE_ARG_CHINESE_TYPE_REQUIRED",
                    message=f"参数 '{arg.arg}' 需要中文字符串类型注解（例如：\"实体\"、\"整数列表\"）",
                    file=str(file_path),
                    line_span=line_span_text(arg) if ann is not None else None,
                ))
        # 返回类型：要求存在且为中文字符串
        ret = getattr(comp_func, "returns", None)
        if not (isinstance(ret, ast.Constant) and isinstance(getattr(ret, "value", None), str)):
            issues.append(EngineIssue(
                level=self.default_level,
                category=self.category,
                code="COMPOSITE_RETURN_CHINESE_TYPE_REQUIRED",
                message="复合节点函数需要中文字符串返回类型注解（例如：\"流程\" 或具体数据类型）",
                file=str(file_path),
                line_span=line_span_text(comp_func) if ret is not None else None,
            ))

        # 2) 流程入声明必填：要求存在名为“流程入”的参数且注解为“流程”
        flow_in_ok = False
        for arg in (comp_func.args.args or []):
            if arg.arg == "流程入":
                ann = getattr(arg, "annotation", None)
                if isinstance(ann, ast.Constant) and (getattr(ann, "value", None) == "流程"):
                    flow_in_ok = True
                break
        if not flow_in_ok:
            issues.append(EngineIssue(
                level=self.default_level,
                category=self.category,
                code="COMPOSITE_FLOW_IN_REQUIRED",
                message="复合节点必须声明参数『流程入: \"流程\"』以表明流程入口",
                file=str(file_path),
                line_span=line_span_text(comp_func),
            ))

        # 3) 禁止复合嵌套：函数体内不允许直接调用其他复合节点
        for node in ast.walk(comp_func):
            if isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name):
                fname = node.func.id
                if fname in composite_names:
                    issues.append(EngineIssue(
                        level=self.default_level,
                        category=self.category,
                        code="COMPOSITE_NESTING_FORBIDDEN",
                        message=f"{line_span_text(node)}: 禁止在复合节点内部调用其他复合节点 '{fname}'",
                        file=str(file_path),
                        line_span=line_span_text(node),
                    ))

        return issues


def _find_top_level_function(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


