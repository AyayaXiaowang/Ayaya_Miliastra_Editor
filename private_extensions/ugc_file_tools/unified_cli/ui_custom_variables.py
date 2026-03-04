from __future__ import annotations

import argparse
import json
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _command_ui_fix_custom_variables_from_html_defaults(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers.schema.custom_variable_defaults_fixer import (
        fix_custom_variables_in_gil_from_html_defaults,
    )

    input_gil = Path(arguments.input_gil_file).resolve()
    output_gil = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil.parent.mkdir(parents=True, exist_ok=True)

    html_files = [Path(p).resolve() for p in list(arguments.html_files or [])]
    if not html_files:
        raise ValueError("必须至少提供 1 个 HTML 文件（包含 data-ui-variable-defaults）。")

    report = fix_custom_variables_in_gil_from_html_defaults(
        input_gil_file_path=input_gil,
        output_gil_file_path=output_gil,
        html_file_paths=html_files,
        overwrite_dict_when_exists=bool(arguments.overwrite_dict_when_exists),
        verify=not bool(arguments.no_verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    changed = report.get("changed") if isinstance(report, dict) else None
    level_changed = 0
    player_changed = 0
    if isinstance(changed, dict):
        v1 = changed.get("关卡实体")
        v2 = None
        for k, v in changed.items():
            if str(k) != "关卡实体" and isinstance(v, list):
                v2 = v
                break
        if isinstance(v1, list):
            level_changed = len(v1)
        if isinstance(v2, list):
            player_changed = len(v2)

    print("=" * 80)
    print("自定义变量修复完成（按 HTML 的 data-ui-variable-defaults 作为权威）：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- html_files_total: {len(html_files)}")
    print(f"- specs_total: {report.get('specs_total')}")
    print(f"- changed_level_total: {level_changed}")
    print(f"- changed_player_total: {player_changed}")
    print(f"- overwrite_dict_when_exists: {report.get('overwrite_dict_when_exists')}")
    print(f"- verified: {report.get('verified')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def register_ui_custom_variables_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    parser = ui_subparsers.add_parser(
        "fix-custom-variables-from-html-defaults",
        help="按 HTML 的 data-ui-variable-defaults 修复 .gil 的实体自定义变量（补齐缺失/修正类型/修正初始值）",
    )
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser.add_argument("output_gil_file", help="输出 .gil 文件路径（会自动落到 ugc_file_tools/out/）")
    parser.add_argument(
        "html_files",
        nargs="+",
        help="HTML 文件路径（可多个；按顺序合并 defaults，后者覆盖前者同名 key）。",
    )
    parser.add_argument(
        "--overwrite-dict-when-exists",
        dest="overwrite_dict_when_exists",
        action="store_true",
        help="覆盖已存在 dict 变量的默认值（默认更安全：只保证存在/类型正确，不覆盖其键值）。",
    )
    parser.add_argument(
        "--no-verify",
        dest="no_verify",
        action="store_true",
        help="跳过写回后的逐项校验（不建议）。",
    )
    parser.add_argument("--report-json", dest="report_json", default=None, help="输出报告 JSON（落到 ugc_file_tools/out/）")
    parser.set_defaults(entrypoint=_command_ui_fix_custom_variables_from_html_defaults)

