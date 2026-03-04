from __future__ import annotations

"""
export_basic_signals_to_gia.py

对外入口：
- 统一通过 `python -X utf8 -m ugc_file_tools tool export_basic_signals_to_gia ...` 调用；
- 对外门面位于 `ugc_file_tools.gia_export.signals`（薄转发，不改产物形态）；
- 真实实现位于 `ugc_file_tools.signal_writeback.gia_export`。
"""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.gia_export.signals import ExportBasicSignalsGiaPlan, export_basic_signals_to_gia


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="导出基础信号（共享根 + 项目存档根的 *.py）为 .gia（信号相关 node_defs GraphUnit）。")
    parser.add_argument("--project-archive", default="", help="项目存档目录（可选；不填则仅导出共享根基础信号）")
    parser.add_argument("--output-gia", default="基础信号.gia", help="输出文件名（写入 ugc_file_tools/out/）")
    parser.add_argument("--game-version", default="6.3.0", help="Root.gameVersion（默认 6.3.0）")
    parser.add_argument(
        "--report",
        dest="report_json",
        default="",
        help="可选：将导出 report 写入 JSON 文件（便于 UI 调用）。",
    )
    parser.add_argument(
        "--copy-to",
        default="",
        help="可选：额外复制到该绝对目录（默认已导出到 Beyond_Local_Export）。",
    )
    parser.add_argument(
        "--select-signal-id",
        action="append",
        default=[],
        help="可选：只导出指定 SIGNAL_ID（可重复传入多次）。不传则导出全部。",
    )
    parser.add_argument(
        "--template-gia",
        default="",
        help="可选：作为信号 node_def 结构模板的 .gia（默认使用 ugc_file_tools/builtin_resources/gia_templates/signals/signal_node_defs_full.gia）",
    )
    args = parser.parse_args(argv)

    project_archive_path = Path(str(args.project_archive)).resolve() if str(args.project_archive).strip() else None
    template_gia_path = Path(str(args.template_gia)).resolve() if str(args.template_gia).strip() else None
    # 强制导出到 Beyond_Local_Export；--copy-to 仅用于额外复制到其他目录
    copy_to_path = Path(str(args.copy_to)).resolve() if str(args.copy_to).strip() else get_beyond_local_export_dir()

    report = export_basic_signals_to_gia(
        plan=ExportBasicSignalsGiaPlan(
            project_archive_path=project_archive_path,
            output_gia_file_name_in_out=str(args.output_gia),
            game_version=str(args.game_version),
            selected_signal_ids=[str(s).strip() for s in list(getattr(args, "select_signal_id", []) or []) if str(s).strip() != ""]
            or None,
            output_user_dir=copy_to_path,
            template_gia=template_gia_path,
        )
    )
    if str(getattr(args, "report_json", "") or "").strip():
        report_path = Path(str(getattr(args, "report_json"))).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

