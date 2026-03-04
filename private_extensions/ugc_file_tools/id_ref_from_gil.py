from __future__ import annotations

"""
id_ref_from_gil.py

目标：
- 从用户选择的参考 `.gil` 中抽取：
  - 元件名 -> 元件ID（模板条目 ID / prefab_id，用于节点图 `元件ID` 端口；通常为 10 位整数）
  - 实体名 -> 实体GUID/实例ID
用于节点图导出/写回阶段的 `component_key:` / `entity_key:` 占位符回填。

约束：
- 同名时取第一个（稳定：按 dump-json 扫描顺序）。
- 不做 try/except：结构不符合预期直接抛错，避免 silent 产出坏映射。
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.gil.name_unwrap import normalize_dump_json_name_text
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root


def _first_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


# -------------------- component_name -> component_id --------------------


def _try_extract_component_name_from_record(record: Dict[str, Any]) -> Optional[str]:
    """
    从 dump-json record 中抽取“元件名称”。

    经验结构（从样本对照抽取）：
    - record['1'] 为模板条目 ID（prefab_id / template_entry_id；通常为 10 位整数）
    - record['2'] 为模板类型码（template_type_code；常见为 1000xxxx/2000xxxx，同类型模板会重复）
    - record['6'] 为 repeated message 列表
      - 某个条目包含 record['11']['1'] 的字符串（名称）
    """
    v6 = record.get("6")
    items = v6 if isinstance(v6, list) else ([v6] if isinstance(v6, dict) else [])
    for it in items:
        if not isinstance(it, dict):
            continue
        # 兼容两种常见形态：
        # - {"1": 1, "11": {"1": "名字"}}
        # - {"1": 1, "11": "名字"}
        v11 = it.get("11")
        if isinstance(v11, str):
            name = normalize_dump_json_name_text(v11)
            if name != "":
                return str(name)

        inner11 = _first_dict(v11)
        if not isinstance(inner11, dict):
            continue
        name_val = inner11.get("1")
        if isinstance(name_val, str):
            name = normalize_dump_json_name_text(name_val)
            if name != "":
                return str(name)
    return None


def _collect_component_name_to_id_from_payload_root(payload_root: Dict[str, Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        # 候选：包含 (template_entry_id, template_type_code, name)
        # 说明：节点图 `元件ID` 端口需要的是“模板条目 ID”（field_1），而不是“模板类型码”（field_2）。
        template_type_code = value.get("2")
        template_entry_id = value.get("1")
        if isinstance(template_type_code, int) and isinstance(template_entry_id, int):
            if int(template_entry_id) > 1_000_000_000 and 1 <= int(template_type_code) <= 999_999_999:
                name = _try_extract_component_name_from_record(value)
                if name is not None and name not in mapping:
                    mapping[str(name)] = int(template_entry_id)

        for _k, v in value.items():
            visit(v)

    visit(payload_root)
    return mapping


# -------------------- entity_name -> entity_guid --------------------


def _ensure_list_allow_scalar(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _extract_instance_id_int(entry: Dict[str, Any]) -> int | None:
    value = entry.get("1")
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    if isinstance(value, int):
        return int(value)
    return None


def _extract_instance_name(entry: Dict[str, Any]) -> str:
    meta_list = _ensure_list_allow_scalar(entry.get("5"))
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        container = item.get("11")
        name_value: str | None = None
        if isinstance(container, dict):
            v = container.get("1")
            if isinstance(v, str):
                name_value = v
        elif isinstance(container, str):
            name_value = container
        if isinstance(name_value, str):
            name = normalize_dump_json_name_text(name_value)
            if name != "":
                return str(name)
    return ""


def _collect_entity_name_to_guid_from_payload_root(payload_root: Dict[str, Any]) -> Dict[str, int]:
    """
    从 payload_root['5']['1']（实体摆放 entries）抽取 name -> instance_id_int。
    """
    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        return {}
    entries = _ensure_list_allow_scalar(section5.get("1"))

    mapping: Dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        instance_id_int = _extract_instance_id_int(entry)
        if not isinstance(instance_id_int, int) or int(instance_id_int) <= 0:
            continue
        name = _extract_instance_name(entry)
        if name == "":
            continue
        if name not in mapping:
            mapping[str(name)] = int(instance_id_int)
    return mapping


def build_id_ref_mappings_from_payload_root(*, payload_root: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    从已解码的 payload_root（dump-json 数值键 dict）构建：
    - component_name_to_id（元件名 -> 模板条目 ID / prefab_id）
    - entity_name_to_guid（实体名 -> 实体 GUID/实例ID）

    用途：
    - 当上层已完成 `.gil` 解码（例如导出中心回填识别）时，复用同一份 payload_root，避免重复解码 `.gil`。
    """
    if not isinstance(payload_root, dict):
        raise TypeError("payload_root must be dict")

    component_name_to_id = _collect_component_name_to_id_from_payload_root(payload_root)
    entity_name_to_guid = _collect_entity_name_to_guid_from_payload_root(payload_root)
    return dict(component_name_to_id), dict(entity_name_to_guid)


def build_id_ref_mappings_from_gil_file(*, gil_file_path: Path) -> Tuple[Dict[str, int], Dict[str, int]]:
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    raw_dump_object = dump_gil_to_raw_json_object(p)
    payload_root = get_payload_root(raw_dump_object)

    return build_id_ref_mappings_from_payload_root(payload_root=payload_root)


__all__ = [
    "build_id_ref_mappings_from_gil_file",
    "build_id_ref_mappings_from_payload_root",
]

