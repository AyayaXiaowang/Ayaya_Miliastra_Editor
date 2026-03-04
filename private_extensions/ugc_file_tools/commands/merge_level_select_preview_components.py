from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.preview_merge.level_select_preview_components_merger import (
    merge_level_select_preview_components_in_project,
)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description=(
            "合并“选关预览”双元件关卡的展示元件（模板 decorations keep_world 合并成一个母体），并同步补丁 GraphVariables 与执行图逻辑。\n"
            "- 默认只 dry-run（不写盘）；需要显式加 --dangerous 才会生成新模板并改写节点图源码。\n"
            "- 偏移/旋转取自 player_graph 的 GraphVariableConfig default_value（无需从 .gil 反解）。\n"
        )
    )
    argument_parser.add_argument("--project-root", dest="project_root", required=True, help="项目存档根目录（例如 assets/资源库/项目存档/测试项目）")
    argument_parser.add_argument("--player-graph", dest="player_graph_file", required=True, help="玩家侧选关控制图（Graph Code .py）路径")
    argument_parser.add_argument("--executor-graph", dest="executor_graph_file", required=True, help="关卡实体侧执行图（Graph Code .py）路径")
    argument_parser.add_argument(
        "--output-name-suffix",
        dest="output_name_suffix",
        default="",
        help="可选：新生成的母体模板 name 追加后缀（用于避免与既有模板名冲突）。默认空。",
    )
    argument_parser.add_argument(
        "--dangerous",
        dest="dangerous",
        action="store_true",
        help="危险写盘：生成新模板 JSON、更新 templates_index.json、并补丁节点图源码。",
    )
    argument_parser.add_argument(
        "--report",
        dest="report_json",
        default="",
        help="可选：输出 report.json（会强制落盘到 ugc_file_tools/out/；用于 UI/批处理集成）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = merge_level_select_preview_components_in_project(
        project_root=Path(args.project_root),
        player_graph_file=Path(args.player_graph_file),
        executor_graph_file=Path(args.executor_graph_file),
        dangerous=bool(args.dangerous),
        output_name_suffix=str(args.output_name_suffix or ""),
    )

    report_text = str(args.report_json or "").strip()
    report_path: Optional[Path] = None
    if report_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_text), default_file_name="merge_level_select_preview_components.report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("选关预览展示元件合并完成：")
    print(f"- project_root: {result.get('project_root')}")
    print(f"- merged_levels: {result.get('merged_levels')}")
    print(f"- dangerous: {result.get('dangerous')}")
    print(f"- generated_templates: {len(list(result.get('generated_templates') or []))}")
    if report_path is not None:
        print(f"- report_json: {str(report_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

