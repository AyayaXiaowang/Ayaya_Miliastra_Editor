from __future__ import annotations

"""
export_center_scan_gil_id_ref_candidates.py

用途：
- 为“导出中心 → 回填识别表（缺失行双击手动选择 ID）”提供独立子进程入口：
  扫描指定 `.gil` 的候选全集：
  - component_name -> component_id（模板名 -> 模板条目 ID）
  - entity_name -> entity_guid（实例名 -> instance_id_int）

设计要点：
- 将 `.gil` 解码放在 **独立子进程** 中执行：即便底层解码在个别环境/样本上触发硬崩，
  也不会带着 PyQt 主进程一起闪退（UI 侧可根据 exit_code 做降级提示）。
- 不使用 try/except；失败直接抛错，便于定位样本差异或解码不兼容点。

输出：
- `--report <path>`：写入 JSON（供 UI 读取）。
- 进度：在 stderr 输出可解析行：`[i/total] label`（供 UI `_cli_subprocess.run_cli_with_progress` 解析）。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding


def _emit_progress(current: int, total: int, label: str) -> None:
    sys.stderr.write(f"[{int(current)}/{int(total)}] {str(label or '').strip()}\n")
    sys.stderr.flush()


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="导出中心辅助：扫描 .gil 的 entity/component ID 候选全集并输出 report.json（用于缺失项手动选择）。"
    )
    parser.add_argument("gil", help="输入 .gil 路径。")
    parser.add_argument("--report", required=True, help="输出 report.json 路径（UI 调用会传临时文件路径）。")
    parser.add_argument(
        "--decode-max-depth",
        type=int,
        default=16,
        help="dump-json 解码深度（用于模板/实例扫描；默认 16）。",
    )
    parser.add_argument("--scan-templates", action="store_true", help="扫描元件模板：component_name -> component_id。")
    parser.add_argument("--scan-instances", action="store_true", help="扫描实体实例：entity_name -> entity_guid。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    gil = Path(str(args.gil)).resolve()
    if not gil.is_file():
        raise FileNotFoundError(str(gil))
    if gil.suffix.lower() != ".gil":
        raise ValueError(f"输入必须为 .gil 文件：{str(gil)}")

    report_path = Path(str(args.report)).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    want_templates = bool(args.scan_templates)
    want_instances = bool(args.scan_instances)
    if not any([want_templates, want_instances]):
        want_templates = True
        want_instances = True

    steps = [
        ("templates", want_templates, "扫描元件模板（component_name -> component_id）"),
        ("instances", want_instances, "扫描实体实例（entity_name -> entity_guid）"),
    ]
    enabled_steps = [s for s in steps if bool(s[1])]
    total = max(1, len(enabled_steps))
    current = 0

    report_obj: Dict[str, Any] = {
        "gil": str(gil),
        "gil_size_bytes": int(gil.stat().st_size),
        "decode_max_depth": int(args.decode_max_depth),
        "scanned": {"templates": bool(want_templates), "instances": bool(want_instances)},
        "component_name_to_id": {},
        "entity_name_to_guid": {},
        "summary": {},
    }

    if want_templates:
        current += 1
        _emit_progress(current, total, "扫描元件模板…")
        from ugc_file_tools.gil.template_scanner import scan_template_ids_by_name

        component_name_to_id = scan_template_ids_by_name(
            gil_file_path=Path(gil),
            decode_max_depth=int(args.decode_max_depth),
        )
        report_obj["component_name_to_id"] = dict(component_name_to_id)
        report_obj["summary"]["components_total"] = int(len(component_name_to_id))

    if want_instances:
        current += 1
        _emit_progress(current, total, "扫描实体实例…")
        from ugc_file_tools.gil.instance_scanner import scan_instance_ids_by_name

        entity_name_to_guid = scan_instance_ids_by_name(
            gil_file_path=Path(gil),
            decode_max_depth=int(args.decode_max_depth),
        )
        report_obj["entity_name_to_guid"] = dict(entity_name_to_guid)
        report_obj["summary"]["entities_total"] = int(len(entity_name_to_guid))

    report_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("export_center IDRef 候选扫描报告已生成：")
    print(f"- gil: {str(gil)}")
    print(f"- report: {str(report_path)}")
    print(f"- scanned: {report_obj['scanned']}")
    print("================================================================================")


if __name__ == "__main__":
    main()

