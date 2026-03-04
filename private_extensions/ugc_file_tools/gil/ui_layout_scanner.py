from __future__ import annotations

from pathlib import Path
from typing import Dict


def scan_ui_layout_root_guids_by_name(*, gil_file_path: Path, decode_max_depth: int = 16) -> dict[str, int]:
    """
    扫描 `.gil` 内已有的“布局 root”记录（UI records 的 root record，满足：无 parent 字段 504），并返回：
      layout_name -> layout_root_guid

    用途：
    - 导出中心（GIL 写回）在 UI Workbench bundle 写回前做“同名布局冲突检查”
    - 写回端按策略 overwrite/add/skip 做预检（可选）

    约束：
    - 本函数仅做轻量扫描，不依赖 PyQt6。
    - 当 base `.gil` 缺失 UI 段（root4/9=None）时，视为“无布局”（返回 {}），对齐写回 bootstrap 场景。

    稳定性说明：
    - 默认 `decode_max_depth=16`（而非更大的深度），用于降低在部分“大/复杂样本”上解析 UI records 时
      触发卡死/崩溃（Windows access violation）的概率；该扫描只需要解码到 UI records 所需的层级即可。
    """
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object
    from ugc_file_tools.ui.readable_dump import (
        extract_primary_guid as _extract_primary_guid,
        extract_primary_name as _extract_primary_name,
        extract_ui_record_list as _extract_ui_record_list,
    )

    dump_obj = load_gil_payload_as_dump_json_object(
        p,
        max_depth=int(decode_max_depth),
        prefer_raw_hex_for_utf8=False,
    )
    payload_root = dump_obj.get("4")
    if not isinstance(payload_root, dict):
        raise TypeError("decoded payload_root is not dict")

    # 兼容：空/极简基底 `.gil` 可能缺失 UI 段（root4/9=None）
    if payload_root.get("9") is None:
        return {}

    ui_record_list = _extract_ui_record_list(dump_obj)

    out: Dict[str, int] = {}
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        # 布局 root：无 parent（504）
        if "504" in record:
            continue
        name_text = _extract_primary_name(record)
        guid_value = _extract_primary_guid(record)
        if not isinstance(name_text, str):
            continue
        name = str(name_text).strip()
        if name == "":
            continue
        if not isinstance(guid_value, int) or int(guid_value) <= 0:
            continue
        if name not in out:
            out[name] = int(guid_value)
    return dict(out)


__all__ = ["scan_ui_layout_root_guids_by_name"]

