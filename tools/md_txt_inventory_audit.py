from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REPO_RELATIVE_GITIGNORE = ".gitignore"

OUTPUT_REL_DIR = Path("docs") / "diagnostics" / "md_txt_inventory"
OUTPUT_REPORT_MD_NAME = "待确认__md_txt_清单与git排除分析.md"
OUTPUT_REPORT_JSON_NAME = "md_txt_清单与git排除分析.json"

SCAN_EXTENSIONS_LOWER = frozenset({".md", ".txt"})
EXCLUDED_BASENAMES_LOWER = frozenset({"claude.md"})

PREVIEW_MAX_BYTES = 32_768
PREVIEW_MAX_LINES = 60
MAX_RULE_GROUP_EXAMPLES = 20

# To keep the report readable, we only preview file contents for "not ignored by root .gitignore".
# Ignored files are still listed (with rule/categorization), but their content is not read by default.
READ_PREVIEW_FOR_IGNORED_FILES = False


@dataclass(frozen=True)
class GitIgnoreRule:
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool
    has_slash: bool
    source_line_no: int
    source_line: str


@dataclass(frozen=True)
class GitIgnoreDecision:
    ignored: bool
    matched_rule: GitIgnoreRule | None


@dataclass(frozen=True)
class FileRecord:
    rel_posix: str
    abs_path: str
    size_bytes: int
    mtime_iso: str
    is_ignored_by_root_gitignore: bool
    ignored_by_rule: str | None
    kind: str
    summary: str
    preview: str


def _now_local_iso() -> str:
    # Use local timezone for human audit friendliness.
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _to_posix_rel_path(repo_root: Path, abs_path: Path) -> str:
    rel = abs_path.relative_to(repo_root)
    # Git ignores use forward slashes regardless of OS.
    return rel.as_posix()


