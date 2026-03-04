from __future__ import annotations

"""
export_center_identify_gil_backfill_comparison.py

用途：
- 为“导出中心 → 回填识别（步骤2：识别按钮）”提供独立子进程入口。

背景：
- 识别过程需要解码 `.gil`（dump-json / protobuf-like），在个别环境/样本上可能触发 Windows access violation。
- 将解码放在子进程中执行可以避免 UI 主进程随之闪退；UI 侧根据 exit_code 与 report.json 做提示。

约束：
- 不使用 try/except；失败直接抛错，便于定位样本差异或解码不兼容点。
- 进度在 stderr 输出可解析行：`[i/total] label`（供 UI `_cli_subprocess.run_cli_with_progress` 解析）。

输入：
- `--manifest <path>`：JSON（由 UI 写入；包含 identify_gil_backfill_comparison 的全部入参）。

输出：
- `--report <path>`：写入 JSON（供 UI 表格直接渲染）。
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


def _load_manifest(path: Path) -> Dict[str, Any]:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError("manifest must be dict")
    return dict(obj)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="导出中心辅助：在子进程中执行回填识别（identify_gil_backfill_comparison），输出 report.json。")
    parser.add_argument("--manifest", required=True, help="输入 manifest.json（由 UI 生成）。")
    parser.add_argument("--report", required=True, help="输出 report.json 路径（UI 调用会传临时文件路径）。")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = _load_manifest(Path(str(args.manifest)))

    report_path = Path(str(args.report)).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def _as_path_or_none(value: object) -> Path | None:
        if value is None:
            return None
        text = str(value or "").strip()
        if text == "":
            return None
        return Path(text).resolve()

    base_gil_file_path = Path(str(manifest.get("base_gil_file_path") or "")).resolve()
    if not base_gil_file_path.is_file():
        raise FileNotFoundError(str(base_gil_file_path))

    id_ref_gil_file_path = _as_path_or_none(manifest.get("id_ref_gil_file_path"))
    if id_ref_gil_file_path is not None and not id_ref_gil_file_path.is_file():
        raise FileNotFoundError(str(id_ref_gil_file_path))

    ui_source_dir = _as_path_or_none(manifest.get("ui_source_dir"))
    if ui_source_dir is not None and not ui_source_dir.is_dir():
        raise FileNotFoundError(str(ui_source_dir))

    workspace_root = _as_path_or_none(manifest.get("workspace_root"))
    if workspace_root is not None and not workspace_root.is_dir():
        raise FileNotFoundError(str(workspace_root))

    ui_export_record_id_raw = manifest.get("ui_export_record_id")
    ui_export_record_id = (str(ui_export_record_id_raw).strip() if ui_export_record_id_raw is not None else None)
    if ui_export_record_id == "":
        ui_export_record_id = None

    required_entity_names = manifest.get("required_entity_names") or []
    if not isinstance(required_entity_names, list):
        raise TypeError("required_entity_names must be list[str]")
    required_component_names = manifest.get("required_component_names") or []
    if not isinstance(required_component_names, list):
        raise TypeError("required_component_names must be list[str]")
    required_ui_keys = manifest.get("required_ui_keys") or []
    if not isinstance(required_ui_keys, list):
        raise TypeError("required_ui_keys must be list[str]")

    ui_key_layout_hints_by_key = manifest.get("ui_key_layout_hints_by_key") or {}
    if not isinstance(ui_key_layout_hints_by_key, dict):
        raise TypeError("ui_key_layout_hints_by_key must be dict[str, list[str]]")

    required_level_custom_variables = manifest.get("required_level_custom_variables") or []
    if not isinstance(required_level_custom_variables, list):
        raise TypeError("required_level_custom_variables must be list[dict[str,str]]")

    use_base_as_id_ref_fallback = bool(manifest.get("use_base_as_id_ref_fallback") or False)
    scan_ui_placeholder_variables = bool(manifest.get("scan_ui_placeholder_variables") or False)
    ui_selected_html_stems = manifest.get("ui_selected_html_stems") or []
    if not isinstance(ui_selected_html_stems, list):
        raise TypeError("ui_selected_html_stems must be list[str]")
    package_id = str(manifest.get("package_id") or "").strip()
    if package_id == "":
        raise ValueError("manifest.package_id 不能为空")

    from ugc_file_tools.ui_integration.export_center.backfill_inspector import identify_gil_backfill_comparison

    report = identify_gil_backfill_comparison(
        base_gil_file_path=Path(base_gil_file_path),
        id_ref_gil_file_path=(Path(id_ref_gil_file_path) if id_ref_gil_file_path is not None else None),
        use_base_as_id_ref_fallback=bool(use_base_as_id_ref_fallback),
        workspace_root=(Path(workspace_root) if workspace_root is not None else None),
        package_id=str(package_id),
        ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
        required_entity_names=[str(x).strip() for x in required_entity_names if str(x).strip() != ""],
        required_component_names=[str(x).strip() for x in required_component_names if str(x).strip() != ""],
        required_ui_keys=[str(x).strip() for x in required_ui_keys if str(x).strip() != ""],
        ui_key_layout_hints_by_key={str(k): [str(x).strip() for x in v if str(x).strip() != ""] for k, v in ui_key_layout_hints_by_key.items()},
        required_level_custom_variables=[dict(x) for x in required_level_custom_variables if isinstance(x, dict)],
        scan_ui_placeholder_variables=bool(scan_ui_placeholder_variables),
        ui_source_dir=(Path(ui_source_dir) if ui_source_dir is not None else None),
        ui_selected_html_stems=[str(x).strip() for x in ui_selected_html_stems if str(x).strip() != ""],
        progress_cb=lambda current, total, label: _emit_progress(int(current), int(total), str(label)),
    )

    if not isinstance(report, dict):
        raise TypeError("identify report must be dict")

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("export_center 回填识别报告已生成：")
    print(f"- base_gil: {str(base_gil_file_path)}")
    print(f"- report: {str(report_path)}")
    print("================================================================================")


if __name__ == "__main__":
    main()

