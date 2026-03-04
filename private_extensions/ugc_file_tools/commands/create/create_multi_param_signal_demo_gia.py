from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.signal_writeback import gia_export as signal_gia_export


@dataclass(frozen=True, slots=True)
class DemoSignalParam:
    name: str
    type_id: int  # server VarTypeId (e.g. Int=3, Str=6, Bol=4, Flt=5, GUID=2, Vec=12)


def _build_demo_signal_node_defs(
    *,
    template_gia: Path | None,
    signal_name: str,
    params: Sequence[DemoSignalParam],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    生成 3 个 node_def GraphUnit（发送/监听/向服务器发送），并返回：
    - units: [send_unit, listen_unit, server_unit]
    - binding: 用于 NodeGraph 内的 Send_Signal 节点绑定信息：
      {
        "send_node_def_id_int": ...,
        "send_signal_name_port_index_int": ...,
        "send_param_port_indices_int": [...],
      }
    """
    template_path = Path(template_gia).resolve() if template_gia is not None else signal_gia_export._default_template_gia_path()
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))

    tpl_send_unit, tpl_listen_unit, tpl_server_unit = signal_gia_export._load_signal_node_def_templates_from_gia(template_path)

    # 分配策略（对齐 signal_writeback.gia_export）：从 0x60000001 起
    send_node_def_id = int(0x60000001)
    listen_node_def_id = int(0x60000002)
    server_node_def_id = int(0x60000003)

    # port indices（对齐 gia_export 的分配风格：从 1 起递增）
    next_port_index = 1
    send_flow_in = int(next_port_index)
    send_flow_out = int(next_port_index + 1)
    send_signal_name_port = int(next_port_index + 2)
    next_port_index += 3

    listen_flow = int(next_port_index)
    listen_signal_name_port = int(next_port_index + 1)
    listen_event_source_entity = int(next_port_index + 2)
    listen_event_source_guid = int(next_port_index + 3)
    listen_signal_source_entity = int(next_port_index + 4)
    next_port_index += 5

    server_flow_in = int(next_port_index)
    server_flow_out = int(next_port_index + 1)
    server_extra_port = int(next_port_index + 2)
    server_signal_name_port = int(next_port_index + 3)
    next_port_index += 4

    # allocate params ports (send/listen/server each has its own port index)
    send_param_items: List[Dict[str, Any]] = []
    server_param_items: List[Dict[str, Any]] = []
    listen_param_ports: List[Dict[str, Any]] = []
    send_param_port_indices: List[int] = []

    for param_ordinal, p in enumerate(list(params)):
        param_name = str(p.name).strip()
        if param_name == "":
            raise ValueError("param_name 不能为空")
        type_id = int(p.type_id)
        if type_id <= 0:
            raise ValueError(f"param type_id 无效：name={param_name!r} type_id={type_id}")

        send_port = int(next_port_index)
        listen_port = int(next_port_index + 1)
        server_port = int(next_port_index + 2)
        next_port_index += 3

        # signal_writeback 的 param_item message 构造器（复用其 schema 口径）
        send_param_items.append(
            signal_gia_export._build_param_item_message_from_param_spec(
                param_spec={"param_name": param_name, "type_id": int(type_id)},
                port_index_int=int(send_port),
                param_ordinal_int=int(param_ordinal),
                for_server_node=False,
            )
        )
        server_param_items.append(
            signal_gia_export._build_param_item_message_from_param_spec(
                param_spec={"param_name": param_name, "type_id": int(type_id)},
                port_index_int=int(server_port),
                param_ordinal_int=int(param_ordinal),
                for_server_node=True,
            )
        )
        listen_param_ports.append(
            {
                "param_name": str(param_name),
                "type_id": int(type_id),
                "port_index": int(listen_port),
            }
        )
        send_param_port_indices.append(int(send_port))

    # meta dicts（复用 gia_export 的构造器）
    signal_index_int = 1
    send_meta = signal_gia_export._build_node_def_meta_dict(node_def_id_int=send_node_def_id, scope_code_int=20000)
    listen_meta = signal_gia_export._build_node_def_meta_dict(node_def_id_int=listen_node_def_id, scope_code_int=20000)
    server_meta = signal_gia_export._build_node_def_meta_dict(node_def_id_int=server_node_def_id, scope_code_int=20002)

    # clone templates
    send_unit = copy.deepcopy(dict(tpl_send_unit))
    listen_unit = copy.deepcopy(dict(tpl_listen_unit))
    server_unit = copy.deepcopy(dict(tpl_server_unit))

    # patch graph unit ids + related ids
    signal_gia_export._set_graph_unit_id_inplace(send_unit, node_def_id_int=send_node_def_id)
    signal_gia_export._set_graph_unit_id_inplace(listen_unit, node_def_id_int=listen_node_def_id)
    signal_gia_export._set_graph_unit_id_inplace(server_unit, node_def_id_int=server_node_def_id)

    signal_gia_export._set_graph_unit_related_ids_inplace(send_unit, related_node_def_ids=[listen_node_def_id, server_node_def_id])
    signal_gia_export._set_graph_unit_related_ids_inplace(listen_unit, related_node_def_ids=[send_node_def_id, server_node_def_id])
    signal_gia_export._set_graph_unit_related_ids_inplace(server_unit, related_node_def_ids=[send_node_def_id, listen_node_def_id])

    # patch node defs
    send_node_def = signal_gia_export._find_node_def_object_in_graph_unit(send_unit, expected_node_def_name="发送信号")
    listen_node_def = signal_gia_export._find_node_def_object_in_graph_unit(listen_unit, expected_node_def_name="监听信号")
    server_node_def = signal_gia_export._find_node_def_object_in_graph_unit(server_unit, expected_node_def_name="向服务器节点图发送信号")

    send_node_def = signal_gia_export._reset_send_node_def_for_new_signal(
        node_def=send_node_def,
        signal_index_int=int(signal_index_int),
        node_def_id_int=int(send_node_def_id),
        signal_name=str(signal_name),
        listen_meta_dict=dict(listen_meta),
        server_meta_dict=dict(server_meta),
        flow_in_port_index=int(send_flow_in),
        flow_out_port_index=int(send_flow_out),
        signal_name_port_index=int(send_signal_name_port),
        send_param_items=list(send_param_items),
    )
    listen_node_def = signal_gia_export._reset_listen_node_def_for_new_signal(
        node_def=listen_node_def,
        signal_index_int=int(signal_index_int),
        node_def_id_int=int(listen_node_def_id),
        signal_name=str(signal_name),
        send_meta_dict=dict(send_meta),
        server_meta_dict=dict(server_meta),
        flow_port_index=int(listen_flow),
        signal_name_port_index=int(listen_signal_name_port),
        fixed_output_port_indices=(int(listen_event_source_entity), int(listen_event_source_guid), int(listen_signal_source_entity)),
        params=list(listen_param_ports),
    )
    server_node_def = signal_gia_export._reset_send_to_server_node_def_for_new_signal(
        node_def=server_node_def,
        signal_index_int=int(signal_index_int),
        node_def_id_int=int(server_node_def_id),
        signal_name=str(signal_name),
        listen_meta_dict=dict(listen_meta),
        send_meta_dict=dict(send_meta),
        flow_in_port_index=int(server_flow_in),
        flow_out_port_index=int(server_flow_out),
        extra_port_index=int(server_extra_port),
        signal_name_port_index=int(server_signal_name_port),
        server_param_items=list(server_param_items),
    )

    def _replace_node_def_inplace(unit: Dict[str, Any], *, expected: str, new_obj: Dict[str, Any]) -> None:
        expected_name = str(expected).strip()
        replaced = {"done": False}

        def walk(value: Any) -> Any:
            if isinstance(value, dict):
                v200 = value.get("200")
                if isinstance(v200, str) and v200.strip() == expected_name:
                    if isinstance(value.get("4"), dict) and isinstance(value.get("107"), dict):
                        replaced["done"] = True
                        return dict(new_obj)
                for k, child in list(value.items()):
                    value[k] = walk(child)
                return value
            if isinstance(value, list):
                for i, child in enumerate(list(value)):
                    value[i] = walk(child)
                return value
            return value

        walk(unit)
        if not replaced["done"]:
            raise ValueError(f"未能替换 node_def：{expected_name!r}")

    _replace_node_def_inplace(send_unit, expected="发送信号", new_obj=send_node_def)
    _replace_node_def_inplace(listen_unit, expected="监听信号", new_obj=listen_node_def)
    _replace_node_def_inplace(server_unit, expected="向服务器节点图发送信号", new_obj=server_node_def)

    binding = {
        "send_node_def_id_int": int(send_node_def_id),
        "send_signal_name_port_index_int": int(send_signal_name_port),
        "send_param_port_indices_int": list(send_param_port_indices),
    }
    return [send_unit, listen_unit, server_unit], binding


def _build_demo_node_graph_ir(*, graph_id_int: int, graph_name: str, binding: Mapping[str, Any]) -> Dict[str, Any]:
    send_node_def_id_int = int(binding["send_node_def_id_int"])
    send_signal_name_port_index_int = int(binding["send_signal_name_port_index_int"])
    send_param_port_indices_int = [int(x) for x in list(binding["send_param_port_indices_int"])]
    if not send_param_port_indices_int:
        raise ValueError("demo signal must have >=1 param")

    # 2 个节点：Trigger(When_Entity_Is_Created) + Send_Signal(node_def)
    # 注：这里的 Send 节点 runtime_id 直接用 node_def_id（kind=22001），对齐信号示例。
    #
    # pins 约定：
    # - node_index 1: OutFlow(0) -> node_index 2 InFlow(0)
    # - node_index 2: IN_PARAM pins 按 0..n-1（局部 index），并写 compositePinIndex=全局 port index
    # - node_index 2: META pin(kind=5) 写信号名，binding_meta(kind=6,index=1)，并写 compositePinIndex=信号名端口 index
    trigger_node_index = 1
    send_node_index = 2

    # 参数常量示例（演示用）：Int=123, Str="hello", Bol=True...（按参数数目循环）
    demo_values: List[Any] = []
    for i in range(len(send_param_port_indices_int)):
        if i == 0:
            demo_values.append(123)
        elif i == 1:
            demo_values.append("hello")
        elif i == 2:
            demo_values.append(True)
        elif i == 3:
            demo_values.append(0.25)
        else:
            demo_values.append(i)

    nodes: List[Dict[str, Any]] = []

    # Trigger: When_Entity_Is_Created (71)
    nodes.append(
        {
            "node_index_int": int(trigger_node_index),
            "node_type_id_int": 71,
            "node_type_name": "When_Entity_Is_Created",
            "node_type_class": "Trigger",
            "node_type_family": "III. Entity Related",
            "node_type_inputs": [],
            "node_type_outputs": ["Ety", "Gid"],
            "generic_id": {"class_int": 10001, "type_int": 20000, "kind_int": 22000, "node_id_int": 71},
            "concrete_id": {"class_int": 10001, "type_int": 20000, "kind_int": 22000, "node_id_int": 71},
            "pos": {"x": -600.0, "y": -300.0},
            "comment": None,
            "input": None,
            "using_structs": [],
            "pin_count": 1,
            "pins": [
                {
                    "kind_int": 2,  # OUT_FLOW
                    "index_int": 0,
                    "type_id_int": None,
                    "type_expr": "",
                    "value": None,
                    "dict_key_type_int": None,
                    "dict_value_type_int": None,
                    "connects": [
                        {
                            "remote_node_index_int": int(send_node_index),
                            "connect": {"kind_int": 1, "index_int": 0, "client_exec_node_id_int": None},
                            "connect2": {"kind_int": 1, "index_int": 0, "client_exec_node_id_int": None},
                        }
                    ],
                    "i2": {"kind_int": 2, "index_int": 0, "client_exec_node_id_int": None},
                    "i1_client_exec_node_id_int": None,
                    "client_exec_node": None,
                    "composite_pin_index_int": None,
                }
            ],
            "edges_from_pins": [],
        }
    )

    # Send node (node_def runtime_id)
    send_pins: List[Dict[str, Any]] = []
    # InFlow pin (kind=1) 不在 IR 中显式表达；用 flow edge 的 connect 即可。
    # 这里直接只写 data pins + meta pin（和信号示例保持一致：只有 2 个 pins）
    for i, global_port_index in enumerate(send_param_port_indices_int):
        send_pins.append(
            {
                "kind_int": 3,  # IN_PARAM
                "index_int": int(i),
                "type_id_int": 3 if isinstance(demo_values[i], int) else (6 if isinstance(demo_values[i], str) else (4 if isinstance(demo_values[i], bool) else 5)),
                "type_expr": "",
                "value": demo_values[i],
                "dict_key_type_int": None,
                "dict_value_type_int": None,
                "connects": [],
                "i2": {"kind_int": 3, "index_int": int(i), "client_exec_node_id_int": None},
                "i1_client_exec_node_id_int": None,
                "client_exec_node": None,
                "composite_pin_index_int": int(global_port_index),
            }
        )

    send_pins.append(
        {
            "kind_int": 5,  # META
            "index_int": 0,
            "type_id_int": None,
            "type_expr": "",
            "value": str(graph_name),  # 这里会被替换为 signal_name（见 main 构造）
            "dict_key_type_int": None,
            "dict_value_type_int": None,
            "connects": [],
            "i2": None,
            "i1_client_exec_node_id_int": None,
            "client_exec_node": {"kind_int": 6, "index_int": 1, "client_exec_node_id_int": None},
            "composite_pin_index_int": int(send_signal_name_port_index_int),
        }
    )

    nodes.append(
        {
            "node_index_int": int(send_node_index),
            "node_type_id_int": int(send_node_def_id_int),
            "node_type_name": "",
            "node_type_class": "",
            "node_type_family": "",
            "node_type_inputs": [],
            "node_type_outputs": [],
            "generic_id": {
                "class_int": 10001,
                "type_int": 20000,
                "kind_int": 22001,
                "node_id_int": int(send_node_def_id_int),
            },
            "concrete_id": None,
            "pos": {"x": -40.0, "y": -300.0},
            "comment": None,
            "input": None,
            "using_structs": [],
            "pin_count": len(send_pins),
            "pins": send_pins,
            "edges_from_pins": [],
        }
    )

    # 图元信息：按信号示例的 graph_info 口径
    return {
        "schema_version": 2,
        "graph_id_int": int(graph_id_int),
        "graph_name": str(graph_name),
        "graph_scope": "server",
        "node_count": len(nodes),
        "nodes": nodes,
        "edges": [],
        "graph_comments": [],
        "graph_variables": [],
        "affiliations": [],
        "composite_pins": [],
        "graph_meta": {},
        "graph_info": {"class_int": 10000, "type_int": 20000, "kind_int": 21001},
        "graph_unit": {"id_int": int(graph_id_int), "class_int": 5, "type_int": 0, "which_int": 9, "name": str(graph_name)},
        "root_file_path": f"0-0-0-\\\\{graph_name}.gia",
        "root_game_version": "6.3.0",
    }


def create_demo_gia(
    *,
    output_file_name_in_out: str,
    signal_name: str,
    params: Sequence[DemoSignalParam],
    template_gia: Path | None,
) -> Dict[str, Any]:
    signal_name = str(signal_name).strip()
    if signal_name == "":
        raise ValueError("signal_name 不能为空")
    if not params:
        raise ValueError("params 不能为空（至少 1 个参数）")

    # 1) build node_def units
    node_def_units, binding = _build_demo_signal_node_defs(
        template_gia=template_gia,
        signal_name=str(signal_name),
        params=list(params),
    )

    # 2) build node graph unit (Graph IR -> GraphUnit message)
    from ugc_file_tools.commands import gia_graph_ir_to_gia as ir_to_gia

    graph_id_int = 1073742959  # server id（演示用，避免与现有样本冲突）
    graph_name = "多参数信号示例"
    graph_ir = _build_demo_node_graph_ir(graph_id_int=graph_id_int, graph_name=graph_name, binding=binding)

    # 把 META pin 里的 value 替换为真正 signal_name（避免误导）
    for node in graph_ir.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if int(node.get("node_type_id_int") or 0) != int(binding["send_node_def_id_int"]):
            continue
        pins = node.get("pins") or []
        if not isinstance(pins, list):
            continue
        for p in pins:
            if isinstance(p, dict) and int(p.get("kind_int") or 0) == 5:
                p["value"] = str(signal_name)

    node_graph_message = ir_to_gia._build_node_graph_message(graph_ir)
    graph_unit_message = ir_to_gia._build_graph_unit_message(graph_ir, node_graph_message)
    # 关键：把信号 node_def units 作为 graph unit 的 relatedIds 挂上。
    # 否则导入时可能不会加载 accessories，从而表现为“信号节点无参数端口”。
    send_node_def_id_int = int(binding["send_node_def_id_int"])
    graph_unit_message["2"] = [
        {"2": 23, "4": int(send_node_def_id_int)},
        {"2": 23, "4": int(send_node_def_id_int + 1)},
        {"2": 23, "4": int(send_node_def_id_int + 2)},
    ]

    # 3) root: graph + accessories(node_defs)
    file_stem = Path(str(output_file_name_in_out)).stem
    if file_stem.strip() == "":
        file_stem = "多参数信号示例"
    # 真源样本的 Root.filePath 形如：<uid>-<timestamp>-<some_id>-\\<file>.gia
    # 其中 <some_id> 不强制等于 graph_id_int（见用户样本），但不能是 0-0-0。
    import time

    export_uid = 341416358
    export_ts = int(time.time())
    export_tag = f"{export_uid}-{export_ts}-{int(graph_id_int)}-\\\\{file_stem}.gia"

    root_message: Dict[str, Any] = {
        "1": graph_unit_message,
        "2": list(node_def_units),
        "3": str(export_tag),
        "5": "6.3.0",
    }

    output_path = resolve_output_file_path_in_out_dir(Path(f"{file_stem}.gia"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(wrap_gia_container(encode_message(root_message)))

    # 同时把“绑定信息”落盘成 json，便于你核对端口索引
    binding_json_path = output_path.with_suffix(".binding.json")
    binding_json_path.write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "output_gia_file": str(output_path),
        "binding_json": str(binding_json_path),
        "send_node_def_id_int": int(binding["send_node_def_id_int"]),
        "send_signal_name_port_index_int": int(binding["send_signal_name_port_index_int"]),
        "send_param_port_indices_int": list(binding["send_param_port_indices_int"]),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="生成一个“多参数信号”的自包含节点图 .gia（不依赖 .gil）。")
    parser.add_argument("--output", default="demo_multi_param_signal.gia", help="输出文件名（写入 ugc_file_tools/out/）")
    parser.add_argument("--signal-name", required=True, help="信号名（字符串）")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="参数，格式：name=type_id，例如：第X关=3 或 文本=6 或 是否成功=4（可重复传参）",
    )
    parser.add_argument(
        "--template-gia",
        default="",
        help="可选：信号模板 .gia 路径（默认使用 builtin_resources/gia_templates/signals/signal_node_defs_full.gia）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    params: List[DemoSignalParam] = []
    for raw in list(args.param or []):
        text = str(raw or "").strip()
        if "=" not in text:
            raise ValueError(f"--param 需要 name=type_id：{text!r}")
        name, type_text = text.split("=", 1)
        name = str(name).strip()
        type_text = str(type_text).strip()
        if name == "":
            raise ValueError(f"--param name 不能为空：{text!r}")
        if type_text == "" or (not type_text.lstrip("-").isdigit()):
            raise ValueError(f"--param type_id 必须是整数：{text!r}")
        params.append(DemoSignalParam(name=str(name), type_id=int(type_text)))

    template_text = str(args.template_gia or "").strip()
    template_path = Path(template_text).resolve() if template_text else None

    result = create_demo_gia(
        output_file_name_in_out=str(args.output),
        signal_name=str(args.signal_name),
        params=params,
        template_gia=template_path,
    )

    print("=" * 80)
    print("多参数信号示例 .gia 生成完成：")
    for k in sorted(result.keys()):
        print(f"- {k}: {result.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



