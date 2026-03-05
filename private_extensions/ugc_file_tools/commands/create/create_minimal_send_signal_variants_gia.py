from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root
from ugc_file_tools.signal_writeback.signal_node_def_units_builder import build_signal_node_def_bundle_for_signals


def _new_edge(*, src_node: str, src_port: str, dst_node: str, dst_port: str, edge_id: str) -> Dict[str, Any]:
    return {"id": str(edge_id), "src_node": str(src_node), "src_port": str(src_port), "dst_node": str(dst_node), "dst_port": str(dst_port)}


def _default_mapping_path() -> Path:
    return (repo_root() / "private_extensions" / "ugc_file_tools" / "graph_ir" / "node_type_semantic_map.json").resolve()


def _build_graph_model_json(
    *,
    graph_id: str,
    graph_name: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    graph_variables: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "graph_id": str(graph_id),
        "name": str(graph_name),
        "graph_type": "server",
        "folder_path": "实体节点图",
        "description": f"最小复现：实体创建时 + 发送信号（{graph_name}）",
        "data": {
            "graph_id": str(graph_id),
            "graph_name": str(graph_name),
            "description": f"最小复现：实体创建时 + 发送信号（{graph_name}）",
            "event_flow_order": ["event_实体创建时_00000000"],
            "event_flow_titles": ["实体创建时"],
            "nodes": list(nodes),
            "edges": list(edges),
            "graph_variables": list(graph_variables),
            "graph_comments": [],
            "affiliations": [],
        },
    }


def _make_event_entity_created_node(*, node_id: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "id": str(node_id),
        "title": "实体创建时",
        "category": "事件节点",
        "composite_id": "",
        "pos": [float(x), float(y)],
        "inputs": [],
        "outputs": ["流程出", "事件源实体", "事件源GUID"],
        "effective_input_types": {},
        "effective_output_types": {"流程出": "流程", "事件源实体": "实体", "事件源GUID": "GUID"},
        "input_constants": {},
        "input_port_declared_types": {},
        "output_port_declared_types": {"流程出": "流程", "事件源实体": "实体", "事件源GUID": "GUID"},
        "input_port_types": {},
        "output_port_types": {"流程出": "流程", "事件源实体": "实体", "事件源GUID": "GUID"},
    }


def _make_get_graph_var_node(*, node_id: str, var_name: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "id": str(node_id),
        "title": "获取节点图变量",
        "category": "查询节点",
        "composite_id": "",
        "pos": [float(x), float(y)],
        "inputs": ["变量名"],
        "outputs": ["变量值"],
        "effective_input_types": {"变量名": "字符串"},
        "effective_output_types": {"变量值": "泛型"},
        "input_constants": {"变量名": str(var_name)},
        "input_port_declared_types": {"变量名": "字符串"},
        "output_port_declared_types": {"变量值": "泛型"},
        "input_port_types": {"变量名": "字符串"},
        "output_port_types": {"变量值": "整数"},
    }


def _make_send_signal_node(
    *,
    node_id: str,
    signal_name: str,
    param_name: str,
    param_value_text: Optional[str],
    x: float,
    y: float,
) -> Dict[str, Any]:
    input_constants: Dict[str, Any] = {"信号名": str(signal_name)}
    if param_value_text is not None:
        input_constants[str(param_name)] = str(param_value_text)
    return {
        "id": str(node_id),
        "title": "发送信号",
        "category": "执行节点",
        "composite_id": "",
        "pos": [float(x), float(y)],
        "inputs": ["流程入", "信号名", str(param_name)],
        "outputs": ["流程出"],
        "effective_input_types": {"流程入": "流程", "信号名": "字符串", str(param_name): "整数"},
        "effective_output_types": {"流程出": "流程"},
        "input_constants": dict(input_constants),
        "input_port_declared_types": {"流程入": "流程", "信号名": "字符串", str(param_name): "泛型"},
        "output_port_declared_types": {"流程出": "流程"},
        "input_port_types": {"流程入": "流程", "信号名": "字符串", str(param_name): "整数"},
        "output_port_types": {"流程出": "流程"},
    }


def _make_graph_variable_int(*, name: str, default_value: int) -> Dict[str, Any]:
    return {
        "name": str(name),
        "variable_type": "整数",
        "default_value": int(default_value),
        "description": "最小复现用图变量。",
        "is_exposed": False,
    }