def _read_text_file_preview(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        return f"<无法读取: {e!r}>", ""

    truncated = raw[:PREVIEW_MAX_BYTES]
    try:
        text = truncated.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 - keep failure visible in report
        return f"<无法解码为 utf-8: {e!r}>", ""

    lines = text.splitlines()
    preview_lines = lines[:PREVIEW_MAX_LINES]
    preview_text = "\n".join(preview_lines)
    if len(raw) > PREVIEW_MAX_BYTES:
        preview_text += "\n<... 预览已按字节截断 ...>"
    elif len(lines) > PREVIEW_MAX_LINES:
        preview_text += "\n<... 预览已按行数截断 ...>"

    summary = _summarize_from_preview(path, preview_lines)
    return summary, preview_text


def _summarize_from_preview(path: Path, preview_lines: Sequence[str]) -> str:
    joined = "\n".join(preview_lines).strip()
    if not joined:
        return "空文件或仅包含空白。"

    lower_name = path.name.lower()
    if lower_name == "readme.md":
        return "项目主入口说明（面向使用者/运行方式/依赖等）。"
    if lower_name in {"requirements.txt", "requirements-dev.txt", "constraints.txt"}:
        return "依赖/约束清单（用于可重复安装与版本收敛）。"

    joined_lower = joined.lower()
    if "todo" in joined_lower or "to-do" in joined_lower:
        return "疑似待办/任务清单（包含 TODO 关键字）。"
    if "diagnostic" in joined_lower or "audit" in joined_lower:
        return "疑似诊断/审计材料（包含 diagnostic/audit 关键字）。"

    first_non_empty = next((ln.strip() for ln in preview_lines if ln.strip()), "")
    if first_non_empty.startswith("#"):
        return f"Markdown 文档（首行标题：{first_non_empty}）。"

    if path.suffix.lower() == ".txt":
        return "纯文本说明/基线/配置片段（需要人工确认具体用途）。"
    return "文档/说明类文件（需要人工确认具体用途）。"


def _strip_trailing_spaces_preserve_escaped_hash(line: str) -> str:
    # Gitignore treats an unescaped # as comment start. We keep it simple:
    # - If line begins with \#, treat as literal #
    # - Otherwise, # at beginning starts a comment
    return line.rstrip("\n\r")


def _parse_root_gitignore(repo_root: Path) -> list[GitIgnoreRule]:
    gitignore_path = repo_root / REPO_RELATIVE_GITIGNORE
    if not gitignore_path.exists():
        return []

    text = gitignore_path.read_text(encoding="utf-8", errors="replace")
    rules: list[GitIgnoreRule] = []
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_trailing_spaces_preserve_escaped_hash(raw_line)
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue

        negated = line.startswith("!")
        body = line[1:] if negated else line
        body = body.strip()
        if not body:
            continue

        anchored = body.startswith("/")
        body = body[1:] if anchored else body

        directory_only = body.endswith("/")
        body = body[:-1] if directory_only else body

        has_slash = "/" in body

        rules.append(
            GitIgnoreRule(
                pattern=body,
                negated=negated,
                directory_only=directory_only,
                anchored=anchored,
                has_slash=has_slash,
                source_line_no=idx,
                source_line=raw_line,
            )
        )
    return rules


def _path_components(posix_rel_path: str) -> list[str]:
    parts = [p for p in posix_rel_path.split("/") if p]
    return parts


def _rule_matches_path(rule: GitIgnoreRule, posix_rel_path: str) -> bool:
    # Approximation of root .gitignore semantics:
    # - Patterns containing "/" are matched against the whole relative path.
    # - Patterns without "/" are matched against basename (files) / any directory segment (dir rules).
    # - Directory-only patterns match any file within that directory.
    parts = _path_components(posix_rel_path)
    basename = parts[-1] if parts else posix_rel_path

    if rule.directory_only:
        # Match directories by segment name when pattern has no slash;
        # otherwise match as a path prefix-ish rule.
        if not rule.has_slash and not rule.anchored:
            # Any directory segment equal/matched.
            dir_parts = parts[:-1]
            return any(fnmatch.fnmatchcase(seg, rule.pattern) for seg in dir_parts)

        # Anchored/path-based directory rule: match if path is inside a matched dir.
        # We treat it as: any prefix directory path matches the rule pattern.
        dir_parts = parts[:-1]
        for i in range(1, len(dir_parts) + 1):
            dir_prefix = "/".join(dir_parts[:i])
            if fnmatch.fnmatchcase(dir_prefix, rule.pattern):
                return True
        return False

    if rule.has_slash or rule.anchored:
        return fnmatch.fnmatchcase(posix_rel_path, rule.pattern)

    return fnmatch.fnmatchcase(basename, rule.pattern)


def _decide_root_gitignore(rules: Sequence[GitIgnoreRule], posix_rel_path: str) -> GitIgnoreDecision:
    ignored = False
    matched: GitIgnoreRule | None = None

    for rule in rules:
        if not _rule_matches_path(rule, posix_rel_path):
            continue
        matched = rule
        ignored = not rule.negated

    return GitIgnoreDecision(ignored=ignored, matched_rule=matched)


def _kind_from_path(rel_posix: str) -> str:
    lower = rel_posix.lower()
    if lower == "readme.md":
        return "入口文档"
    if lower in {"requirements.txt", "requirements-dev.txt", "constraints.txt"}:
        return "依赖清单"
    if lower.startswith("docs/diagnostics/"):
        return "诊断材料（本地留存）"
    if lower.startswith("tmp/") or lower.startswith("tmp_"):
        return "临时产物/调试输出"
    if lower.startswith("projects/"):
        return "项目资料（通常仅本地）"
    if lower.startswith("assets/"):
        return "资源/内容侧文档或基线"
    if lower.startswith("tests/"):
        return "测试基线/说明"
    return "文档/说明（待确认）"


def _list_target_files(repo_root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Avoid scanning nested git folders if any.
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            suffix_lower = Path(name).suffix.lower()
            if suffix_lower not in SCAN_EXTENSIONS_LOWER:
                continue
            if name.lower() in EXCLUDED_BASENAMES_LOWER:
                continue
            yield Path(dirpath) / name


def _build_records(repo_root: Path, rules: Sequence[GitIgnoreRule]) -> list[FileRecord]:
    records: list[FileRecord] = []
    for abs_path in _list_target_files(repo_root):
        rel_posix = _to_posix_rel_path(repo_root, abs_path)
        st = abs_path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone().replace(microsecond=0).isoformat()

        decision = _decide_root_gitignore(rules, rel_posix)
        if decision.matched_rule is None:
            ignored_by_rule = None
        else:
            ignored_by_rule = f"L{decision.matched_rule.source_line_no}: {decision.matched_rule.source_line.strip()}"

        kind = _kind_from_path(rel_posix)
        if decision.ignored and not READ_PREVIEW_FOR_IGNORED_FILES:
            summary = f"{kind}（已被根 .gitignore 排除；默认不读取内容预览）"
            preview = ""
        else:
            summary, preview = _read_text_file_preview(abs_path)
        records.append(
            FileRecord(
                rel_posix=rel_posix,
                abs_path=str(abs_path),
                size_bytes=st.st_size,
                mtime_iso=mtime,
                is_ignored_by_root_gitignore=decision.ignored,
                ignored_by_rule=ignored_by_rule,
                kind=kind,
                summary=summary,
                preview=preview,
            )
        )

    # Stable ordering for diff-friendly output.
    records.sort(key=lambda r: r.rel_posix)
    return records


def _group_ignored_by_rule(records: Sequence[FileRecord]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for rec in records:
        if not rec.is_ignored_by_root_gitignore:
            continue
        key = rec.ignored_by_rule or "<命中但无规则信息>"
        groups.setdefault(key, []).append(rec.rel_posix)
    return groups


def _write_report_md(output_dir: Path, repo_root: Path, rules: Sequence[GitIgnoreRule], records: Sequence[FileRecord]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / OUTPUT_REPORT_MD_NAME

    ignored_count = sum(1 for r in records if r.is_ignored_by_root_gitignore)
    not_ignored_count = len(records) - ignored_count
    ignored_groups = _group_ignored_by_rule(records)
    not_ignored_records = [r for r in records if not r.is_ignored_by_root_gitignore]
    ignored_records = [r for r in records if r.is_ignored_by_root_gitignore]

    lines: list[str] = []
    lines.append("# 待确认：仓库内非 claude.md 的 .md/.txt 清单与 git 排除分析")
    lines.append("")
    lines.append(f"- 生成时间：{_now_local_iso()}")
    lines.append(f"- 仓库根目录：`{repo_root}`")
    lines.append(f"- 扫描范围：后缀为 `.md`/`.txt`，且文件名不为 `claude.md`（大小写不敏感）。")
    lines.append(f"- gitignore 判定：仅基于根目录 `{REPO_RELATIVE_GITIGNORE}` 做近似匹配（不含子目录 `.gitignore`，因为本仓库未发现）。")
    lines.append(f"- 内容预览策略：默认仅对**未被根 `.gitignore` 排除**的文件抽取内容预览；被排除的文件只做路径/规则/类型汇总，以避免报告爆炸。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 总文件数：**{len(records)}**")
    lines.append(f"- 可能被 `.gitignore` 排除：**{ignored_count}**")
    lines.append(f"- 可能会被 git 纳入（未被排除）：**{not_ignored_count}**")
    lines.append("")

    lines.append("## 重点：未被 `.gitignore` 排除的文件（最可能进入仓库，建议逐个确认）")
    lines.append("")

    for rec in not_ignored_records:
        rule_text = rec.ignored_by_rule or "<未命中任何根 .gitignore 规则>"
        lines.append(f"### `{rec.rel_posix}`")
        lines.append("")
        lines.append(f"- **类型**：{rec.kind}")
        lines.append(f"- **大小**：{rec.size_bytes} bytes")
        lines.append(f"- **修改时间**：{rec.mtime_iso}")
        lines.append(f"- **根 .gitignore 排除**：否（可能会进仓库）")
        lines.append(f"- **规则命中**：{rule_text}")
        lines.append(f"- **用途摘要**：{rec.summary}")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>预览（前若干行）</summary>")
        lines.append("")
        lines.append("```")
        lines.append(rec.preview if rec.preview else "<无预览>")
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("## 参考：已被 `.gitignore` 排除的文件（按规则分组统计）")
    lines.append("")
    lines.append("这些文件通常不会进入仓库（除非强行 `git add -f`）。本节按命中的根 `.gitignore` 规则分组，方便你定位“哪些目录在产生大量本地文档/日志”。")
    lines.append("")

    for rule_key in sorted(ignored_groups.keys()):
        paths = ignored_groups[rule_key]
        lines.append(f"### 规则：{rule_key}")
        lines.append("")
        lines.append(f"- **数量**：{len(paths)}")
        lines.append(f"- **示例（最多 {MAX_RULE_GROUP_EXAMPLES} 条）**：")
        for p in paths[:MAX_RULE_GROUP_EXAMPLES]:
            lines.append(f"  - `{p}`")
        if len(paths) > MAX_RULE_GROUP_EXAMPLES:
            lines.append(f"  - <... 其余 {len(paths) - MAX_RULE_GROUP_EXAMPLES} 条略 ...>")
        lines.append("")

    lines.append("## 参考：已被 `.gitignore` 排除的文件逐条简表（路径/类型/命中规则）")
    lines.append("")
    lines.append("说明：此处不提供内容预览（默认不读取被排除文件的内容），但会逐条列出以便你人工 spot-check。")
    lines.append("")
    for rec in ignored_records:
        rule_text = rec.ignored_by_rule or "<未命中任何根 .gitignore 规则>"
        lines.append(f"- `{rec.rel_posix}` — {rec.kind} — {rule_text}")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _write_report_json(output_dir: Path, records: Sequence[FileRecord]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / OUTPUT_REPORT_JSON_NAME
    payload = {
        "generated_at": _now_local_iso(),
        "records": [dataclasses.asdict(r) for r in records],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描仓库内非 claude.md 的 .md/.txt，并基于根 .gitignore 给出排除分析与用途摘要。")
    parser.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="仓库根目录（默认：当前工作目录）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f"repo-root not found: {repo_root}")

    rules = _parse_root_gitignore(repo_root)
    records = _build_records(repo_root, rules)

    out_dir = repo_root / OUTPUT_REL_DIR
    md_path = _write_report_md(out_dir, repo_root, rules, records)
    json_path = _write_report_json(out_dir, records)

    print(f"[ok] report(md): {md_path}")
    print(f"[ok] report(json): {json_path}")
    print(f"[ok] total={len(records)} ignored={sum(1 for r in records if r.is_ignored_by_root_gitignore)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

