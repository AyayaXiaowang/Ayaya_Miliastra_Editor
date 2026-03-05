from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

from .gil_dump import _dump_gil_to_raw_json_object, _get_payload_root, _iter_graph_entries_for_group, _iter_graph_groups
from .record_codec import _decode_type_id_from_node, _extract_data_record_slot_index, _extract_nested_int, _node_has_multibranch_value_record


@dataclass(frozen=True)
class _NodeTemplate:
    node: Dict[str, Any]
    template_node_id_set: set[int]


@dataclass(frozen=True)
class _TemplateLibrary:
    node_template_by_type_id: Dict[int, _NodeTemplate]
    data_link_record_template_by_dst_type_id_and_slot_index: Dict[int, Dict[int, str]]
    outparam_record_template_by_type_id_and_index_and_var_type: Dict[int, Dict[int, Dict[int, str]]]


def _build_template_library_from_nodes(*, template_nodes: List[Dict[str, Any]], template_node_id_set: set[int]) -> _TemplateLibrary:
    node_template_by_type_id: Dict[int, _NodeTemplate] = {}
    data_link_record_template_by_dst_type_id_and_slot_index: Dict[int, Dict[int, str]] = {}
    outparam_record_template_by_type_id_and_index_and_var_type: Dict[int, Dict[int, Dict[int, str]]] = {}

    for node in template_nodes:
        type_id_int = _decode_type_id_from_node(node)
        if int(type_id_int) not in node_template_by_type_id:
            node_template_by_type_id[int(type_id_int)] = _NodeTemplate(
                node=node,
                template_node_id_set=set(template_node_id_set),
            )

        records = node.get("4")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, str) or not record.startswith("<binary_data>"):
                continue
            record_bytes = parse_binary_data_hex_text(record)
            decoded = decode_bytes_to_python(record_bytes)
            if not isinstance(decoded, dict):
                continue

            # link record?
            other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
            # 注意：不要求 other_node_id 必须在 template_node_id_set 内。
            # 导出样本可能存在“悬空连接”（record 仍在，但被指向的 source 节点被编辑器剔除）。
            is_link = isinstance(other_node_id, int) and int(other_node_id) > 0
            if is_link and ("field_4" not in decoded):
                # flow link record：写回时按 schema 构造，不再依赖模板 record
                continue
            if is_link and ("field_4" in decoded):
                # 仅收集 InParam(kind=3) 的 data-link record 作为模板
                kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
                if int(kind or -1) != 3:
                    continue
                slot_index = _extract_data_record_slot_index(decoded)
                data_link_record_template_by_dst_type_id_and_slot_index.setdefault(int(type_id_int), {}).setdefault(
                    int(slot_index), record
                )
                continue

            # non-link record：收集 OutParam pin 模板（kind=4 且非连线）
            kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
            if int(kind or -1) != 4:
                continue
            out_index = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
            out_index_int = 0 if out_index is None else int(out_index)
            var_type_int = _extract_nested_int(decoded, ["field_4"])
            if not isinstance(var_type_int, int):
                continue
            outparam_record_template_by_type_id_and_index_and_var_type.setdefault(int(type_id_int), {}).setdefault(
                out_index_int, {}
            ).setdefault(int(var_type_int), record)

    return _TemplateLibrary(
        node_template_by_type_id=node_template_by_type_id,
        data_link_record_template_by_dst_type_id_and_slot_index=data_link_record_template_by_dst_type_id_and_slot_index,
        outparam_record_template_by_type_id_and_index_and_var_type=outparam_record_template_by_type_id_and_index_and_var_type,
    )


def _merge_template_library_from_extra_gil(
    *,
    lib: _TemplateLibrary,
    extra_gil: Path,
    effective_base_gil_path: Path,
) -> None:
    extra_resolved = Path(extra_gil).resolve()
    base_resolved = Path(effective_base_gil_path).resolve()
    if extra_resolved == base_resolved:
        return

    extra_raw = _dump_gil_to_raw_json_object(extra_gil)
    extra_payload = _get_payload_root(extra_raw)
    extra_section = extra_payload.get("10")
    if not isinstance(extra_section, dict):
        return

    for group in _iter_graph_groups(extra_section):
        for entry in _iter_graph_entries_for_group(group):
            nodes_value = entry.get("3")
            if not isinstance(nodes_value, list):
                continue
            nodes = [n for n in nodes_value if isinstance(n, dict)]
            if not nodes:
                continue

            node_id_set: set[int] = set()
            for n in nodes:
                node_id_value = n.get("1")
                if isinstance(node_id_value, list) and node_id_value and isinstance(node_id_value[0], int):
                    node_id_set.add(int(node_id_value[0]))

            for n in nodes:
                tid = _decode_type_id_from_node(n)
                existing = lib.node_template_by_type_id.get(int(tid))
                if existing is None:
                    lib.node_template_by_type_id[int(tid)] = _NodeTemplate(node=n, template_node_id_set=set(node_id_set))
                else:
                    # 多分支(type_id=3)优先选“带分支值列表 record”的样本
                    if int(tid) == 3 and (not _node_has_multibranch_value_record(existing.node)) and _node_has_multibranch_value_record(n):
                        lib.node_template_by_type_id[int(tid)] = _NodeTemplate(node=n, template_node_id_set=set(node_id_set))

                records = n.get("4")
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, str) or not record.startswith("<binary_data>"):
                        continue
                    record_bytes = parse_binary_data_hex_text(record)
                    decoded = decode_bytes_to_python(record_bytes)
                    if not isinstance(decoded, dict):
                        continue
                    other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
                    is_link = isinstance(other_node_id, int) and int(other_node_id) > 0

                    if is_link and ("field_4" not in decoded):
                        # flow link record：写回时按 schema 构造，不再依赖模板 record
                        continue

                    if is_link and ("field_4" in decoded):
                        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
                        if int(kind or -1) != 3:
                            continue
                        slot_index = _extract_data_record_slot_index(decoded)
                        lib.data_link_record_template_by_dst_type_id_and_slot_index.setdefault(int(tid), {}).setdefault(
                            int(slot_index), record
                        )
                        continue

                    # non-link record：收集 OutParam pin 模板
                    kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
                    if int(kind or -1) != 4:
                        continue
                    out_index = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
                    out_index_int = 0 if out_index is None else int(out_index)
                    var_type_int = _extract_nested_int(decoded, ["field_4"])
                    if not isinstance(var_type_int, int):
                        continue
                    lib.outparam_record_template_by_type_id_and_index_and_var_type.setdefault(int(tid), {}).setdefault(
                        out_index_int, {}
                    ).setdefault(int(var_type_int), record)


def build_template_library(
    *,
    template_nodes: List[Dict[str, Any]],
    template_node_id_set: set[int],
    template_library_dir: Optional[Path],
    effective_base_gil_path: Path,
) -> _TemplateLibrary:
    lib = _build_template_library_from_nodes(template_nodes=template_nodes, template_node_id_set=template_node_id_set)

    if template_library_dir is None:
        return lib

    lib_dir = Path(template_library_dir).resolve()
    if not lib_dir.exists():
        raise ValueError(f"template_library_dir 不存在：{str(lib_dir)}")

    for extra_gil in sorted(lib_dir.rglob("*.gil")):
        _merge_template_library_from_extra_gil(lib=lib, extra_gil=extra_gil, effective_base_gil_path=effective_base_gil_path)

    return lib


