from __future__ import annotations

"""
tools.claude_md_audit

扫描仓库内所有 `claude.md`（Windows 下大小写等价），生成可勾选的巡检 TODO 清单。

- 会合并旧清单中的勾选状态（不会丢）。
- 默认将 `private_extensions/` 分组放在最前，便于先处理“外部插件”目录。

运行：
  python -X utf8 -m tools.claude_md_audit
  python -X utf8 -m tools.claude_md_audit --scope private_extensions
  python -X utf8 -m tools.claude_md_audit --output claude_md_audit_todolist.md
"""

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


_CHECKED_LINE_RE = re.compile(r"^- \[(?P<mark>[ xX])\]\s+`(?P<path>[^`]+)`")
_HISTORY_HEADING_RE = re.compile(
    r"(?im)^\s*#+\s*(修改记录|更新记录|变更记录|changelog|change\s+log)\b"
)


@dataclass(frozen=True, slots=True)
class ClaudeFile:
    rel_path: Path
    abs_path: Path
    issues: tuple[str, ...]
    autocheck_ok: bool


def _is_parse_status_autogen_claude(text: str) -> bool:
    return ("解析状态报告" in text) and ("自动生成" in text) and ("可重复生成" in text)


def _parse_checked_paths(existing_todolist_md: str) -> set[str]:
    checked: set[str] = set()
    for line in existing_todolist_md.splitlines():
        m = _CHECKED_LINE_RE.match(line.strip())
        if not m:
            continue
        if m.group("mark").lower() == "x":
            checked.add(m.group("path"))
    return checked


def _is_under_prefix(rel_dir: Path, prefix: Path) -> bool:
    if prefix == Path("."):
        return True
    if len(rel_dir.parts) < len(prefix.parts):
        return False
    return rel_dir.parts[: len(prefix.parts)] == prefix.parts


def _iter_claude_md_files(
    *,
    repo_root: Path,
    scope: Path | None,
    exclude_dirnames_lower: set[str],
    exclude_prefixes: Sequence[Path],
) -> Iterable[Path]:
    exclude_dirname_prefixes_lower = (".tmp_", "_tmp_", "__tmp_")
    start_dir = (repo_root / scope) if (scope and not scope.is_absolute()) else (scope or repo_root)
    start_dir = start_dir.resolve()

    for dirpath, dirnames, filenames in os.walk(start_dir):
        dir_path = Path(dirpath)
        rel_dir = dir_path.resolve().relative_to(repo_root)

        if any(_is_under_prefix(rel_dir, p) for p in exclude_prefixes):
            dirnames[:] = []
            continue

        pruned: list[str] = []
        for d in dirnames:
            dl = d.lower()
            if dl in exclude_dirnames_lower:
                continue
            if any(dl.startswith(pfx) for pfx in exclude_dirname_prefixes_lower):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        for fname in filenames:
            if fname.lower() != "claude.md":
                continue
            yield (dir_path / fname).resolve()


def _analyze_claude_md(text: str) -> tuple[str, ...]:
    issues: list[str] = []

    if "目录用途" not in text:
        issues.append("缺少「目录用途」")
    if ("当前状态" not in text) and ("当前文件" not in text):
        issues.append("缺少「当前状态」")
    if "注意事项" not in text:
        issues.append("缺少「注意事项」")

    if _HISTORY_HEADING_RE.search(text):
        issues.append("疑似包含修改/变更历史（存在相关标题）")

    lines = text.splitlines()
    if len(lines) > 400:
        issues.append(f"过长（{len(lines)} 行）")

    return tuple(issues)


def _group_order_key(top: str) -> tuple[int, str]:
    preferred = [
        "private_extensions",
        "plugins",
        "engine",
        "app",
        "assets",
        "docs",
        "tools",
        "tests",
    ]
    if top in preferred:
        return (preferred.index(top), top)
    return (999, top)


def _to_rel_path(repo_root: Path, abs_path: Path) -> Path:
    return abs_path.resolve().relative_to(repo_root.resolve())


