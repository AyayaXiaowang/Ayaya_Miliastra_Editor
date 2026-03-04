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
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


_CUSTOM_VAR_READ_FUNCS = {"获取自定义变量"}
_CUSTOM_VAR_WRITE_FUNCS = {"设置自定义变量"}
_CUSTOM_VAR_FUNCS = _CUSTOM_VAR_READ_FUNCS | _CUSTOM_VAR_WRITE_FUNCS

_MOUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_BRACED_PLACEHOLDER_RE = re.compile(r"\{(\d+)\s*:\s*([^{}]+?)\}")


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
    ui_contract: "UiPlaceholderVarContract | None" = None

    def serialize(self) -> dict:
        return {
            "graph_roots": list(self.graph_roots),
            "scanned_files": int(self.scanned_files),
            "usages": [u.serialize() for u in self.usages],
            "summary": build_summary(self.usages),
            "ui_contract": self.ui_contract.serialize() if self.ui_contract is not None else None,
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
    literal_var_names = sorted(
        {u.var_name_literal for u in report.usages if u.var_name_literal},
        key=lambda s: s.casefold(),
    )
    lines: list[str] = []
    lines.append("# 节点图自定义变量引用审计\n")
    lines.append("## Summary\n")
    lines.append(f"- graph_roots: {', '.join(report.graph_roots) if report.graph_roots else '<empty>'}")
    lines.append(f"- scanned_files: {report.scanned_files}")
    lines.append(f"- total_usages: {summary['total_usages']}")
    lines.append(f"- literal_usages: {summary['literal_usages']}")
    lines.append(f"- dynamic_usages: {summary['dynamic_usages']}")
    lines.append(f"- unique_literal_var_names: {summary['unique_literal_var_names']}\n")

    if report.ui_contract is not None:
        ui = report.ui_contract
        lines.append("## UI 占位符变量契约（管理配置/UI源码）\n")
        lines.append(f"- ui_source_dir: {ui.ui_source_dir}")
        lines.append(f"- scanned_html_files: {ui.scanned_html_files}")
        lines.append(f"- lv_scoped_var_names: {len(ui.level_scoped_var_names)}")
        lines.append(f"- ps_scoped_var_names: {len(ui.player_scoped_var_names)}\n")

        ui_level_set = set(ui.level_scoped_var_names)
        ui_player_set = set(ui.player_scoped_var_names)
        graph_literal_set = set(literal_var_names)

        level_used_by_ui_not_in_graph = sorted(ui_level_set - graph_literal_set, key=lambda s: s.casefold())
        player_used_by_ui_not_in_graph = sorted(ui_player_set - graph_literal_set, key=lambda s: s.casefold())
        used_by_graph_not_in_ui = sorted(graph_literal_set - (ui_level_set | ui_player_set), key=lambda s: s.casefold())

        lines.append("### 差集摘要（帮助定位“UI/节点图谁在用”）\n")
        lines.append(f"- UI(lv) 用到但节点图未出现(字面量)：{len(level_used_by_ui_not_in_graph)}")
        lines.append(f"- UI(ps/p1..p8) 用到但节点图未出现(字面量)：{len(player_used_by_ui_not_in_graph)}")
        lines.append(f"- 节点图用到但 UI 未出现(字面量)：{len(used_by_graph_not_in_ui)}\n")

        def _emit_first(items: list[str], *, title: str) -> None:
            lines.append(f"### {title}\n")
            if not items:
                lines.append("- <none>\n")
                return
            for name in items[:30]:
                lines.append(f"- {name}")
            if len(items) > 30:
                lines.append(f"- ... truncated, total={len(items)}")
            lines.append("")

        _emit_first(level_used_by_ui_not_in_graph, title="UI(lv) only（first 30）")
        _emit_first(player_used_by_ui_not_in_graph, title="UI(ps/p1..p8) only（first 30）")
        _emit_first(used_by_graph_not_in_ui, title="Graph only（first 30）")
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


@dataclass(frozen=True, slots=True)
class UiPlaceholderVarContract:
    ui_source_dir: str
    scanned_html_files: int
    level_scoped_var_names: list[str]
    player_scoped_var_names: list[str]
    # var_name -> [html_file_path...]
    level_var_to_files: dict[str, list[str]]
    player_var_to_files: dict[str, list[str]]

    def serialize(self) -> dict:
        return {
            "ui_source_dir": self.ui_source_dir,
            "scanned_html_files": int(self.scanned_html_files),
            "level_scoped_var_names": list(self.level_scoped_var_names),
            "player_scoped_var_names": list(self.player_scoped_var_names),
            "level_var_to_files": dict(self.level_var_to_files),
            "player_var_to_files": dict(self.player_var_to_files),
        }


def _accept_ui_expr_to_contract(
    *,
    expr: str,
    html_path: Path,
    level_var_to_files: dict[str, set[str]],
    player_var_to_files: dict[str, set[str]],
) -> None:
    e = str(expr or "").strip()
    if not e or any(ch.isspace() for ch in e):
        return
    scope, sep, rest = e.partition(".")
    if sep != ".":
        return
    scope_lower = scope.strip().lower()
    segments = [s.strip() for s in str(rest or "").split(".") if s.strip()]
    if not segments:
        return
    var_name = segments[0]
    if not var_name:
        return
    file_key = html_path.as_posix()
    if scope_lower == "lv":
        level_var_to_files.setdefault(var_name, set()).add(file_key)
        return
    if scope_lower == "ps" or (scope_lower.startswith("p") and scope_lower[1:].isdigit()):
        player_var_to_files.setdefault(var_name, set()).add(file_key)
        return


def collect_ui_placeholder_var_contract_from_ui_source_dir(ui_source_dir: Path) -> UiPlaceholderVarContract | None:
    """从 UI源码(HTML) 中收集 lv/ps/p1..p8 根变量名集合（用于 where-used 报告）。

    注意：这里只做“占位符契约提取”，不做存在性/类型校验（校验请用 validate-ui）。
    """
    ui_source_dir = Path(ui_source_dir).resolve()
    if not ui_source_dir.exists() or not ui_source_dir.is_dir():
        return None

    html_files = sorted(
        [p for p in ui_source_dir.rglob("*.html") if p.is_file() and not p.name.lower().endswith(".flattened.html")],
        key=lambda p: p.as_posix().casefold(),
    )
    if not html_files:
        return None

    level_var_to_files: dict[str, set[str]] = {}
    player_var_to_files: dict[str, set[str]] = {}

    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        for match in _MOUSTACHE_PLACEHOLDER_RE.finditer(text):
            _accept_ui_expr_to_contract(
                expr=match.group(1),
                html_path=html_path,
                level_var_to_files=level_var_to_files,
                player_var_to_files=player_var_to_files,
            )
        for match in _BRACED_PLACEHOLDER_RE.finditer(text):
            _accept_ui_expr_to_contract(
                expr=match.group(2),
                html_path=html_path,
                level_var_to_files=level_var_to_files,
                player_var_to_files=player_var_to_files,
            )

    level_names = sorted(level_var_to_files.keys(), key=lambda s: s.casefold())
    player_names = sorted(player_var_to_files.keys(), key=lambda s: s.casefold())
    level_map = {
        k: sorted(v, key=str.casefold)
        for k, v in sorted(level_var_to_files.items(), key=lambda kv: kv[0].casefold())
    }
    player_map = {
        k: sorted(v, key=str.casefold)
        for k, v in sorted(player_var_to_files.items(), key=lambda kv: kv[0].casefold())
    }
    return UiPlaceholderVarContract(
        ui_source_dir=ui_source_dir.as_posix(),
        scanned_html_files=len(html_files),
        level_scoped_var_names=level_names,
        player_scoped_var_names=player_names,
        level_var_to_files=level_map,
        player_var_to_files=player_map,
    )