def _export_one(
    *,
    graph_json_object: Dict[str, Any],
    graph_id_int: int,
    graph_name: str,
    output_gia_name: str,
    copy_to: Optional[Path],
) -> Dict[str, Any]:
    from ugc_file_tools.gia_export.node_graph.asset_bundle_builder import GiaAssetBundleGraphExportHints, create_gia_file_from_graph_model_json
    from ugc_file_tools.node_graph_writeback.type_id_map import build_node_name_to_type_id as _build_node_name_to_type_id

    # 找出该最小图实际使用的信号名与参数声明（从 Send_Signal 节点 inputs/effective_input_types 推断）
    data = graph_json_object.get("data")
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, list):
        raise TypeError("graph_json_object.data.nodes must be list")
    send_nodes = [n for n in nodes if isinstance(n, dict) and str(n.get("title") or "").strip() == "发送信号"]
    if len(send_nodes) != 1:
        raise ValueError(f"expected exactly 1 Send_Signal node, got {len(send_nodes)}")
    send_node = dict(send_nodes[0])
    input_constants = send_node.get("input_constants")
    if not isinstance(input_constants, dict):
        raise TypeError("send_node.input_constants must be dict")
    signal_name = input_constants.get("信号名")
    if not isinstance(signal_name, str) or str(signal_name).strip() == "":
        raise ValueError("send_node.input_constants['信号名'] must be non-empty str")
    signal_name = str(signal_name).strip()
    inputs = send_node.get("inputs")
    input_types = send_node.get("effective_input_types")
    if not isinstance(inputs, list) or not isinstance(input_types, dict):
        raise TypeError("send_node.inputs/effective_input_types invalid")
    params: List[Dict[str, Any]] = []
    for p in inputs:
        pn = str(p or "").strip()
        if pn in {"流程入", "信号名"} or pn == "":
            continue
        t = input_types.get(pn)
        if not isinstance(t, str) or t.strip() == "":
            continue
        # 仅覆盖该工具的最小用例：整数/字符串/布尔/浮点数
        if "整数" in t:
            type_id_int = 3
        elif "字符串" in t:
            type_id_int = 6
        elif "布尔" in t:
            type_id_int = 4
        elif "浮点" in t:
            type_id_int = 5
        else:
            type_id_int = 3
        params.append({"param_name": pn, "type_id": int(type_id_int)})

    signal_bundle = build_signal_node_def_bundle_for_signals(signals=[{"signal_name": signal_name, "params": params}])
    send_id_by_name = dict(signal_bundle.send_node_def_id_by_signal_name)
    name_port_by_name = dict(signal_bundle.send_signal_name_port_index_by_signal_name)
    param_ports_by_name = dict(signal_bundle.send_param_port_indices_by_signal_name)
    param_types_by_name = dict(signal_bundle.send_param_var_type_ids_by_signal_name)

    mapping_path = _default_mapping_path()
    from ugc_file_tools.node_graph_writeback.type_id_map import build_node_def_key_to_type_id as _build_node_def_key_to_type_id

    node_type_id_by_node_def_key = _build_node_def_key_to_type_id(
        mapping_path=mapping_path,
        scope="server",
        graph_generater_root=repo_root(),
    )

    hints = GiaAssetBundleGraphExportHints(
        graph_id_int=int(graph_id_int),
        graph_name=str(graph_name),
        graph_scope="server",
        resource_class="ENTITY_NODE_GRAPH",
        graph_generater_root=repo_root(),
        node_type_id_by_node_def_key=dict(node_type_id_by_node_def_key),
        export_uid=0,
        game_version="6.3.0",
        signal_send_node_def_id_by_signal_name=dict(send_id_by_name) or None,
        signal_send_signal_name_port_index_by_signal_name=dict(name_port_by_name) or None,
        signal_send_param_port_indices_by_signal_name=dict(param_ports_by_name) or None,
        signal_send_param_var_type_ids_by_signal_name=dict(param_types_by_name) or None,
        extra_dependency_graph_units=list(signal_bundle.dependency_units),
        graph_related_ids=list(signal_bundle.related_ids),
    )

    output_rel = Path(str(output_gia_name))
    write_result = create_gia_file_from_graph_model_json(graph_json_object=graph_json_object, hints=hints, output_gia_path=output_rel)
    output_gia = Path(write_result["output_gia_file"]).resolve()

    copied = ""
    if copy_to is not None:
        dst_dir = Path(copy_to).resolve()
        dst_dir.mkdir(parents=True, exist_ok=True)
        target = (dst_dir / output_gia.name).resolve()
        shutil.copy2(output_gia, target)
        copied = str(target)

    return {"output_gia_file": str(output_gia), "copied_output_gia_file": str(copied)}


