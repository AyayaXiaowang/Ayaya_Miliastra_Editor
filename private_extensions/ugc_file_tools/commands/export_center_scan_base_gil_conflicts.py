from __future__ import annotations

"""
export_center_scan_base_gil_conflicts.py

用途：
- 为“导出中心（.gil 写回）”提供 base `.gil` 的只读冲突扫描结果，供 UI 弹窗做 overwrite/add/skip 选择。

设计要点：
- 该工具将 `.gil` 解码放在 **独立子进程** 中执行：即便底层解码在个别环境/样本上触发硬崩，
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
        description="导出中心辅助：扫描 base .gil 冲突信息（UI布局/节点图/模板/实体）并输出 report.json（用于 overwrite/add/skip 交互）。"
    )
    parser.add_argument("base_gil", help="输入 base .gil 路径。")
    parser.add_argument("--report", required=True, help="输出 report.json 路径（UI 调用会传临时文件路径）。")
    parser.add_argument(
        "--decode-max-depth",
        type=int,
        default=16,
        help="dump-json 解码深度（用于 UI布局/模板/实体扫描；默认 16）。",
    )
    parser.add_argument("--scan-ui-layouts", action="store_true", help="扫描 UI 布局 root：layout_name -> guid。")
    parser.add_argument("--scan-node-graphs", action="store_true", help="扫描节点图：按 scope+graph_name 映射 graph_id_int。")
    parser.add_argument("--scan-templates", action="store_true", help="扫描元件模板：template_name -> template_id_int。")
    parser.add_argument("--scan-instances", action="store_true", help="扫描实体实例：instance_name -> instance_id_int。")

    args = parser.parse_args(list(argv) if argv is not None else None)

    base = Path(str(args.base_gil)).resolve()
    if not base.is_file():
        raise FileNotFoundError(str(base))

    report_path = Path(str(args.report)).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    want_ui_layouts = bool(args.scan_ui_layouts)
    want_node_graphs = bool(args.scan_node_graphs)
    want_templates = bool(args.scan_templates)
    want_instances = bool(args.scan_instances)

    # 若未显式指定任何 --scan-*，默认全扫（便于手动运行）。
    if not any([want_ui_layouts, want_node_graphs, want_templates, want_instances]):
        want_ui_layouts = True
        want_node_graphs = True
        want_templates = True
        want_instances = True

    steps = [
        ("ui_layouts", want_ui_layouts, "扫描 UI 布局…"),
        ("node_graphs", want_node_graphs, "扫描节点图…"),
        ("templates", want_templates, "扫描元件模板…"),
        ("instances", want_instances, "扫描实体实例…"),
    ]
    enabled_steps = [s for s in steps if bool(s[1])]
    total = max(1, len(enabled_steps))

    report_obj: Dict[str, Any] = {
        "base_gil": str(base),
        "base_gil_size_bytes": int(base.stat().st_size),
        "decode_max_depth": int(args.decode_max_depth),
        "scanned": {
            "ui_layouts": bool(want_ui_layouts),
            "node_graphs": bool(want_node_graphs),
            "templates": bool(want_templates),
            "instances": bool(want_instances),
        },
        "ui_layout_guid_by_name": {},
        "node_graph_id_by_scope_and_name": {"server": {}, "client": {}},
        "template_id_by_name": {},
        "instance_id_by_name": {},
        "summary": {},
    }

    current = 0

    if want_ui_layouts:
        current += 1
        _emit_progress(current, total, "扫描 UI 布局（layout_name -> guid）")
        from ugc_file_tools.gil.ui_layout_scanner import scan_ui_layout_root_guids_by_name

        ui_layout_guid_by_name = scan_ui_layout_root_guids_by_name(
            gil_file_path=Path(base),
            decode_max_depth=int(args.decode_max_depth),
        )
        report_obj["ui_layout_guid_by_name"] = dict(ui_layout_guid_by_name)
        report_obj["summary"]["ui_layout_total"] = int(len(ui_layout_guid_by_name))

    if want_node_graphs:
        current += 1
        _emit_progress(current, total, "扫描节点图（(scope, graph_name) -> graph_id_int）")
        from ugc_file_tools.gil.graph_variable_scanner import scan_gil_file_graph_variables
        from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.constants import (
            CLIENT_SCOPE_MASK,
            SCOPE_MASK,
            SERVER_SCOPE_MASK,
        )

        base_scan = scan_gil_file_graph_variables(Path(base))
        by_scope: dict[str, dict[str, int]] = {"server": {}, "client": {}}
        for g in base_scan.graphs:
            name = str(g.graph_name or "").strip()
            if name == "":
                continue
            gid = int(g.graph_id_int)
            mask = int(gid) & int(SCOPE_MASK)
            if int(mask) == int(SERVER_SCOPE_MASK):
                scope = "server"
            elif int(mask) == int(CLIENT_SCOPE_MASK):
                scope = "client"
            else:
                continue
            by_scope.setdefault(scope, {})
            if name not in by_scope[scope]:
                by_scope[scope][name] = int(gid)

        report_obj["node_graph_id_by_scope_and_name"] = {
            "server": dict(by_scope.get("server", {})),
            "client": dict(by_scope.get("client", {})),
        }
        report_obj["summary"]["node_graph_total"] = int(len(base_scan.graphs))
        report_obj["summary"]["node_graph_server_unique_name_total"] = int(len(by_scope.get("server", {})))
        report_obj["summary"]["node_graph_client_unique_name_total"] = int(len(by_scope.get("client", {})))

    if want_templates:
        current += 1
        _emit_progress(current, total, "扫描元件模板（template_name -> template_id_int）")
        from ugc_file_tools.gil.template_scanner import scan_template_ids_by_name

        template_id_by_name = scan_template_ids_by_name(
            gil_file_path=Path(base),
            decode_max_depth=int(args.decode_max_depth),
        )
        report_obj["template_id_by_name"] = dict(template_id_by_name)
        report_obj["summary"]["template_total"] = int(len(template_id_by_name))

    if want_instances:
        current += 1
        _emit_progress(current, total, "扫描实体实例（instance_name -> instance_id_int）")
        from ugc_file_tools.gil.instance_scanner import scan_instance_ids_by_name

        instance_id_by_name = scan_instance_ids_by_name(
            gil_file_path=Path(base),
            decode_max_depth=int(args.decode_max_depth),
        )
        report_obj["instance_id_by_name"] = dict(instance_id_by_name)
        report_obj["summary"]["instance_total"] = int(len(instance_id_by_name))

    report_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("export_center base .gil 冲突扫描报告已生成：")
    print(f"- base_gil: {str(base)}")
    print(f"- report: {str(report_path)}")
    print(f"- scanned: {report_obj['scanned']}")
    print("================================================================================")


if __name__ == "__main__":
    main()