def _build_todolist_markdown(
    *,
    repo_root: Path,
    items: Sequence[ClaudeFile],
    checked_paths: set[str],
    scope: Path | None,
) -> str:
    total = len(items)
    checked = sum(1 for it in items if str(it.rel_path).replace("\\", "/") in checked_paths)
    with_issues = sum(1 for it in items if it.issues)

    scope_display = str(scope).replace("\\", "/") if scope else "(全仓)"
    lines: list[str] = []
    lines.append("# claude.md 巡检 TODO")
    lines.append("")
    lines.append(f"- **扫描范围**：`{scope_display}`")
    lines.append(f"- **仓库根目录**：`{str(repo_root)}`")
    lines.append(f"- **总数**：{total}  |  **已勾选**：{checked}  |  **疑似有问题**：{with_issues}")
    lines.append("- **用法**：逐个打开条目对应的 `claude.md`，检查/修正后将该条目勾选为 `[x]`。")
    lines.append("- **快速筛选**：在本文件中搜索 `问题` 或 `缺少`。")
    lines.append("")

    groups: dict[str, list[ClaudeFile]] = {}
    for it in items:
        top = it.rel_path.parts[0] if it.rel_path.parts else ""
        groups.setdefault(top, []).append(it)

    for top, group_items in sorted(groups.items(), key=lambda kv: _group_order_key(kv[0])):
        group_items_sorted = sorted(group_items, key=lambda it: str(it.rel_path).lower())
        lines.append(f"## {top or '(root)'}")
        lines.append("")
        for it in group_items_sorted:
            rel_str = str(it.rel_path).replace("\\", "/")
            is_checked = rel_str in checked_paths
            mark = "x" if is_checked else " "
            suffix = f" — **问题**：{'; '.join(it.issues)}" if it.issues else ""
            lines.append(f"- [{mark}] `{rel_str}`{suffix}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan claude.md files and generate a TODO checklist.")
    parser.add_argument(
        "--root",
        type=str,
        default="",
        help="Repository root directory. Default: inferred from this script location.",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default="",
        help="Limit scanning to a subdirectory (relative to repo root), e.g. private_extensions",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output markdown path. Default: claude_md_audit_todolist.md (relative to repo root).",
    )
    parser.add_argument(
        "--auto-check-parse-status",
        action="store_true",
        help="Auto-check parse_status/* subdirectories whose claude.md matches the generated boilerplate.",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    scope = Path(args.scope) if args.scope else None
    output = Path(args.output) if args.output else Path("claude_md_audit_todolist.md")
    output_abs = (repo_root / output) if not output.is_absolute() else output

    exclude_dirnames_lower = {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".cursor",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "_debug_screenshots",
        "release",
        "tmp",
        "out",
    }
    exclude_prefixes = [
        Path("app") / "runtime" / "cache",
    ]

    old_checked: set[str] = set()
    if output_abs.is_file():
        old_checked = _parse_checked_paths(output_abs.read_text(encoding="utf-8", errors="replace"))

    abs_paths = list(
        _iter_claude_md_files(
            repo_root=repo_root,
            scope=scope,
            exclude_dirnames_lower=exclude_dirnames_lower,
            exclude_prefixes=exclude_prefixes,
        )
    )

    items: list[ClaudeFile] = []
    for p in abs_paths:
        rel = _to_rel_path(repo_root, p)
        text = p.read_text(encoding="utf-8", errors="replace")
        issues = _analyze_claude_md(text)
        rel_parts = rel.parts
        is_parse_status_subdir_claude = (
            len(rel_parts) >= 5
            and rel_parts[0] == "private_extensions"
            and rel_parts[1] == "ugc_file_tools"
            and rel_parts[2] == "parse_status"
            and rel_parts[-1].lower() == "claude.md"
        )
        autocheck_ok = is_parse_status_subdir_claude and _is_parse_status_autogen_claude(text)
        items.append(ClaudeFile(rel_path=rel, abs_path=p, issues=issues, autocheck_ok=autocheck_ok))

    checked_paths = set(old_checked)
    if args.auto_check_parse_status:
        checked_paths |= {str(it.rel_path).replace("\\", "/") for it in items if it.autocheck_ok}

    md = _build_todolist_markdown(repo_root=repo_root, items=items, checked_paths=checked_paths, scope=scope)
    output_abs.parent.mkdir(parents=True, exist_ok=True)
    output_abs.write_text(md, encoding="utf-8")

    print(f"[claude_md_audit] wrote: {output_abs}")
    print(f"[claude_md_audit] total={len(items)} checked={len(old_checked)} with_issues={sum(1 for it in items if it.issues)}")


if __name__ == "__main__":
    main()

