from __future__ import annotations

"""
build_minimal_graph_variables_reference_gil.py

目标：
- 从一个已有的 `.gil`（作为结构容器/模板）生成“节点图变量全类型”的最简参考 `.gil`：
  - 清空目标图的 nodes（GraphEntry['3']），避免把演示节点/连线带进参考文件；
  - 重建 GraphEntry['6']（节点图变量定义表），覆盖 Graph_Generater.type_registry.VARIABLE_TYPES（允许集合）；
  - 产物写入 `ugc_file_tools/out/`，并可选跑写回合约校验（建议默认开启）。

说明：
- 该工具不尝试“最小化整个 payload 的所有段”，只保证：
  - 节点图变量表是“最完整的写回允许集合”；
  - 图内不携带多余演示 nodes；
  - 其余段保持输入样本的最小可用形态（避免删字段导致真源导入失败）。
- 不使用 try/except；失败直接抛错。
"""

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import load_graph_generater_type_registry
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

# 复用写回侧的“GraphEntry['6'] 变量表生成”逻辑（严格对齐 Graph_Generater VARIABLE_TYPES）
from ugc_file_tools.node_graph_writeback.graph_variables import build_graph_variable_def_item_from_metadata
from ugc_file_tools.node_graph_writeback.gil_dump import find_graph_entry, get_payload_root


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_dump_") as temp_dir:
        raw_json_path = Path(temp_dir) / "dump.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise ValueError("DLL dump-json 顶层不是 dict")
    return raw_dump_object


def _iter_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    sec10 = payload_root.get("10")
    if not isinstance(sec10, dict):
        return []
    groups = sec10.get("1")
    groups_list = groups if isinstance(groups, list) else [groups] if isinstance(groups, dict) else []
    out: List[int] = []
    for g in groups_list:
        if not isinstance(g, dict):
            continue
        entries = g.get("1")
        entries_list = entries if isinstance(entries, list) else [entries] if isinstance(entries, dict) else []
        for e in entries_list:
            if not isinstance(e, dict):
                continue
            header_value = e.get("1")
            header_obj = (
                header_value[0]
                if isinstance(header_value, list) and header_value and isinstance(header_value[0], dict)
                else header_value
            )
            if not isinstance(header_obj, dict):
                continue
            gid = header_obj.get("5")
            if isinstance(gid, int):
                out.append(int(gid))
    return out


def _build_minimal_graph_variables(*, dict_key_type: str, dict_value_type: str) -> List[Dict[str, Any]]:
    tr = load_graph_generater_type_registry()

    def default_value_for_type(type_text: str) -> Any:
        t = str(type_text).strip()
        if t == tr.TYPE_STRING:
            return ""
        if t == tr.TYPE_INTEGER:
            return 0
        if t == tr.TYPE_FLOAT:
            return 0.0
        if t == tr.TYPE_BOOLEAN:
            return False
        if t == tr.TYPE_VECTOR3:
            return (0.0, 0.0, 0.0)

        # id-like：用 0（避免引用校验风险）
        if t in (tr.TYPE_ENTITY, tr.TYPE_GUID, tr.TYPE_CAMP, tr.TYPE_CONFIG_ID, tr.TYPE_COMPONENT_ID):
            return 0

        # lists
        if t.endswith("列表"):
            return []

        # struct: 常见默认 None（运行期拼装）
        if t == tr.TYPE_STRUCT:
            return None
        if t == tr.TYPE_STRUCT_LIST:
            return []

        if t == tr.TYPE_DICT:
            return {}

        raise ValueError(f"未覆盖的变量类型默认值生成规则：{t!r}")

    variables: List[Dict[str, Any]] = []
    for type_text in list(tr.VARIABLE_TYPES):
        t = str(type_text).strip()
        if t == "":
            continue

        name = f"v_{t}"
        item: Dict[str, Any] = {
            "name": name,
            "variable_type": t,
            "default_value": default_value_for_type(t),
            "is_exposed": False,
        }

        if t == tr.TYPE_DICT:
            item["name"] = f"v_{t}_{dict_key_type}_{dict_value_type}"
            item["dict_key_type"] = str(dict_key_type)
            item["dict_value_type"] = str(dict_value_type)
        variables.append(item)

    # 稳定顺序：按 VARIABLE_TYPES 原顺序输出（不额外排序）
    return variables


def build_minimal_reference_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    graph_id_int: Optional[int],
    strip_nodes: bool,
    dict_key_type: str,
    dict_value_type: str,
) -> Dict[str, Any]:
    raw_dump_object = _dump_gil_to_raw_json_object(Path(input_gil_file_path))
    payload_root = get_payload_root(raw_dump_object)

    available_graph_ids = _iter_graph_ids(payload_root)
    if not available_graph_ids:
        raise ValueError("输入 .gil 不包含节点图段/graph entries，无法生成参考 gil（请换一个包含 graph 的样本）。")

    target_graph_id = int(graph_id_int) if graph_id_int is not None else int(available_graph_ids[0])
    entry = find_graph_entry(payload_root, int(target_graph_id))

    if bool(strip_nodes):
        entry["3"] = []

    variables = _build_minimal_graph_variables(dict_key_type=str(dict_key_type), dict_value_type=str(dict_value_type))
    entry["6"] = [build_graph_variable_def_item_from_metadata(v, struct_defs=None) for v in variables]

    # 输出
    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(Path(input_gil_file_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(Path(input_gil_file_path).resolve()),
        "output_gil": str(output_path),
        "graph_id_int": int(target_graph_id),
        "strip_nodes": bool(strip_nodes),
        "variables_count": int(len(variables)),
        "dict_key_type": str(dict_key_type),
        "dict_value_type": str(dict_value_type),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="生成“节点图变量全类型”的最简参考 .gil（清空 nodes，仅保留/重建 GraphEntry['6']）。")
    parser.add_argument("--input-gil", required=True, help="输入 .gil（作为结构容器/模板；需要包含至少一张节点图）。")
    parser.add_argument(
        "--output-gil",
        default="ref_graph_variables_all_supported_types.min.gil",
        help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument("--graph-id", type=int, default=None, help="可选：目标 graph_id_int；不填则使用第一个图。")
    parser.add_argument(
        "--keep-nodes",
        action="store_true",
        help="不清空 nodes（默认会清空，以去除演示节点/连线）。",
    )
    parser.add_argument(
        "--dict-key-type",
        default="字符串",
        help="字典变量的 key 类型（默认：字符串；必须属于 Graph_Generater VARIABLE_TYPES 且非字典）。",
    )
    parser.add_argument(
        "--dict-value-type",
        default="整数",
        help="字典变量的 value 类型（默认：整数；必须属于 Graph_Generater VARIABLE_TYPES 且非字典）。",
    )
    parser.add_argument(
        "--skip-contract-check",
        action="store_true",
        help="跳过节点图变量写回合约校验（不推荐；默认会校验输出 .gil）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_minimal_reference_gil(
        input_gil_file_path=Path(args.input_gil),
        output_gil_file_path=Path(args.output_gil),
        graph_id_int=(int(args.graph_id) if args.graph_id is not None else None),
        strip_nodes=(not bool(args.keep_nodes)),
        dict_key_type=str(args.dict_key_type),
        dict_value_type=str(args.dict_value_type),
    )

    if not bool(args.skip_contract_check):
        # 仅校验该 graph_id，避免 base/template 里其他图带来的噪声
        from ugc_file_tools.commands.check_graph_variable_writeback_contract import main as _contract_main

        _contract_main([report["output_gil"], "--graph-id", str(report["graph_id_int"])])

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



