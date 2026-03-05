from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class VariableAnalysisResult:
    """变量分析结果"""

    assignment_counts: Dict[str, int]  # 赋值次数
    assigned_in_branch: Set[str]  # 在分支结构内被赋值的变量
    used_after_branch: Set[str]  # 在分支结构后被使用的变量


def _collect_names(target: ast.expr) -> List[str]:
    """收集赋值目标中的所有变量名"""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple):
        names: List[str] = []
        for elt in target.elts:
            names.extend(_collect_names(elt))
        return names
    return []


def _collect_used_names(node: ast.AST) -> Set[str]:
    """收集表达式中被读取的所有变量名（Load 上下文）"""
    used: Set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            used.add(sub.id)
    return used


def _stmt_assigns_to_name(stmt: ast.stmt, name: str) -> bool:
    """判断某条语句是否会为指定变量名赋值（Store）。

    说明：
    - 仅用于“占位初始化是否会被后续赋值覆盖”的线性判定；
    - 分支/循环等复杂结构由调用方选择保守处理。
    """
    name_text = str(name or "")
    if name_text == "":
        return False
    if isinstance(stmt, ast.Assign):
        for target in list(getattr(stmt, "targets", []) or []):
            if name_text in _collect_names(target):
                return True
        return False
    if isinstance(stmt, ast.AnnAssign):
        return name_text in _collect_names(getattr(stmt, "target", None))
    if isinstance(stmt, ast.AugAssign):
        return name_text in _collect_names(getattr(stmt, "target", None))
    if isinstance(stmt, ast.For):
        return name_text in _collect_names(getattr(stmt, "target", None))
    return False


def is_placeholder_annassign_overwritten_before_use(
    *,
    var_name: str,
    remaining_statements: List[ast.stmt],
) -> bool:
    """判断“带类型注解的常量占位初始化”是否会在被使用前被后续赋值覆盖。

    典型代码模式（仅用于声明/类型提示）：
      x: "整数" = 0
      x = 某个节点输出 / 解包赋值(...)[...]

    这类占位初始化在节点图语义中应被视为“声明”，不应触发【获取局部变量】建模，
    否则会在画布上产生大量零散的“获取局部变量”纯数据节点（且多数无实际连线意义）。
    """
    name_text = str(var_name or "").strip()
    if name_text == "":
        return False
    for stmt in list(remaining_statements or []):
        # 遇到复杂控制流：保守处理，避免误删真正需要的初始化
        if isinstance(stmt, (ast.If, ast.Match, ast.For, ast.While, ast.Try)):
            return False
        used_names = _collect_used_names(stmt)
        if name_text in used_names:
            return False
        if _stmt_assigns_to_name(stmt, name_text):
            return True
    return False


def analyze_variable_assignments(body: List[ast.stmt]) -> VariableAnalysisResult:
    """预先扫描方法体，分析变量的赋值和使用情况。

    收集信息：
    1. assignment_counts: 每个变量的赋值次数
    2. assigned_in_branch: 在分支结构（if/match）内被赋值的变量
    3. used_after_branch: 在分支结构后被使用的变量

    判断逻辑的关键：只有当变量在分支内被赋值，且在分支后被使用时，
    才真正需要局部变量来合并不同分支的数据流。
    """
    counts: Dict[str, int] = {}
    assigned_in_branch: Set[str] = set()
    used_after_branch: Set[str] = set()

    def _scan_assignments(stmts: List[ast.stmt], in_branch: bool = False) -> None:
        """扫描赋值语句，统计赋值次数并标记分支内赋值"""
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    for name in _collect_names(target):
                        counts[name] = counts.get(name, 0) + 1
                        if in_branch:
                            assigned_in_branch.add(name)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                for name in _collect_names(stmt.target):
                    counts[name] = counts.get(name, 0) + 1
                    if in_branch:
                        assigned_in_branch.add(name)
            elif isinstance(stmt, ast.If):
                # if/else 内部是分支结构
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.For):
                # for 循环体内也视为分支（因为可能执行 0 次或多次）
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.While):
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.Match):
                # match/case 各分支
                for case in stmt.cases:
                    _scan_assignments(case.body, in_branch=True)

    def _scan_usage_after_branch(stmts: List[ast.stmt]) -> None:
        """扫描分支结构后的变量使用"""
        pending_branch_vars: Set[str] = set()  # 当前分支结构内赋值的变量

        for idx, stmt in enumerate(stmts):
            if isinstance(stmt, (ast.If, ast.Match, ast.For, ast.While)):
                # 收集该分支结构内赋值的变量
                branch_assigned: Set[str] = set()
                if isinstance(stmt, ast.If):
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            branch_assigned.add(sub.id)
                elif isinstance(stmt, ast.Match):
                    for case in stmt.cases:
                        for sub in ast.walk(case):
                            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                                branch_assigned.add(sub.id)
                elif isinstance(stmt, (ast.For, ast.While)):
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            branch_assigned.add(sub.id)

                pending_branch_vars.update(branch_assigned)

                # 检查后续语句中是否使用了这些变量
                for later_stmt in stmts[idx + 1 :]:
                    used_names = _collect_used_names(later_stmt)
                    for name in pending_branch_vars:
                        if name in used_names:
                            used_after_branch.add(name)

                # 递归处理嵌套结构
                if isinstance(stmt, ast.If):
                    _scan_usage_after_branch(stmt.body)
                    _scan_usage_after_branch(stmt.orelse)
                elif isinstance(stmt, ast.Match):
                    for case in stmt.cases:
                        _scan_usage_after_branch(case.body)
                elif isinstance(stmt, (ast.For, ast.While)):
                    _scan_usage_after_branch(stmt.body)
                    _scan_usage_after_branch(stmt.orelse)

    _scan_assignments(body, in_branch=False)
    _scan_usage_after_branch(body)

    return VariableAnalysisResult(
        assignment_counts=counts,
        assigned_in_branch=assigned_in_branch,
        used_after_branch=used_after_branch,
    )

