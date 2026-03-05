from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from app.cli.ui_variable_validator import (
    _compute_line_col,
    _iter_valid_placeholders_in_text,
    _iter_valid_progressbar_bindings_in_text,
    _scope_set_default,
    parse_variable_path,
)

KeyPath = Tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UiVarRef:
    file_path: Path
    line: int
    column: int
    kind: str  # placeholder / progressbar_binding
    token: str
    raw_expr: str
    scope: str  # lv / ps / p1~p8
    variable_name: str
    key_path: KeyPath


@dataclass(frozen=True, slots=True)
class UiSourceDirScan:
    ui_source_dir: Path
    exists: bool
    html_file_count: int


@dataclass(frozen=True, slots=True)
class UiVarQueryResult:
    workspace_root: Path
    package_id: str
    query_expr: str
    scope_filter: str | None
    variable_name: str
    key_path_filter: KeyPath
    scanned_dirs: list[UiSourceDirScan]
    refs: list[UiVarRef]


def _iter_ui_html_files_for_query(ui_source_dir: Path) -> Iterable[Path]:
    if not ui_source_dir.exists():
        return []
    if not ui_source_dir.is_dir():
        raise ValueError(f"UI源码路径存在但不是目录：{ui_source_dir}")
    # 说明：排除 .flattened.html，避免重复统计（flattened 是派生产物）。
    return [
        p
        for p in sorted(ui_source_dir.rglob("*.html"))
        if not p.name.lower().endswith(".flattened.html")
    ]


def _parse_query_expr(expr: str, *, allowed_scopes: set[str]) -> tuple[str | None, str, KeyPath]:
    text = str(expr or "").strip()
    if not text:
        raise ValueError("缺少 expr：请传入变量名或 UI 表达式（例如 UI战斗_文本 / lv.UI战斗_文本 / ps.xxx）。")

    # 允许写成 lv.xxx 或 lv.xxx.key1.key2（会把 key_path 作为过滤器）
    if "." in text:
        scope, segments = parse_variable_path(text)
        if scope not in allowed_scopes or not segments:
            raise ValueError(
                "expr 包含 '.' 时必须使用合法作用域前缀（lv/ps/p1~p8），例如：lv.UI战斗_文本 或 ps.ui_vote。\n"
                f"当前：{text!r}"
            )
        return scope, segments[0], tuple(segments[1:])

    # 仅变量名：不限制 scope
    return None, text, ()


def _iter_matching_refs_in_html_text(
    *,
    text: str,
    file_path: Path,
    allowed_scopes: set[str],
    scope_filter: str | None,
    variable_name: str,
    key_path_filter: KeyPath,
) -> Iterable[UiVarRef]:
    for token, scope, segments, start_offset, raw_expr in _iter_valid_placeholders_in_text(
        text, allowed_scopes=allowed_scopes
    ):
        if scope_filter and scope != scope_filter:
            continue
        if not segments or segments[0] != variable_name:
            continue
        key_path = tuple(segments[1:])
        if key_path_filter and key_path[: len(key_path_filter)] != key_path_filter:
            continue
        line, column = _compute_line_col(text, start_offset)
        yield UiVarRef(
            file_path=file_path,
            line=line,
            column=column,
            kind="placeholder",
            token=token,
            raw_expr=raw_expr,
            scope=scope,
            variable_name=variable_name,
            key_path=key_path,
        )

    for token, scope, segments, start_offset, raw_expr in _iter_valid_progressbar_bindings_in_text(
        text, allowed_scopes=allowed_scopes
    ):
        if scope_filter and scope != scope_filter:
            continue
        if not segments or segments[0] != variable_name:
            continue
        if key_path_filter:
            # 进度条绑定只会产生单段变量名，不可能命中 key_path 过滤器。
            continue
        line, column = _compute_line_col(text, start_offset)
        yield UiVarRef(
            file_path=file_path,
            line=line,
            column=column,
            kind="progressbar_binding",
            token=token,
            raw_expr=raw_expr,
            scope=scope,
            variable_name=variable_name,
            key_path=(),
        )


