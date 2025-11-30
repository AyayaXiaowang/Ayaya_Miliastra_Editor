"""
代码质量规范规则：长连线检测、未使用输出、不可达代码等
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import (
    get_cached_module,
    line_span_text,
    iter_class_methods,
)
from .node_index import data_query_node_names


class LongWireRule(ValidationRule):
    """事件源实体"长连线"检测（原生规则）
    
    启发式实现：
    - 面向类结构节点图：扫描方法内将 Name('事件源实体') 作为关键字参数传递的调用
    - 统计使用行号集合与使用次数，结合配置阈值判断是否报错
    - 阈值来自 config.THRESHOLDS：
        - LONG_WIRE_USAGE_MAX（默认 2）
        - LONG_WIRE_LINE_SPAN_MIN（默认 50 行）

    说明：
    - 不依赖 runtime 巨石类的内部状态；在引擎内独立运行
    - 由于缺乏"流程节点跨度"的精确信息，此处以源码行距近似衡量跨度
    """

    rule_id = "engine_code_long_wire"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        # 仅对类结构节点图（非复合）生效，且需要文件路径
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)

        thresholds = (ctx.config or {}).get("THRESHOLDS", {})
        usage_max: int = int(thresholds.get("LONG_WIRE_USAGE_MAX", 2))
        line_span_min: int = int(thresholds.get("LONG_WIRE_LINE_SPAN_MIN", 50))
        issues: List[EngineIssue] = []

        for class_node, method in iter_class_methods(tree):
            param_names = [a.arg for a in method.args.args if isinstance(a, ast.arg)]
            if "事件源实体" not in param_names:
                continue

            usage_lines: List[int] = []

            for call in ast.walk(method):
                if isinstance(call, ast.Call):
                    for kw in getattr(call, "keywords", []):
                        val = getattr(kw, "value", None)
                        if isinstance(val, ast.Name) and val.id == "事件源实体":
                            line_number = getattr(val, "lineno", getattr(call, "lineno", None))
                            if isinstance(line_number, int):
                                usage_lines.append(line_number)

            usage_count = len(usage_lines)
            if usage_count <= usage_max:
                continue

            line_span = (max(usage_lines) - min(usage_lines)) if usage_lines else 0
            if line_span <= line_span_min:
                continue

            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="CODE_EVENT_ENTITY_LONG_WIRE",
                    message=(
                        f"方法 {class_node.name}.{method.name} 内『事件源实体』作为参数被使用 {usage_count} 次，"
                        f"源码行跨度约 {line_span} 行；建议在方法内部尽早获取局部引用或拆分流程以缩短跨越。"
                    ),
                    file=str(file_path),
                    line_span=f"{min(usage_lines)}~{max(usage_lines)}" if usage_lines else None,
                    detail={
                        "class_name": class_node.name,
                        "method": method.name,
                        "usage_count": usage_count,
                        "line_span": line_span,
                    },
                )
            )

        return issues


class UnusedQueryOutputRule(ValidationRule):
    """未使用的数据/查询输出"""

    rule_id = "engine_code_unused_query_output"
    category = "代码规范"
    default_level = "warning"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        query_funcs = data_query_node_names(ctx.workspace_path)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            assigned: Dict[str, int] = {}
            used: Set[str] = set()

            # 收集：简单赋值（x = 查询(...)）
            for node in ast.walk(method):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    fname = getattr(getattr(node.value, "func", None), "id", None)
                    if isinstance(fname, str) and (fname in query_funcs):
                        target = _single_target_name(node.targets)
                        if target:
                            lineno = getattr(node, "lineno", 0) or 0
                            assigned[target] = lineno

            # 使用：Name Load
            for node in ast.walk(method):
                if isinstance(node, ast.Name) and isinstance(getattr(node, "ctx", None), ast.Load):
                    nm = node.id
                    if nm in assigned:
                        # 必须是赋值之后的使用才算
                        if (getattr(node, "lineno", 10**9) or 10**9) > assigned[nm]:
                            used.add(nm)

            for var, line in assigned.items():
                if var not in used:
                    issues.append(EngineIssue(
                        level=self.default_level,
                        category=self.category,
                        code="CODE_UNUSED_QUERY_OUTPUT",
                        message=f"变量 '{var}' 接收了查询节点输出但后续未使用；请删除赋值或使用其值",
                        file=str(file_path),
                        line_span=str(line),
                    ))

        return issues


class UnreachableCodeRule(ValidationRule):
    """不可达代码（基础版）
    
    仅检测：函数顶层语句序列中，出现在 Return/Raise 之后的语句。
    不展开分支的全覆盖分析（保守）。
    """

    rule_id = "engine_code_unreachable"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            terminated = False
            for stmt in getattr(method, "body", []) or []:
                if terminated:
                    issues.append(EngineIssue(
                        level=self.default_level,
                        category=self.category,
                        code="CODE_UNREACHABLE_AFTER_RETURN",
                        message=f"{line_span_text(stmt)}: 该语句位于 return/raise 之后，永远不会被执行",
                        file=str(file_path),
                        line_span=line_span_text(stmt),
                    ))
                    continue
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    terminated = True
        return issues


def _single_target_name(targets: List[ast.expr]) -> str | None:
    """获取赋值目标名称（仅支持单个名称）"""
    if len(targets) != 1:
        return None
    tgt = targets[0]
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None

