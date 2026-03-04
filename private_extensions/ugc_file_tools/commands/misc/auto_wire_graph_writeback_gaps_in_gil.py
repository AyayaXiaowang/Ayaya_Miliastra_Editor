from __future__ import annotations

"""
auto_wire_graph_writeback_gaps_in_gil.py

目标：
- 读取 `report_graph_writeback_gaps.py` 的输出 JSON（gap 报告）；
- 将报告中“缺失的 record 样本需求”自动写入到一个现有 `.gil` 的指定节点图（GraphEntry）里：
  - data-link record（dst_type_id + slot_index/pin_index）
  - OutParam record（type_id + out_index + VarType）

为什么需要它：
- Graph_Generater 的 NodeDef 确实定义了端口名与端口类型，但 `.gil` 的 record 二进制形态仍存在大量“样本驱动”的细节。
- 你手工连线可以产出权威样本，但一口气要连几百个端口太累。
- 本工具用“最小 schema record”批量铺连线/OutParam pins，让你只需要：
  - 打开一次官方编辑器/游戏内节点图
  - 导出 `.gil`
  就能获得一份更接近“权威形态”的 record 样本库。

约束：
- 不使用 try/except；失败直接抛错（fail-fast）。
- 输出路径强制写入 `ugc_file_tools/out/`。
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.model_ir import normalize_nodes_list, pick_graph_model_payload_and_metadata
from ugc_file_tools.var_type_map import try_map_server_port_type_text_to_var_type_id
from ugc_file_tools.commands.create_type_id_matrix_in_gil import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_graph_entry as _find_graph_entry,
    get_payload_root as _get_payload_root,
    patch_node_type_id_in_binary_text as _patch_node_type_id_in_binary_text,
)
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.node_graph_semantics.pin_rules import infer_index_of_concrete_for_generic_pin
from ugc_file_tools.node_graph_writeback.record_codec import (
    build_node_connection_message as _build_node_connection_message,
    build_node_pin_message as _build_node_pin_message,
    decode_type_id_from_node as _decode_type_id_from_node,
    decoded_field_map_to_dump_json_message as _decoded_field_map_to_dump_json_message,
    ensure_record_list as _ensure_record_list,
    extract_nested_int as _extract_nested_int,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)


def _try_map_port_type_text_to_var_type_int(port_type_text: str) -> Optional[int]:
    return try_map_server_port_type_text_to_var_type_id(port_type_text)


def _resolve_input_port_var_type_int_from_example_graph(
    *,
    example_graph_json_path: Path,
    node_title: str,
    input_port_name: str,
) -> int:
    obj = json.loads(Path(example_graph_json_path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"GraphModel JSON 顶层必须是 dict：{str(example_graph_json_path)!r}")
    _, graph_model = pick_graph_model_payload_and_metadata(obj)
    if not isinstance(graph_model, dict):
        raise TypeError(f"GraphModel payload 不是 dict：{str(example_graph_json_path)!r}")

    nodes = normalize_nodes_list(graph_model)
    title = str(node_title or "").strip()
    port = str(input_port_name or "").strip()
    if title == "" or port == "":
        raise ValueError(f"example_graph_json 缺少 node_title/port：title={node_title!r} port={input_port_name!r}")

    candidates: List[Dict[str, Any]] = []
    for n in nodes:
        if str(n.get("title") or "").strip() != title:
            continue
        inputs_value = n.get("inputs")
        inputs = [str(x) for x in inputs_value] if isinstance(inputs_value, list) else []
        if port not in inputs:
            continue
        candidates.append(n)

    if not candidates:
        raise ValueError(
            f"example_graph_json 未找到节点/输入端口：graph={str(example_graph_json_path)!r} title={title!r} port={port!r}"
        )

    port_type_texts: List[str] = []
    for n in candidates:
        ipt = n.get("input_port_types")
        if not isinstance(ipt, dict):
            ipt = n.get("effective_input_types")
        if not isinstance(ipt, dict):
            continue
        t = ipt.get(port)
        if isinstance(t, str) and t.strip():
            port_type_texts.append(t.strip())

    if not port_type_texts:
        raise ValueError(
            f"example_graph_json 目标节点缺少 input_port_types/input_types：graph={str(example_graph_json_path)!r} title={title!r} port={port!r} candidates={len(candidates)}"
        )

    # 将“具体类型文本”收敛为 VarType（record 里只关心 VarType，而非字典的 key/value alias）
    vt_list: List[int] = []
    for t in port_type_texts:
        vt = _try_map_port_type_text_to_var_type_int(str(t))
        if not isinstance(vt, int):
            raise ValueError(
                f"无法将端口类型映射为 VarType：graph={str(example_graph_json_path)!r} title={title!r} port={port!r} port_type={t!r}"
            )
        vt_list.append(int(vt))

    uniq_vt = sorted(set(int(v) for v in vt_list))
    if len(uniq_vt) == 1:
        return int(uniq_vt[0])

    # 同一端口在样本里出现多个“具体类型”时：优先选择“字典/列表”等更强约束的 VarType。
    # 说明：这类歧义通常来自“泛型端口在不同实例中被绑定为不同类型”。
    # 模板库目前按 (dst_type_id, pin_index) 单模板存储，无法同时覆盖多种 VarType；因此这里做一个稳定、可解释的收敛策略。
    if 27 in uniq_vt and ("字典" in port):
        return 27

    # 回退：按出现频次选择（同频则选择较小 VarType，保证稳定）。
    by_count: Dict[int, int] = {}
    for vt in vt_list:
        by_count[int(vt)] = int(by_count.get(int(vt), 0)) + 1
    best_count = max(by_count.values())
    best = sorted([vt for vt, c in by_count.items() if int(c) == int(best_count)])
    return int(best[0])


def _build_outparam_record_text(*, node_title: str, out_port: str, out_index: int, var_type_int: int) -> str:
    pin_msg = _build_node_pin_message(kind=4, index=int(out_index), var_type_int=int(var_type_int), connects=None)

    # 对齐校准样本：OutParam record 通常包含 field_3(ConcreteBase/VarBase)。
    inner_empty = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
    concrete = _wrap_var_base_as_concrete_base(
        inner=inner_empty,
        index_of_concrete=infer_index_of_concrete_for_generic_pin(
            node_title=str(node_title), port_name=str(out_port), is_input=False
        ),
    )
    pin_msg["3"] = dict(concrete)

    return format_binary_data_hex_text(encode_message(pin_msg))


def _find_existing_record_index(*, records: List[Any], kind: int, index: int) -> Optional[int]:
    for i, r in enumerate(list(records)):
        if not isinstance(r, str) or not r.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(r))
        if not isinstance(decoded, dict):
            continue
        kind0 = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx0 = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        idx0_int = 0 if idx0 is None else int(idx0)
        if int(kind0 or -1) != int(kind):
            continue
        if idx0_int != int(index):
            continue
        return int(i)
    return None


def _find_existing_outparam_record_index_by_var_type(
    *, records: List[Any], out_index: int, var_type_int: int
) -> Optional[int]:
    for i, r in enumerate(list(records)):
        if not isinstance(r, str) or not r.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(r))
        if not isinstance(decoded, dict):
            continue
        kind0 = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx0 = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        idx0_int = 0 if idx0 is None else int(idx0)
        if int(kind0 or -1) != 4:
            continue
        if idx0_int != int(out_index):
            continue
        vt0 = _extract_nested_int(decoded, ["field_4"])
        if not isinstance(vt0, int):
            continue
        if int(vt0) != int(var_type_int):
            continue
        return int(i)
    return None


def apply_gaps_to_graph_inplace(
    *,
    payload_root: Dict[str, Any],
    target_graph_id_int: int,
    gaps_report_path: Path,
    source_node_type_id_int: int,
    source_out_index: int,
) -> Dict[str, Any]:
    gaps_obj = json.loads(Path(gaps_report_path).read_text(encoding="utf-8"))
    if not isinstance(gaps_obj, dict):
        raise TypeError("gaps_report JSON 顶层必须是 dict")
    gaps = gaps_obj.get("gaps")
    if not isinstance(gaps, dict):
        raise TypeError("gaps_report 缺少 gaps(dict)")

    entry = _find_graph_entry(payload_root, int(target_graph_id_int))
    nodes_value = entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("target graph entry 缺少 nodes 列表 entry['3']")
    # 注意：nodes_value 才是 payload 内的“真实列表”；nodes 仅是便于类型标注与过滤的视图。
    # 若要新增节点，必须 append 到 nodes_value，否则不会写入文件（会导致悬空 other_node_id 连接）。
    nodes: List[Dict[str, Any]] = [n for n in nodes_value if isinstance(n, dict)]
    if not nodes:
        raise ValueError("target graph nodes 为空")

    # ===== 索引现有节点：type_id -> node_obj / node_id =====
    type_id_to_node: Dict[int, Dict[str, Any]] = {}
    type_id_to_node_id: Dict[int, int] = {}
    existing_node_ids: List[int] = []
    for n in nodes:
        node_id_value = n.get("1")
        node_id_int = node_id_value[0] if isinstance(node_id_value, list) and node_id_value and isinstance(node_id_value[0], int) else None
        if isinstance(node_id_int, int):
            existing_node_ids.append(int(node_id_int))
        tid = int(_decode_type_id_from_node(n))
        if int(tid) in type_id_to_node:
            # node wall 应该是唯一；若重复则直接报错避免写到错误节点
            raise ValueError(f"target graph 内存在重复 type_id 节点：type_id={int(tid)}")
        type_id_to_node[int(tid)] = n
        if isinstance(node_id_int, int):
            type_id_to_node_id[int(tid)] = int(node_id_int)

    if not existing_node_ids:
        raise ValueError("target graph 中未找到 node_id")

    # ===== 添加/复用 source node =====
    src_type_id = int(source_node_type_id_int)
    src_node_obj = type_id_to_node.get(src_type_id)
    if src_node_obj is None:
        template_node = copy.deepcopy(nodes[0])
        new_node_id_int = max(existing_node_ids) + 1
        existing_node_ids.append(int(new_node_id_int))
        template_node["1"] = [int(new_node_id_int)]
        template_node["5"] = float(template_node.get("5", 0.0) or 0.0) - 900.0
        template_node["6"] = float(template_node.get("6", 0.0) or 0.0)
        template_node["4"] = []
        template_node["2"] = _patch_node_type_id_in_binary_text(str(template_node.get("2")), int(src_type_id))
        template_node["3"] = _patch_node_type_id_in_binary_text(str(template_node.get("3")), int(src_type_id))
        nodes_value.append(template_node)
        nodes.append(template_node)
        type_id_to_node[int(src_type_id)] = template_node
        type_id_to_node_id[int(src_type_id)] = int(new_node_id_int)
        src_node_obj = template_node

    src_node_id_int = type_id_to_node_id.get(int(src_type_id))
    if not isinstance(src_node_id_int, int):
        raise ValueError("source node 缺少 node_id")

    # ===== data-link record（按 gaps 需求写入）=====
    missing_data = gaps.get("missing_data_link_slot_templates") or []
    if not isinstance(missing_data, list):
        raise TypeError("gaps.missing_data_link_slot_templates 必须是 list")

    added_data_records = 0
    for item in missing_data:
        if not isinstance(item, dict):
            continue
        dst_type_id_int = int(item.get("dst_type_id_int"))
        pin_index = int(item.get("slot_index"))

        dst_node = type_id_to_node.get(int(dst_type_id_int))
        if dst_node is None:
            # 若 target graph 内没有该 type_id，则补一个节点（用 patch type_id 的模板节点提供承载 record 的容器）
            template_node = copy.deepcopy(nodes[0])
            new_node_id_int = max(existing_node_ids) + 1
            existing_node_ids.append(int(new_node_id_int))
            template_node["1"] = [int(new_node_id_int)]
            template_node["5"] = float(template_node.get("5", 0.0) or 0.0) + 900.0
            template_node["6"] = float(template_node.get("6", 0.0) or 0.0)
            template_node["4"] = []
            template_node["2"] = _patch_node_type_id_in_binary_text(str(template_node.get("2")), int(dst_type_id_int))
            template_node["3"] = _patch_node_type_id_in_binary_text(str(template_node.get("3")), int(dst_type_id_int))
            nodes_value.append(template_node)
            nodes.append(template_node)
            type_id_to_node[int(dst_type_id_int)] = template_node
            type_id_to_node_id[int(dst_type_id_int)] = int(new_node_id_int)
            dst_node = template_node

        # 端口 VarType：优先使用 gaps 报告中已给出的字段（不再反向打开 GraphModel 文件，避免 out/ 产物变成输入依赖）。
        dst_var_type_int_raw = item.get("dst_var_type_int")
        dst_port_type_text = str(item.get("dst_port_type_text") or "").strip()
        dst_var_type_int: int
        if isinstance(dst_var_type_int_raw, int):
            dst_var_type_int = int(dst_var_type_int_raw)
        elif dst_port_type_text:
            mapped = _try_map_port_type_text_to_var_type_int(dst_port_type_text)
            if not isinstance(mapped, int):
                raise ValueError(
                    "data-link gap 条目提供了 dst_port_type_text，但无法映射为 VarType："
                    f"dst_type_id_int={int(dst_type_id_int)} pin_index={int(pin_index)} port_type={dst_port_type_text!r}"
                )
            dst_var_type_int = int(mapped)
        else:
            # 兼容旧报告：回退到从 example_graph_json 读取 input_port_types/input_types 推导 VarType
            dst_title = str(item.get("dst_title_example") or item.get("node_name") or "").strip()
            dst_port = str(item.get("dst_port_example") or "").strip()
            example_graph_json = str(item.get("example_graph_json") or "").strip()
            if dst_title == "" or dst_port == "" or example_graph_json == "":
                raise ValueError(
                    "data-link gap 条目缺少 dst_var_type_int/dst_port_type_text，且示例信息不完整："
                    f"dst_type_id_int={int(dst_type_id_int)} pin_index={int(pin_index)} item={item!r}"
                )
            dst_var_type_int = _resolve_input_port_var_type_int_from_example_graph(
                example_graph_json_path=Path(example_graph_json),
                node_title=str(dst_title),
                input_port_name=str(dst_port),
            )

        dst_records = _ensure_record_list(dst_node)
        exist_index = _find_existing_record_index(records=dst_records, kind=3, index=int(pin_index))
        if exist_index is not None:
            # 已有 record：若已经包含 field_5(连线) 则跳过；否则“就地补齐连接”
            decoded0 = decode_bytes_to_python(parse_binary_data_hex_text(str(dst_records[int(exist_index)])))
            if isinstance(decoded0, dict) and ("field_5" in decoded0):
                continue
            if not isinstance(decoded0, dict):
                continue
            dump_msg = _decoded_field_map_to_dump_json_message(decoded0)
            dump_msg["4"] = int(dst_var_type_int)
            dump_msg["5"] = _build_node_connection_message(
                other_node_id_int=int(src_node_id_int),
                kind=4,  # OutParam
                index=int(source_out_index),
            )
            dst_records[int(exist_index)] = format_binary_data_hex_text(encode_message(dump_msg))
            added_data_records += 1
            continue

        connect_msg = _build_node_connection_message(
            other_node_id_int=int(src_node_id_int),
            kind=4,  # OutParam
            index=int(source_out_index),
        )
        pin_msg = _build_node_pin_message(
            kind=3,  # InParam
            index=int(pin_index),
            var_type_int=int(dst_var_type_int),
            connects=[connect_msg],
        )
        dst_records.append(format_binary_data_hex_text(encode_message(pin_msg)))
        added_data_records += 1

    # ===== OutParam record（按 gaps 需求写入）=====
    missing_outparam = gaps.get("missing_outparam_templates") or []
    if not isinstance(missing_outparam, list):
        raise TypeError("gaps.missing_outparam_templates 必须是 list")

    added_outparam_records = 0
    for item in missing_outparam:
        if not isinstance(item, dict):
            continue
        type_id_int = int(item.get("type_id_int"))
        out_index = int(item.get("out_index"))
        desired_var_type_int = int(item.get("desired_var_type_int"))
        node_title = str(item.get("node_name") or item.get("node_title") or "").strip()
        out_port = str(item.get("out_port") or "").strip()
        if node_title == "":
            node_title = str(item.get("node_title") or "").strip()

        node_obj = type_id_to_node.get(int(type_id_int))
        if node_obj is None:
            # 若 target graph 内没有该 type_id，则补一个节点（同样用 patch type_id 的模板节点）
            template_node = copy.deepcopy(nodes[0])
            new_node_id_int = max(existing_node_ids) + 1
            existing_node_ids.append(int(new_node_id_int))
            template_node["1"] = [int(new_node_id_int)]
            template_node["5"] = float(template_node.get("5", 0.0) or 0.0) + 900.0
            template_node["6"] = float(template_node.get("6", 0.0) or 0.0) + 900.0
            template_node["4"] = []
            template_node["2"] = _patch_node_type_id_in_binary_text(str(template_node.get("2")), int(type_id_int))
            template_node["3"] = _patch_node_type_id_in_binary_text(str(template_node.get("3")), int(type_id_int))
            nodes_value.append(template_node)
            nodes.append(template_node)
            type_id_to_node[int(type_id_int)] = template_node
            type_id_to_node_id[int(type_id_int)] = int(new_node_id_int)
            node_obj = template_node

        records = _ensure_record_list(node_obj)
        exist_exact_index = _find_existing_outparam_record_index_by_var_type(
            records=records, out_index=int(out_index), var_type_int=int(desired_var_type_int)
        )
        record_text = _build_outparam_record_text(
            node_title=str(node_title),
            out_port=str(out_port),
            out_index=int(out_index),
            var_type_int=int(desired_var_type_int),
        )
        if exist_exact_index is not None:
            continue
        # 注意：同一个 (type_id, out_index) 在不同 GraphModel 样本中可能需要落到不同 VarType。
        # 因此这里不覆盖“同 index 的已有 OutParam record”，而是允许同 index 追加多条记录。
        records.append(str(record_text))
        added_outparam_records += 1

    return {
        "target_graph_id_int": int(target_graph_id_int),
        "source_node_type_id_int": int(src_type_id),
        "source_node_id_int": int(src_node_id_int),
        "source_out_index": int(source_out_index),
        "data_records_added_or_patched": int(added_data_records),
        "outparam_records_added_or_patched": int(added_outparam_records),
        "nodes_total_after": int(len(nodes)),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="根据 report_graph_writeback_gaps 的 JSON 报告，在指定 .gil 的指定节点图中自动写入 data-link/OutParam record（减少人工连线）。"
    )
    parser.add_argument("--input-gil", required=True, help="输入 .gil（将被 dump-json 并在内存中打补丁）")
    parser.add_argument("--graph-id", dest="graph_id_int", type=int, required=True, help="要写入 record 的 graph_id_int")
    parser.add_argument("--gaps-report", required=True, help="report_graph_writeback_gaps 的输出 JSON 路径")
    parser.add_argument("--output-gil", required=True, help="输出 .gil 文件名（强制写入 ugc_file_tools/out/）")
    parser.add_argument(
        "--source-type-id",
        dest="source_type_id_int",
        type=int,
        default=337,
        help="作为 data-link 连接源的节点 type_id（默认 337=获取节点图变量；client 可用 200082=获取局部变量）",
    )
    parser.add_argument(
        "--source-out-index",
        dest="source_out_index",
        type=int,
        default=0,
        help="source 节点的 data 输出索引（默认 0）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    input_gil_path = Path(args.input_gil).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))
    gaps_report_path = Path(args.gaps_report).resolve()
    if not gaps_report_path.is_file():
        raise FileNotFoundError(str(gaps_report_path))

    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_path)
    payload_root = _get_payload_root(raw_dump_object)

    patch_report = apply_gaps_to_graph_inplace(
        payload_root=payload_root,
        target_graph_id_int=int(args.graph_id_int),
        gaps_report_path=gaps_report_path,
        source_node_type_id_int=int(args.source_type_id_int),
        source_out_index=int(args.source_out_index),
    )

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_gil_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)

    output_path = resolve_output_file_path_in_out_dir(Path(str(args.output_gil)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    print("=" * 80)
    print("auto-wire 完成：")
    print(f"- input_gil: {str(input_gil_path)}")
    print(f"- output_gil: {str(output_path)}")
    for k in sorted(patch_report.keys()):
        print(f"- {k}: {patch_report.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