def query_ui_var_usage(
    *,
    workspace_root: Path,
    package_id: str,
    expr: str,
    include_shared: bool,
) -> UiVarQueryResult:
    package_id_text = str(package_id or "").strip()
    if not package_id_text:
        raise ValueError("缺少 --package-id。")

    package_root = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id_text
    ).resolve()
    if not package_root.is_dir():
        raise ValueError(
            f"未找到指定项目存档：{package_id_text}（请确认目录存在：{package_root}）。"
        )

    allowed_scopes = _scope_set_default()
    scope_filter, variable_name, key_path_filter = _parse_query_expr(expr, allowed_scopes=allowed_scopes)

    ui_source_dirs: list[Path] = []
    if bool(include_shared):
        ui_source_dirs.append((workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve())
    ui_source_dirs.append((package_root / "管理配置" / "UI源码").resolve())

    scanned_dirs: list[UiSourceDirScan] = []
    refs: list[UiVarRef] = []

    for ui_source_dir in ui_source_dirs:
        html_files = list(_iter_ui_html_files_for_query(ui_source_dir))
        scanned_dirs.append(
            UiSourceDirScan(
                ui_source_dir=ui_source_dir,
                exists=ui_source_dir.is_dir(),
                html_file_count=len(html_files),
            )
        )
        for file_path in html_files:
            text = file_path.read_text(encoding="utf-8")
            refs.extend(
                list(
                    _iter_matching_refs_in_html_text(
                        text=text,
                        file_path=file_path,
                        allowed_scopes=allowed_scopes,
                        scope_filter=scope_filter,
                        variable_name=variable_name,
                        key_path_filter=key_path_filter,
                    )
                )
            )

    return UiVarQueryResult(
        workspace_root=workspace_root,
        package_id=package_id_text,
        query_expr=str(expr or "").strip(),
        scope_filter=scope_filter,
        variable_name=variable_name,
        key_path_filter=key_path_filter,
        scanned_dirs=scanned_dirs,
        refs=refs,
    )


def _scope_sort_key(scope: str) -> tuple[int, str]:
    order = {"lv": 0, "ps": 1, "p1": 2, "p2": 3, "p3": 4, "p4": 5, "p5": 6, "p6": 7, "p7": 8, "p8": 9}
    return order.get(str(scope or "").strip().lower(), 999), str(scope or "").strip().lower()


def _format_path_for_display(path: Path, *, workspace_root: Path) -> str:
    if path.is_relative_to(workspace_root):
        return str(path.relative_to(workspace_root)).replace("\\", "/")
    return str(path)


def format_ui_var_query_result_text(result: UiVarQueryResult, *, show_locations: bool) -> str:
    refs = list(result.refs or [])
    used = bool(refs)

    refs_by_scope: dict[str, list[UiVarRef]] = {}
    for ref in refs:
        refs_by_scope.setdefault(ref.scope, []).append(ref)

    scopes = sorted(refs_by_scope.keys(), key=_scope_sort_key)
    used_scopes_text = ", ".join(scopes) if scopes else "<none>"

    entity_hints: list[str] = []
    if any(s == "lv" for s in scopes):
        entity_hints.append("- UI 以 lv 作用域引用：节点图读写通常应选择【关卡实体】作为目标实体。")
    if any(s != "lv" for s in scopes):
        entity_hints.append("- UI 以 ps/pN 作用域引用：节点图读写通常应选择【玩家实体】作为目标实体。")
    if ("lv" in scopes) and any(s != "lv" for s in scopes):
        entity_hints.append("- 注意：同名变量同时出现在 lv 与 ps/pN 中会增加歧义；建议避免同名或用更清晰命名拆分。")

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("ui-var：UI 变量引用查询（HTML 占位符 + 进度条绑定）")
    lines.append(f"- package_id: {result.package_id}")
    lines.append(f"- query:      {result.query_expr}")
    if result.scope_filter:
        lines.append(f"- scope:      {result.scope_filter}")
    lines.append(f"- var_name:   {result.variable_name}")
    if result.key_path_filter:
        lines.append(f"- key_path:   {'.'.join(result.key_path_filter)}")
    lines.append("")
    lines.append("扫描范围（UI源码目录）:")
    for scan in result.scanned_dirs:
        status = "OK" if scan.exists else "MISSING"
        lines.append(
            f"- [{status}] { _format_path_for_display(scan.ui_source_dir, workspace_root=result.workspace_root) }"
            f"  (html={scan.html_file_count})"
        )
    lines.append("")
    lines.append(f"结果: {'已引用' if used else '未发现引用'}")
    lines.append(f"- scopes: {used_scopes_text}")
    if entity_hints:
        lines.append("")
        lines.append("写节点图时的提示:")
        lines.extend(entity_hints)

    if used:
        lines.append("")
        lines.append("引用点（按 scope 分组）:")
        for scope in scopes:
            bucket = refs_by_scope.get(scope, [])
            # 文件去重 + 稳定排序
            files = sorted({ref.file_path for ref in bucket}, key=lambda p: str(p).casefold())
            lines.append(f"- {scope}: files={len(files)} refs={len(bucket)}")
            for file_path in files:
                display_path = _format_path_for_display(file_path, workspace_root=result.workspace_root)
                if not show_locations:
                    lines.append(f"  - {display_path}")
                    continue
                # show_locations：更像 grep，列出每个引用点
                for ref in sorted(
                    [r for r in bucket if r.file_path == file_path],
                    key=lambda r: (r.line, r.column, r.kind, r.raw_expr),
                ):
                    suffix = ""
                    if ref.key_path:
                        suffix = f"  (key={'.'.join(ref.key_path)})"
                    lines.append(
                        f"  - {display_path}:{ref.line}:{ref.column}  {ref.raw_expr}{suffix}"
                    )

    lines.append("")
    lines.append("备注:")
    lines.append("- 本命令仅统计“语法合法”的 UI 引用点；若要发现拼写错误/非法占位符，请先运行：")
    lines.append(f"  python -X utf8 -m app.cli.graph_tools validate-ui --package-id \"{result.package_id}\"")
    lines.append("=" * 80)
    return "\n".join(lines)


def serialize_ui_var_query_result_json(result: UiVarQueryResult) -> str:
    payload = {
        "package_id": result.package_id,
        "query_expr": result.query_expr,
        "scope_filter": result.scope_filter,
        "variable_name": result.variable_name,
        "key_path_filter": list(result.key_path_filter),
        "scanned_dirs": [
            {
                "ui_source_dir": str(scan.ui_source_dir),
                "exists": bool(scan.exists),
                "html_file_count": int(scan.html_file_count),
            }
            for scan in (result.scanned_dirs or [])
        ],
        "refs": [
            {
                "file_path": str(ref.file_path),
                "line": int(ref.line),
                "column": int(ref.column),
                "kind": ref.kind,
                "token": ref.token,
                "raw_expr": ref.raw_expr,
                "scope": ref.scope,
                "variable_name": ref.variable_name,
                "key_path": list(ref.key_path),
            }
            for ref in (result.refs or [])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

