from __future__ import annotations

"""
扫描源码中直接写死的颜色值（如 #FFFFFF / #333333 / QColor("#FFF") 等）
用于辅助深色/浅色主题适配，将这些位置逐步迁移到 ThemeManager/Colors 体系下。

使用方式（在项目根目录执行）：

    python -X utf8 tools/check_hardcoded_colors.py

可选参数：传入一个或多个子目录，相对于项目根目录，例如：

    python -X utf8 tools/check_hardcoded_colors.py app/ui app/cli
"""

import re
import sys
from pathlib import Path
from typing import Iterable


HEX_COLOR_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
CSS_COLOR_PATTERN = re.compile(r"color\\s*:\\s*#[0-9a-fA-F]{3,8}", re.IGNORECASE)
QCOLOR_PATTERN = re.compile(r"QColor\\(\"#?[0-9a-fA-F]{3,8}\"\\)")

DEFAULT_ROOTS = ("app/ui",)

SKIP_PARTS = (
    "ui/foundation/theme/tokens/colors.py",
    "ui/foundation/theme/styles",
)


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        normalized = str(path).replace("\\", "/")
        should_skip = False
        for part in SKIP_PARTS:
            if part in normalized:
                should_skip = True
                break
        if should_skip:
            continue
        yield path


def scan_file(path: Path) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if HEX_COLOR_PATTERN.search(line) or CSS_COLOR_PATTERN.search(line) or QCOLOR_PATTERN.search(line):
                matches.append((index, line.rstrip("\n")))
    return matches


def main(argv: list[str]) -> int:
    project_root = Path(__file__).resolve().parents[1]
    args = argv[1:]
    roots = args if args else list(DEFAULT_ROOTS)

    any_match = False
    results: dict[Path, list[tuple[int, str]]] = {}

    for root_str in roots:
        root_path = (project_root / root_str).resolve()
        if not root_path.exists():
            print(f"[skip] 根目录不存在: {root_path}")
            continue

        print(f"=== 扫描目录: {root_path} ===")
        for source_path in iter_source_files(root_path):
            file_matches = scan_file(source_path)
            if not file_matches:
                continue
            any_match = True
            relative = source_path.relative_to(project_root)
            results[relative] = file_matches
            for line_no, text in file_matches:
                print(f"{relative}:{line_no}: {text}")

    if not any_match:
        print("未发现直接写死的颜色值。")
    else:
        print("\n扫描完成：上方列表为疑似需要迁移到主题系统的颜色字符串。")
        write_todo_markdown(project_root, results)
    return 0


def write_todo_markdown(
    project_root: Path,
    results: dict[Path, list[tuple[int, str]]],
) -> None:
    """将扫描结果写入 Markdown Todo 文件，便于按文件逐项勾选。

    约定：
    - 文件路径相对于项目根目录保存；
    - 每个命中的行作为一个待办子项，保留行号与原始文本。
    """
    if not results:
        return

    output_path = project_root / "tools" / "hardcoded_colors_todo.md"

    lines: list[str] = []
    lines.append("# 硬编码颜色整改 Todo")
    lines.append("")
    lines.append("下面列出了当前扫描到的所有硬编码颜色位置，建议按文件逐步迁移到 `ThemeManager/Colors` 体系下：")
    lines.append("")

    for relative_path in sorted(results.keys(), key=lambda p: str(p)):
        lines.append(f"- [ ] `{relative_path.as_posix()}`")
        for line_no, text in results[relative_path]:
            trimmed = text.strip()
            lines.append(f"  - [ ] L{line_no}: `{trimmed}`")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Todo 列表已写入: {output_path}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