def create_variants(
    *,
    signal_name: str,
    param_name: str,
    output_prefix: str,
    copy_to: Optional[Path],
) -> Dict[str, Any]:
    # A) 不连线、不填参数（只写信号名）
    node_event = _make_event_entity_created_node(node_id="event_实体创建时_00000000", x=200.0, y=200.0)
    node_send = _make_send_signal_node(
        node_id="node_发送信号_00000000",
        signal_name=str(signal_name),
        param_name=str(param_name),
        param_value_text=None,
        x=900.0,
        y=200.0,
    )
    edges_a = [
        _new_edge(
            src_node=node_event["id"],
            src_port="流程出",
            dst_node=node_send["id"],
            dst_port="流程入",
            edge_id="edge_flow_a",
        )
    ]
    graph_a = _build_graph_model_json(
        graph_id="server_min_send_signal_no_param",
        graph_name=f"{output_prefix}_A_不连线不填参",
        nodes=[node_event, node_send],
        edges=edges_a,
        graph_variables=[],
    )

    # B) 不连线、直接填参数（常量）
    node_send_b = _make_send_signal_node(
        node_id="node_发送信号_00000000",
        signal_name=str(signal_name),
        param_name=str(param_name),
        param_value_text="1",
        x=900.0,
        y=200.0,
    )
    graph_b = _build_graph_model_json(
        graph_id="server_min_send_signal_const_param",
        graph_name=f"{output_prefix}_B_不连线直接填参",
        nodes=[node_event, node_send_b],
        edges=edges_a,
        graph_variables=[],
    )

    # C) 连线参数：通过“获取节点图变量”连到信号参数
    gv_name = "开始关卡号"
    node_get = _make_get_graph_var_node(node_id="node_获取节点图变量_00000000", var_name=gv_name, x=520.0, y=420.0)
    node_send_c = _make_send_signal_node(
        node_id="node_发送信号_00000000",
        signal_name=str(signal_name),
        param_name=str(param_name),
        param_value_text=None,
        x=900.0,
        y=200.0,
    )
    edges_c = list(edges_a) + [
        _new_edge(
            src_node=node_get["id"],
            src_port="变量值",
            dst_node=node_send_c["id"],
            dst_port=str(param_name),
            edge_id="edge_data_c",
        )
    ]
    graph_c = _build_graph_model_json(
        graph_id="server_min_send_signal_wired_param",
        graph_name=f"{output_prefix}_C_连线参数",
        nodes=[node_event, node_get, node_send_c],
        edges=edges_c,
        graph_variables=[_make_graph_variable_int(name=gv_name, default_value=1)],
    )

    # graph_id_int: choose stable but unique-ish ids
    a = _export_one(
        graph_json_object=graph_a,
        graph_id_int=1073744901,
        graph_name=str(graph_a["name"]),
        output_gia_name=f"{output_prefix}_A_不连线不填参.gia",
        copy_to=copy_to,
    )
    b = _export_one(
        graph_json_object=graph_b,
        graph_id_int=1073744902,
        graph_name=str(graph_b["name"]),
        output_gia_name=f"{output_prefix}_B_不连线直接填参.gia",
        copy_to=copy_to,
    )
    c = _export_one(
        graph_json_object=graph_c,
        graph_id_int=1073744903,
        graph_name=str(graph_c["name"]),
        output_gia_name=f"{output_prefix}_C_连线参数.gia",
        copy_to=copy_to,
    )

    out_debug = resolve_output_file_path_in_out_dir(Path(f"{output_prefix}__variants.graph_model.json"))
    out_debug.write_text(json.dumps({"A": graph_a, "B": graph_b, "C": graph_c}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"A": a, "B": b, "C": c, "debug_graph_model_json": str(out_debug)}


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="生成最小的“实体创建时 + 发送信号”节点图变体并导出为 .gia。")
    parser.add_argument("--signal-name", default="关卡大厅_开始关卡", help="信号名（必须在 builtin_signal_defs.json 中可查到）。")
    parser.add_argument("--param-name", default="第X关", help="信号参数名（默认 第X关）。")
    parser.add_argument("--output-prefix", default="最小_实体创建时_发送信号", help="输出文件名前缀（写入 ugc_file_tools/out/）。")
    parser.add_argument("--copy-to", default="", help="可选：额外复制到该目录（绝对路径）。")
    args = parser.parse_args(list(argv) if argv is not None else None)

    copy_to: Optional[Path] = None
    if str(args.copy_to or "").strip() != "":
        copy_to = Path(str(args.copy_to)).resolve()
        if not copy_to.is_absolute():
            raise ValueError("copy_to 必须是绝对路径")

    result = create_variants(
        signal_name=str(args.signal_name),
        param_name=str(args.param_name),
        output_prefix=str(args.output_prefix),
        copy_to=copy_to,
    )
    print("=" * 80)
    print("最小节点图变体导出完成：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 80)


if __name__ == "__main__":
    main()


