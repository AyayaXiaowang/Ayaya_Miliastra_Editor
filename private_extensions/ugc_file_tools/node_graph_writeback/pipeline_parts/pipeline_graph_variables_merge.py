from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text

from ..graph_variables import _build_graph_variable_def_item_from_metadata, _extract_struct_defs_from_payload_root


def _normalize_graph_variable_def_table_inplace(maybe_table: Any) -> None:
    """
    对齐真源样本：GraphVariables(default_value) 的 id-like 0 常以 empty bytes 表达，
    而不是显式写入 `{field_101.message.field_1=0}`。
    """
    if maybe_table is None:
        return
    empty = format_binary_data_hex_text(b"")

    items: List[Dict[str, Any]] = []
    if isinstance(maybe_table, list):
        items = [x for x in list(maybe_table) if isinstance(x, dict)]
    elif isinstance(maybe_table, dict):
        items = [maybe_table]
    else:
        return

    for item in items:
        vb = item.get("4")
        if not isinstance(vb, dict):
            continue
        # VarBase(IdBaseValue)
        if int(vb.get("1") or 0) != 1:
            continue
        if int(vb.get("2") or 0) != 1:
            continue
        f101 = vb.get("101")
        if isinstance(f101, dict) and int(f101.get("1") or 0) == 0 and len(f101) == 1:
            vb["101"] = empty


def _build_base_graph_variables_by_name(*, base_existing_graph_variables_table: List[Any]) -> Dict[str, Dict[str, Any]]:
    base_items = [x for x in list(base_existing_graph_variables_table) if isinstance(x, dict)]
    base_by_name: Dict[str, Dict[str, Any]] = {}
    for item in base_items:
        n = str(item.get("2") or "").strip()
        if n != "" and n not in base_by_name:
            base_by_name[n] = item
    return base_by_name


def _merge_graph_variables_with_base_existing_table(
    *,
    graph_variables: List[Dict[str, Any]],
    struct_defs: Any,
    base_existing_graph_variables_table: List[Any],
) -> List[Dict[str, Any]]:
    base_by_name = _build_base_graph_variables_by_name(base_existing_graph_variables_table=base_existing_graph_variables_table)

    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for v in list(graph_variables):
        if not isinstance(v, dict):
            continue
        name = str(v.get("name") or "").strip()
        if name == "" or name in seen:
            continue
        seen.add(name)

        preserve_from_base = False
        if name.startswith("布局索引_"):
            # 约定：布局索引默认值在代码中通常是 0（占位），真源会从 UI records 解析得到实际整数 GUID。
            preserve_from_base = True

        if preserve_from_base and name in base_by_name:
            merged.append(dict(base_by_name[name]))
        else:
            merged.append(_build_graph_variable_def_item_from_metadata(v, struct_defs=struct_defs))

    # 兼容：若 base 中存在但代码级变量表缺失的条目，按原样追加（避免用户存档里有手工图变量但源码未同步）。
    for name, item in base_by_name.items():
        if name in seen:
            continue
        merged.append(dict(item))

    return merged


def build_graph_variables_table_for_entry(
    *,
    graph_variables: List[Dict[str, Any]],
    payload_root: Dict[str, Any],
    base_existing_graph_variables_table: Any,
    preserve_base_existing_table_enabled: bool,
) -> Optional[List[Dict[str, Any]]]:
    """
    构造写回 entry['6'] 的 GraphVariables 表；返回 None 表示不写入（保留 entry 中继承/空值）。

    规则保持与原 pipeline.py 一致：
    - 若启用 preserve 且 base 同 graph_id 已存在变量表：
      - `布局索引_*` 优先保留 base 条目；
      - 其余变量按 metadata 重建；
      - base 有但 metadata 缺失的条目按原样追加。
    - 否则：按 metadata 全量重建。
    """
    if not graph_variables:
        return None
    struct_defs = _extract_struct_defs_from_payload_root(payload_root)

    if (
        bool(preserve_base_existing_table_enabled)
        and isinstance(base_existing_graph_variables_table, list)
        and base_existing_graph_variables_table
    ):
        return _merge_graph_variables_with_base_existing_table(
            graph_variables=list(graph_variables),
            struct_defs=struct_defs,
            base_existing_graph_variables_table=list(base_existing_graph_variables_table),
        )

    return [_build_graph_variable_def_item_from_metadata(v, struct_defs=struct_defs) for v in list(graph_variables)]

