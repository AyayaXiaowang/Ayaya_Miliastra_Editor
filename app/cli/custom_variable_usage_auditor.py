from __future__ import annotations

"""
Custom-variable usage auditor (read-only).

目标：
- 扫描节点图源码中对“实体自定义变量”的读写调用点，生成可发现性报告（where-used）。
- 只做静态分析：不执行任何节点图逻辑、不依赖运行时环境。

说明：
- Graph Code 是合法 Python 源码，因此可用 `ast` 做静态遍历；
- 对 `变量名` 为字面量字符串的调用点可做精确索引；
- 对 `变量名` 为动态表达式的调用点，只记录表达式文本（用于人工复核与重构提示）。
"""

import ast
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


_CUSTOM_VAR_READ_FUNCS = {"获取自定义变量"}
_CUSTOM_VAR_WRITE_FUNCS = {"设置自定义变量"}
_CUSTOM_VAR_FUNCS = _CUSTOM_VAR_READ_FUNCS | _CUSTOM_VAR_WRITE_FUNCS


@dataclass(frozen=True, slots=True)
class CustomVariableUsage:
    file_path: Path
    line: int
    column: int
    func_name: str
    var_name_literal: str
    var_name_expr: str
    target_entity_expr: str

    def serialize(self) -> dict:
        return {
            "file_path": self.file_path.as_posix(),
            "line": self.line,
            "column": self.column,
            "func_name": self.func_name,
            "var_name_literal": self.var_name_literal,
            "var_name_expr": self.var_name_expr,
            "target_entity_expr": self.target_entity_expr,
        }


def _iter_py_files_under(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if path.is_file():
            yield path


def collect_graph_py_files(graph_roots: Sequence[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()
    for root in graph_roots:
        for path in _iter_py_files_under(root):
            key = path.resolve().as_posix()
            if key in seen:
                continue
            seen.add(key)
            results.append(path)
    results.sort(key=lambda p: p.as_posix())
    return results


def _safe_source_segment(source_text: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source_text, node)
    if isinstance(segment, str) and segment.strip():
        return segment.strip()
    return ""


def _extract_call_func_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _extract_kw_value_expr(source_text: str, call: ast.Call, kw_name: str) -> str:
    for kw in call.keywords:
        if kw.arg == kw_name:
            return _safe_source_segment(source_text, kw.value)
    return ""


def _extract_var_name_literal_and_expr(source_text: str, call: ast.Call) -> tuple[str, str]:
    # 优先：关键字参数 变量名="xxx"
    for kw in call.keywords:
        if kw.arg != "变量名":
            continue
        expr_text = _safe_source_segment(source_text, kw.value)
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value, expr_text or repr(kw.value.value)
        return "", expr_text

    # 兼容：有人可能写成 name="xxx"（保守支持，不鼓励）
    for kw in call.keywords:
        if kw.arg not in {"name", "var_name"}:
            continue
        expr_text = _safe_source_segment(source_text, kw.value)
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value, expr_text or repr(kw.value.value)
        return "", expr_text

    return "", ""


def _extract_target_entity_expr(source_text: str, call: ast.Call) -> str:
    # 约定：目标实体=xxx（节点 prelude 常用签名）
    expr = _extract_kw_value_expr(source_text, call, "目标实体")
    if expr:
        return expr
    # 兼容：target_entity=xxx
    expr = _extract_kw_value_expr(source_text, call, "target_entity")
    if expr:
        return expr
    return ""


def scan_custom_variable_usages(py_files: Sequence[Path]) -> list[CustomVariableUsage]:
    usages: list[CustomVariableUsage] = []
    for path in py_files:
        source_text = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source_text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _extract_call_func_name(node)
            if func_name not in _CUSTOM_VAR_FUNCS:
                continue

            var_literal, var_expr = _extract_var_name_literal_and_expr(source_text, node)
            target_entity_expr = _extract_target_entity_expr(source_text, node)
            line = int(getattr(node, "lineno", 1) or 1)
            col = int(getattr(node, "col_offset", 0) or 0) + 1

            usages.append(
                CustomVariableUsage(
                    file_path=path,
                    line=line,
                    column=col,
                    func_name=func_name,
                    var_name_literal=var_literal,
                    var_name_expr=var_expr,
                    target_entity_expr=target_entity_expr,
                )
            )
    usages.sort(key=lambda u: (u.file_path.as_posix(), u.line, u.column, u.func_name))
    return usages


@dataclass(frozen=True, slots=True)
class CustomVariableAuditReport:
    graph_roots: list[str]
    scanned_files: int
    usages: list[CustomVariableUsage]

    def serialize(self) -> dict:
        return {
            "graph_roots": list(self.graph_roots),
            "scanned_files": int(self.scanned_files),
            "usages": [u.serialize() for u in self.usages],
            "summary": build_summary(self.usages),
        }


def build_summary(usages: Sequence[CustomVariableUsage]) -> dict:
    total = len(usages)
    literal = [u for u in usages if u.var_name_literal]
    dynamic = [u for u in usages if not u.var_name_literal]
    unique_names = sorted({u.var_name_literal for u in literal if u.var_name_literal})

    by_name: dict[str, int] = {}
    for u in literal:
        by_name[u.var_name_literal] = by_name.get(u.var_name_literal, 0) + 1

    top = sorted(by_name.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    return {
        "total_usages": total,
        "literal_usages": len(literal),
        "dynamic_usages": len(dynamic),
        "unique_literal_var_names": len(unique_names),
        "top_literal_var_names": [{"name": name, "count": count} for name, count in top],
    }


def write_report(report: CustomVariableAuditReport, out_dir: Path, *, name_prefix: str = "") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{name_prefix}_" if name_prefix else ""
    json_path = (out_dir / f"{prefix}custom_vars_{timestamp}.json").resolve()
    md_path = (out_dir / f"{prefix}custom_vars_{timestamp}.md").resolve()

    json_path.write_text(json.dumps(report.serialize(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary = build_summary(report.usages)
    lines: list[str] = []
    lines.append("# 节点图自定义变量引用审计\n")
    lines.append("## Summary\n")
    lines.append(f"- graph_roots: {', '.join(report.graph_roots) if report.graph_roots else '<empty>'}")
    lines.append(f"- scanned_files: {report.scanned_files}")
    lines.append(f"- total_usages: {summary['total_usages']}")
    lines.append(f"- literal_usages: {summary['literal_usages']}")
    lines.append(f"- dynamic_usages: {summary['dynamic_usages']}")
    lines.append(f"- unique_literal_var_names: {summary['unique_literal_var_names']}\n")
    lines.append("## Top literal variable names\n")
    if summary["top_literal_var_names"]:
        for item in summary["top_literal_var_names"]:
            lines.append(f"- {item['name']}: {item['count']}")
    else:
        lines.append("- <none>")
    lines.append("\n## Usages (first 200)\n")
    for u in report.usages[:200]:
        name_text = u.var_name_literal or (u.var_name_expr or "<dynamic>")
        entity_text = u.target_entity_expr or "<unknown>"
        lines.append(
            f"- {u.file_path.as_posix()}:{u.line}:{u.column}  {u.func_name}  变量名={name_text}  目标实体={entity_text}"
        )
    if len(report.usages) > 200:
        lines.append(f"\n... truncated, total usages={len(report.usages)} (see json for full list)\n")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return json_path, md_path

