from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import scan_map_terms


def should_modify_file(file_path: Path) -> bool:
    extension = file_path.suffix.lower()
    if extension not in {".py", ".md"}:
        return False

    # 避免自修改与扫描脚本本身被改写
    if file_path.name in {"scan_map_terms.py", "replace_map_terms.py"}:
        return False

    # 项目级设计文档中的“地图”更多是比喻意义，避免自动替换为“存档”
    if "projects" in file_path.parts:
        return False

    return True


def transform_line(line_text: str, category: str, extension: str) -> str:
    """根据分类决定是否将“地图”替换为“存档”。

    约定：
    - 小地图相关行（minimap）完全跳过；
    - 资源路径与索引路径（resource_path/index_path）暂不自动修改，避免改动磁盘目录名；
    - 当前脚本只在 .py / .md 文件中生效，JSON 等资源描述留给人工确认。
    """
    if "地图" not in line_text:
        return line_text

    if extension == ".json":
        return line_text

    if category in ("minimap", "resource_path", "index_path"):
        return line_text

    return line_text.replace("地图", "存档")


def main(argv: List[str]) -> None:
    root = Path(__file__).resolve().parent.parent
    apply_changes = "--apply" in argv

    changed_files: List[Path] = []

    for file_path in scan_map_terms.iter_repository_files(root):
        if not should_modify_file(file_path):
            continue

        text = file_path.read_text(encoding="utf-8")
        if scan_map_terms.TARGET_KEYWORD not in text:
            continue

        matches = scan_map_terms.scan_file(file_path)
        if not matches:
            continue

        line_categories: Dict[int, str] = {}
        for record in matches:
            existing = line_categories.get(record.line_number)
            if existing is None:
                line_categories[record.line_number] = record.category

        lines = text.splitlines(keepends=False)
        new_lines: List[str] = []
        file_changed = False

        for index, line_text in enumerate(lines, start=1):
            category = line_categories.get(index)
            if category is None:
                new_lines.append(line_text)
                continue

            new_line = transform_line(line_text, category, file_path.suffix.lower())
            if new_line != line_text:
                file_changed = True
            new_lines.append(new_line)

        if not file_changed:
            continue

        changed_files.append(file_path)

        if apply_changes:
            new_text = "\n".join(new_lines)
            if text.endswith("\n"):
                new_text += "\n"
            file_path.write_text(new_text, encoding="utf-8")

    print("候选修改文件数量:", len(changed_files))
    for file_path in sorted(changed_files):
        print(file_path.as_posix())

    if not apply_changes:
        print()
        print("当前为 dry-run 模式（未写回文件）。要实际应用修改，请加上 --apply 参数。")


if __name__ == "__main__":
    main(sys.argv[1:])


