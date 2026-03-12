from __future__ import annotations

"""
tools.export_claude_md_paths

导出仓库内所有 `claude.md` 的绝对路径清单到一个 Markdown 文档。

设计目标：
- 独立脚本：不依赖本仓库内部模块（便于拎到项目外层运行）。
- 失败显式：路径不存在/不可写等错误直接抛出或返回非 0。

用法：
  python -X utf8 -m tools.export_claude_md_paths --repo-root <repo_root> --output <out.md>
"""

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

CLAUDE_MD_BASENAME_LOWER = "claude.md"
DEFAULT_OUTPUT_BASENAME = "claude_md_paths.md"

EXCLUDED_DIRNAMES_LOWER = frozenset(
    {
        ".git",
    }
)


def _now_local_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def iter_claude_md_abs_paths(*, repo_root: Path) -> Iterable[Path]:
    repo_root = repo_root.resolve()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDED_DIRNAMES_LOWER]
        for name in filenames:
            if name.lower() != CLAUDE_MD_BASENAME_LOWER:
                continue
            yield (Path(dirpath) / name).resolve()


def collect_claude_md_abs_paths(*, repo_root: Path) -> list[Path]:
    paths = list(iter_claude_md_abs_paths(repo_root=repo_root))
    paths.sort(key=lambda p: str(p).lower())
    return paths


def build_claude_md_paths_markdown(*, repo_root: Path, abs_paths: Sequence[Path]) -> str:
    lines: list[str] = []
    lines.append("# claude.md 完整路径清单")
    lines.append("")
    lines.append(f"- 生成时间：{_now_local_iso()}")
    lines.append(f"- 仓库根目录：`{repo_root.resolve()}`")
    lines.append(f"- 总数：**{len(abs_paths)}**")
    lines.append("")
    lines.append("## 清单（绝对路径）")
    lines.append("")
    for p in abs_paths:
        lines.append(f"- `{p}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export absolute paths of all claude.md files in a repo.")
    parser.add_argument(
        "--repo-root",
        required=True,
        help="仓库根目录（必填；建议传入绝对路径）",
    )
    parser.add_argument(
        "--output",
        default="",
        help=(
            "输出 Markdown 文件路径（可为相对路径）。"
            "默认：<repo-root>/tmp/claude_md_paths.md（建议放 tmp 以免误入库）。"
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f"repo-root not found: {repo_root}")
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo-root is not a directory: {repo_root}")

    if args.output:
        output = Path(args.output)
        output_abs = output.resolve() if output.is_absolute() else (repo_root / output).resolve()
    else:
        output_abs = (repo_root / "tmp" / DEFAULT_OUTPUT_BASENAME).resolve()

    abs_paths = collect_claude_md_abs_paths(repo_root=repo_root)
    md = build_claude_md_paths_markdown(repo_root=repo_root, abs_paths=abs_paths)

    output_abs.parent.mkdir(parents=True, exist_ok=True)
    output_abs.write_text(md, encoding="utf-8")

    print(f"[ok] wrote: {output_abs}")
    print(f"[ok] total={len(abs_paths)} repo_root={repo_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

