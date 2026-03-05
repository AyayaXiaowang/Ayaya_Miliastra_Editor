from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui.export_records import UIExportRecord, load_ui_export_records


def graph_code_files_need_ui_export_record(*, graph_code_files: List[Path]) -> bool:
    """
    轻量判断：若节点图源码中出现 `ui_key:` 占位符，则导出 `.gia` 时需要 UIKey→GUID 映射。

    说明：
    - 不解析 GraphModel；只做文本包含判断（UI 对话框层用于决定是否展示“回填记录选择”）。
    - 该判断允许保守：只要命中就认为需要；未命中也不代表一定不需要（极少数 `ui:` 前缀或生成期注入场景）。
    """
    for p in list(graph_code_files or []):
        text = Path(p).read_text(encoding="utf-8", errors="strict")
        if "ui_key:" in text:
            return True
    return False


def load_ui_export_record_options(*, workspace_root: Path, package_id: str) -> List[Dict[str, Any]]:
    """
    为 UI 下拉框准备选项列表（最新在前）。

    返回结构：
      [{"record_id": "...", "label": "...", "record": UIExportRecord}, ...]
    """
    records = load_ui_export_records(workspace_root=Path(workspace_root).resolve(), package_id=str(package_id))
    out: List[Dict[str, Any]] = []
    for r in records:
        out.append(
            {
                "record_id": str(r.record_id),
                "label": f"{r.created_at}  {r.title}",
                "record": r,
            }
        )
    return out


def format_ui_export_record_detail_text(record: UIExportRecord) -> str:
    payload = dict(record.payload)
    output_name = str(payload.get("output_gil_name") or payload.get("output_gil_file") or "").strip()
    base_name = str(payload.get("base_gil_name") or "").strip()
    mapping_total = payload.get("ui_guid_mapping_total")
    lines = [
        f"时间：{record.created_at}",
        f"名称：{record.title}",
        f"输出：{output_name}",
    ]
    if base_name != "":
        lines.append(f"基底：{base_name}")
    if isinstance(mapping_total, int):
        lines.append(f"映射条目：{int(mapping_total)}")
    return "\n".join(lines)


__all__ = [
    "graph_code_files_need_ui_export_record",
    "load_ui_export_record_options",
    "format_ui_export_record_detail_text",
]

