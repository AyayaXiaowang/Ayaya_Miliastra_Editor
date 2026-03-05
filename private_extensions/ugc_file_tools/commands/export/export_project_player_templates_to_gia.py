from __future__ import annotations

"""
export_project_player_templates_to_gia.py

目标：
- 从 Graph_Generater 项目存档目录导出“玩家模板（含自定义变量）”为 `.gia`。

说明：
- 复用 `ugc_file_tools/pipelines/project_export_player_templates_gia.py` 的实现（UI/CLI 同口径）；
- 导出采用 template-driven：基于一个 base 玩家模板 `.gia`（真源导出）克隆结构，再写入名称/ID 与自定义变量列表；
- 自定义变量来源：玩家模板 JSON 的 `metadata.custom_variable_file`（兼容字符串/列表），引用 `管理配置/关卡变量/自定义变量/*.py` 中的变量文件（VARIABLE_FILE_ID）。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.console_encoding import configure_console_encoding


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="项目存档 → 导出玩家模板为 .gia（包含自定义变量；产物落盘到 ugc_file_tools/out/）。"
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="项目存档根目录路径（例如 assets/资源库/项目存档/测试项目）。",
    )
    parser.add_argument(
        "--base-gia",
        dest="base_player_template_gia_file",
        required=True,
        help=(
            "必选：结构模板 base 玩家模板 .gia（推荐：真源导出的“默认玩家模板”）。\n"
            "说明：该工具不会重编码完整 schema，仅做结构克隆 + 小范围字段补丁。"
        ),
    )
    parser.add_argument(
        "--player-template-json",
        dest="player_template_json_files",
        action="append",
        default=[],
        help="可选：仅导出指定玩家模板 JSON（可重复传参）；不传则导出当前项目 战斗预设/玩家模板/*.json。",
    )
    parser.add_argument(
        "--selection-json",
        dest="selection_json",
        default="",
        help="可选：从 JSON 文件读取要导出的玩家模板 JSON 列表（优先级高于 --player-template-json；用于避免命令行过长）。",
    )
    parser.add_argument(
        "--out-dir",
        dest="output_dir_name_in_out",
        default="",
        help="输出到 ugc_file_tools/out/ 下的子目录名（默认 <package_id>_player_template_gia_export）。",
    )
    parser.add_argument(
        "--copy-to",
        dest="output_user_dir",
        default="",
        help="可选：额外复制一份到 out 外的绝对目录（为空则不复制）。",
    )
    parser.add_argument(
        "--copy-to-beyond-export",
        dest="copy_to_beyond_export",
        action="store_true",
        help="可选：生成后复制到默认 Beyond_Local_Export。",
    )
    parser.add_argument(
        "--decode-max-depth",
        dest="base_decode_max_depth",
        type=int,
        default=16,
        help="解码 base `.gia` 的 protobuf 递归深度上限（默认 16）。",
    )
    parser.add_argument(
        "--report",
        dest="report_json",
        default="",
        help="可选：将导出 report 写入 JSON 文件（便于 UI 调用）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    base_gia = Path(str(args.base_player_template_gia_file)).resolve()
    if not base_gia.is_file() or base_gia.suffix.lower() != ".gia":
        raise FileNotFoundError(str(base_gia))

    player_template_json_files: list[Path] = []
    selection_json_text = str(getattr(args, "selection_json", "") or "").strip()
    if selection_json_text != "":
        selection_json_path = Path(selection_json_text).resolve()
        if not selection_json_path.is_file():
            raise FileNotFoundError(str(selection_json_path))
        obj = json.loads(selection_json_path.read_text(encoding="utf-8"))
        raw_list: list[str]
        if isinstance(obj, list):
            raw_list = [str(x) for x in obj]
        elif isinstance(obj, dict):
            v = obj.get("player_template_json_files")
            if v is None:
                raise KeyError("selection-json 必须为 list[str] 或包含 player_template_json_files 的 dict")
            if not isinstance(v, list):
                raise TypeError("selection-json['player_template_json_files'] 必须为 list[str]")
            raw_list = [str(x) for x in v]
        else:
            raise TypeError("selection-json 必须为 list[str] 或 dict")
        for p in raw_list:
            t = str(p or "").strip()
            if t == "":
                continue
            player_template_json_files.append(Path(t).resolve())
        if not player_template_json_files:
            raise ValueError("selection-json 为空：未选择任何玩家模板 JSON")
    else:
        player_template_json_files = [
            Path(p).resolve()
            for p in list(args.player_template_json_files or [])
            if str(p).strip() != ""
        ]

    output_user_dir_text = str(args.output_user_dir or "").strip()
    output_user_dir = Path(output_user_dir_text).resolve() if output_user_dir_text else None
    if bool(args.copy_to_beyond_export):
        output_user_dir = Path(get_beyond_local_export_dir()).resolve()

    report_json_text = str(args.report_json or "").strip()
    report_json_path = Path(report_json_text).resolve() if report_json_text else None

    from ugc_file_tools.pipelines.project_export_player_templates_gia import (
        ProjectExportPlayerTemplatesGiaPlan,
        run_project_export_player_templates_to_gia,
    )

    out_dir_name = str(args.output_dir_name_in_out or "").strip()
    if out_dir_name == "":
        out_dir_name = f"{project_root.name}_player_template_gia_export"

    plan = ProjectExportPlayerTemplatesGiaPlan(
        project_archive_path=project_root,
        base_player_template_gia_file=base_gia,
        player_template_json_files=(list(player_template_json_files) if player_template_json_files else None),
        output_dir_name_in_out=str(out_dir_name),
        output_user_dir=output_user_dir,
        base_decode_max_depth=int(args.base_decode_max_depth),
    )

    def _progress_cb(current: int, total: int, label: str) -> None:
        # 供 UI 调用（子进程 stderr 解析）：`[current/total] label`
        print(f"[{int(current)}/{int(total)}] {str(label or '').strip()}", file=sys.stderr, flush=True)

    report = run_project_export_player_templates_to_gia(plan=plan, progress_cb=_progress_cb)

    if report_json_path is not None:
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("项目存档 → 导出玩家模板 .gia 完成：")
    for k in sorted(report.keys()):
        print(f"- {k}: {report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



