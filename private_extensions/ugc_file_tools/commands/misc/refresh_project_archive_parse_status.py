from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.gil_package_exporter.claude_files import write_claude_if_missing as _write_claude_if_missing
from ugc_file_tools.gil_package_exporter.file_io import write_text_file as _write_text_file
from ugc_file_tools.gil_package_exporter.parse_status import build_parse_status_markdown as _build_parse_status_markdown
from ugc_file_tools.gil_package_exporter.paths import resolve_parse_status_root_path as _resolve_parse_status_root_path
from ugc_file_tools.repo_paths import repo_root


def _resolve_default_project_archives_root() -> Path:
    return repo_root() / "assets" / "资源库" / "项目存档"


def _load_report_object(report_path: Path) -> Dict[str, Any]:
    report_object = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report_object, dict):
        raise ValueError(f"invalid report.json (expected dict): {str(report_path)!r}")
    return report_object


def refresh_one_package_parse_status(package_root: Path, parse_status_root: Path) -> Path:
    report_path = package_root / "原始解析" / "report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"report.json not found: {str(report_path)!r}")

    report_object = _load_report_object(report_path)
    validation_summary = report_object.get("validation")
    if not isinstance(validation_summary, dict):
        validation_summary = None

    parse_status_markdown = _build_parse_status_markdown(
        output_package_root=package_root,
        report_object=report_object,
        validation_summary=validation_summary,
    )

    status_package_root = parse_status_root / package_root.name
    _write_claude_if_missing(
        status_package_root,
        purpose_lines=[f"集中存放 `{package_root.name}` 的解析状态报告（自动生成）。"],
        state_lines=["解析状态会随导出/解析脚本刷新；每个存档包一份。"],
        note_lines=[
            "该目录内容可重复生成；权威数据以对应存档包目录为准。",
            "不在此文件中记录修改历史，仅保持用途/状态/注意事项的实时描述。",
        ],
    )

    status_path = status_package_root / "解析状态.md"
    _write_text_file(status_path, parse_status_markdown)
    return status_path


def main(argv: Optional[Sequence[str]] = None) -> None:
    argument_parser = argparse.ArgumentParser(
        description=(
            "从 Graph_Generater 的“项目存档”目录读取各包的 report.json，"
            "并将解析状态文档统一刷新到 ugc_file_tools/parse_status/。"
        )
    )
    argument_parser.add_argument(
        "--project-archives-root",
        dest="project_archives_root",
        default=str(_resolve_default_project_archives_root()),
        help="Graph_Generater 项目存档根目录（默认 <repo>/Graph_Generater/assets/资源库/项目存档）",
    )
    argument_parser.add_argument(
        "--parse-status-root",
        dest="parse_status_root",
        default=str(_resolve_parse_status_root_path()),
        help="解析状态输出根目录（默认 ugc_file_tools/parse_status）",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)
    project_archives_root = Path(arguments.project_archives_root)
    parse_status_root = Path(arguments.parse_status_root)

    if not project_archives_root.is_dir():
        raise FileNotFoundError(f"project archives root not found: {str(project_archives_root)!r}")

    package_roots = sorted([path for path in project_archives_root.iterdir() if path.is_dir()])
    refreshed: List[Path] = []
    skipped: List[Path] = []
    for package_root in package_roots:
        report_path = package_root / "原始解析" / "report.json"
        if not report_path.is_file():
            skipped.append(package_root)
            continue
        status_path = refresh_one_package_parse_status(package_root, parse_status_root=parse_status_root)
        refreshed.append(status_path)
        print(f"[ok] {package_root.name}: {status_path}")

    print("")
    print(f"refreshed: {len(refreshed)}")
    print(f"skipped(no report.json): {len(skipped)}")


if __name__ == "__main__":
    main()


