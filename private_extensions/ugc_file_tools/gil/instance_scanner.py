from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.gil.name_unwrap import normalize_dump_json_name_text


def _ensure_list_allow_scalar(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _extract_first_int_from_repeated_field(node: Dict[str, Any], key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _try_extract_instance_name_from_entry(entry: Dict[str, Any]) -> str:
    """
    从实例 entry（root4/5/1）抽取“实体显示名”。

    经验结构（对齐 `project_archive_importer/instances_importer.py` 的写回口径）：
    - entry['5'] 为 meta repeated
      - item['1']==1 的 item['11']['1'] 或 item['11'] 为名称字符串
    """
    meta_list = _ensure_list_allow_scalar(entry.get("5"))
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        v11 = item.get("11")
        if isinstance(v11, str):
            return normalize_dump_json_name_text(v11)
        if isinstance(v11, dict):
            name_val = v11.get("1")
            if isinstance(name_val, str):
                return normalize_dump_json_name_text(name_val)
    return ""


def scan_instance_ids_by_name(*, gil_file_path: Path, decode_max_depth: int = 16) -> dict[str, int]:
    """
    只读扫描 `.gil` 内的“实体实例段(root4/5/1)”并返回：

      instance_name -> instance_id_int（first-wins）

    用途：
    - 导出中心（GIL）导出前的“同名实体冲突检查”
    - 写回链路可选按 name 做策略编排（overwrite/add/skip）

    约束：
    - 本函数仅做轻量扫描，不依赖 PyQt6。
    - 当 base `.gil` 缺失实例段时，视为“无实例”（返回 {}）。

    稳定性说明：
    - 默认 `decode_max_depth=16`：实例名/ID 扫描不需要解到很深；较小深度可降低在部分样本上触发
      解码卡死/崩溃的概率（尤其是 UI/导出中心在主进程内做冲突预扫的场景）。
    """
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object

    dump_obj = load_gil_payload_as_dump_json_object(
        p,
        max_depth=int(decode_max_depth),
        prefer_raw_hex_for_utf8=False,
    )
    payload_root = dump_obj.get("4")
    if not isinstance(payload_root, dict):
        raise TypeError("decoded payload_root is not dict")

    instance_section = payload_root.get("5")
    if not isinstance(instance_section, dict):
        return {}

    entries = _ensure_list_allow_scalar(instance_section.get("1"))

    out: Dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        instance_id_int = _extract_first_int_from_repeated_field(entry, "1")
        if not isinstance(instance_id_int, int) or int(instance_id_int) <= 0:
            continue
        name = _try_extract_instance_name_from_entry(entry)
        if name == "":
            continue
        if name not in out:
            out[str(name)] = int(instance_id_int)
    return dict(out)


__all__ = ["scan_instance_ids_by_name"]

