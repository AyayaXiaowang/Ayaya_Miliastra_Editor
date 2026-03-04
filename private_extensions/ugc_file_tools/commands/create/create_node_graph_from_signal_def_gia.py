from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.signal_writeback import gia_export as signal_gia_export
from ugc_file_tools.node_graph_semantics.var_base import build_var_base_message_server


@dataclass(frozen=True, slots=True)
class _SignalPortSpec:
    signal_name: str
    send_node_def_id_int: int
    signal_name_port_index_int: int
    params: List[Tuple[str, int, int]]  # (param_name, type_id_int, port_index_int)


def _ensure_mapping(value: Any, *, hint: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping for {hint}, got {type(value).__name__}")
    return value


def _ensure_list_or_single_mapping(value: Any, *, hint: str) -> List[Mapping[str, Any]]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, Mapping)]
    if isinstance(value, Mapping):
        return [value]
    raise TypeError(f"expected list or mapping for {hint}, got {type(value).__name__}")


def _extract_int(value: Any, *, hint: str) -> int:
    if isinstance(value, int):
        return int(value)
    raise TypeError(f"expected int for {hint}, got {type(value).__name__}")


def _extract_utf8(value: Any, *, hint: str) -> str:
    if isinstance(value, str):
        return str(value)
    raise TypeError(f"expected str for {hint}, got {type(value).__name__}")


def _parse_send_node_def_for_ports(*, send_unit: Dict[str, Any]) -> _SignalPortSpec:
    """
    从“发送信号” GraphUnit 内部的 node_def（key '200' == '发送信号'）解析：
    - signal_name（node_def['107']['101']['1']）
    - signal_name_port_index（node_def['106']['8']）
    - params（node_def['102'][*]['1','3','8']）
    """
    # GraphUnit id: {'2': 23, '4': 0x6000_00xx}
    unit_id = _ensure_mapping(send_unit.get("1"), hint="send_unit['1'](GraphUnitId)")
    send_node_def_id_int = _extract_int(unit_id.get("4"), hint="send_unit.id.4(node_def_id)")

    node_def = signal_gia_export._find_node_def_object_in_graph_unit(dict(send_unit), expected_node_def_name="发送信号")
    node_def = _ensure_mapping(node_def, hint="node_def")

    # signal name port entry
    entry_106 = _ensure_mapping(node_def.get("106"), hint="node_def['106'](signal_name_port)")
    signal_name_port_index_int = _extract_int(entry_106.get("8"), hint="node_def['106']['8'](signal_name_port_index)")

    # signal name itself
    entry_107 = _ensure_mapping(node_def.get("107"), hint="node_def['107'](signal_info)")
    entry_101 = _ensure_mapping(entry_107.get("101"), hint="node_def['107']['101'](send_signal_spec)")
    signal_name = _extract_utf8(entry_101.get("1"), hint="node_def['107']['101']['1'](signal_name)")
    signal_name = str(signal_name).strip()
    if signal_name == "":
        raise ValueError("signal_name 为空（node_def['107']['101']['1']）")

    params_list = _ensure_list_or_single_mapping(node_def.get("102", []), hint="node_def['102'](params)")
    params: List[Tuple[str, int, int]] = []
    for idx, p in enumerate(params_list):
        p = _ensure_mapping(p, hint=f"param[{idx}]")
        name = _extract_utf8(p.get("1"), hint=f"param[{idx}]['1'](param_name)").strip()
        if name == "":
            raise ValueError(f"param_name 为空：index={idx}")
        # 真源信号 node_def 的参数 VarType 通常位于 param['4']['3']（而不是 param['3']['1']）。
        # 例如 `builtin_resources/gia_templates/signals/signal_node_defs_minimal.gia` 的 “台词内容” 参数是 var_type=6(字符串)。
        type_id_int: Optional[int] = None
        meta_4 = p.get("4")
        if isinstance(meta_4, Mapping):
            t3 = meta_4.get("3")
            if isinstance(t3, int):
                type_id_int = int(t3)
            else:
                t4 = meta_4.get("4")
                if isinstance(t4, int):
                    type_id_int = int(t4)

        if type_id_int is None:
            # 兼容旧形态/兜底：沿用历史解析路径
            type_msg = _ensure_mapping(p.get("3"), hint=f"param[{idx}]['3'](type_msg)")
            t1 = type_msg.get("1")
            if not isinstance(t1, int):
                raise ValueError(f"无法解析参数类型：param[{idx}] name={name!r}")
            type_id_int = int(t1)
        port_index_int = _extract_int(p.get("8"), hint=f"param[{idx}]['8'](port_index)")
        params.append((str(name), int(type_id_int), int(port_index_int)))

    if not params:
        raise ValueError(f"该信号无参数，无法作为“多参数示例”：signal_name={signal_name!r}")

    return _SignalPortSpec(
        signal_name=str(signal_name),
        send_node_def_id_int=int(send_node_def_id_int),
        signal_name_port_index_int=int(signal_name_port_index_int),
        params=list(params),
    )


def _build_node_graph_unit(
    *,
    graph_id_int: int,
    graph_name: str,
    spec: _SignalPortSpec,
    related_node_def_ids: Sequence[int],
) -> Dict[str, Any]:
    """
    生成一个最小 NodeGraph GraphUnit（与 `实体创建时.gia`/`信号示例.gia` 同结构）：
    - Trigger(71) -> Send(node_def_id)
    - Send 节点：多个 IN_PARAM + META pin（compositePinIndex 对齐 node_def 的 port indices）
    """
    trigger_node_index = 1
    send_node_index = 2

    # params -> node pins
    pins: List[Dict[str, Any]] = []
    for i, (param_name, type_id_int, port_index_int) in enumerate(list(spec.params)):
        # demo constant values by type
        value: Any
        if int(type_id_int) == 3:
            value = 123 + int(i)
        elif int(type_id_int) == 6:
            value = f"demo_{param_name}"
        elif int(type_id_int) == 4:
            value = True
        elif int(type_id_int) == 5:
            value = 0.25
        else:
            # unknown type: keep int placeholder (fail-fast is ok, but keep usable)
            value = 0

        def _pin_sig(kind: int, index: int) -> Dict[str, Any]:
            msg: Dict[str, Any] = {"1": int(kind)}
            if int(index) != 0:
                msg["2"] = int(index)
            return msg

        pins.append(
            {
                "1": _pin_sig(3, int(i)),  # IN_PARAM
                "2": _pin_sig(3, int(i)),
                "3": build_var_base_message_server(var_type_int=int(type_id_int), value=value),
                "4": int(type_id_int),
                "7": int(port_index_int),  # compositePinIndex
            }
        )

    # META pin: signal name binding (VarBase string), compositePinIndex=signal name port index
    pins.append(
        {
            "1": {"1": 5},  # META index=0 -> omit field_2
            "2": {"1": 5},
            "3": build_var_base_message_server(var_type_int=6, value=str(spec.signal_name)),
            "6": {"1": 6, "2": 1},  # binding_meta(kind=6,index=1)
            "7": int(spec.signal_name_port_index_int),
        }
    )

    # Trigger node (71): OutFlow(0) -> Send InFlow(0)
    trigger_node_msg: Dict[str, Any] = {
        "1": int(trigger_node_index),
        "2": {"1": 10001, "2": 20000, "3": 22000, "5": 71},
        "3": {"1": 10001, "2": 20000, "3": 22000, "5": 71},
        "4": [
            {
                "1": {"1": 2},  # OUT_FLOW index=0 -> omit field_2
                "5": [
                    {
                        "1": int(send_node_index),
                        "2": {"1": 1},  # IN_FLOW index=0
                        "3": {"1": 1},
                    }
                ],
            }
        ],
        "5": float(-796.0),
        "6": float(-597.0),
    }

    send_node_msg: Dict[str, Any] = {
        "1": int(send_node_index),
        "2": {"1": 10001, "2": 20000, "3": 22001, "5": int(spec.send_node_def_id_int)},
        "4": list(pins),
        "5": float(-45.0),
        "6": float(-333.0),
    }

    node_graph_message: Dict[str, Any] = {
        "1": {"1": 10000, "2": 20000, "3": 21001, "5": int(graph_id_int)},
        "2": str(graph_name),
        "3": [trigger_node_msg, send_node_msg],
    }

    graph_unit_id_msg: Dict[str, Any] = {"2": 5, "4": int(graph_id_int)}
    graph_unit: Dict[str, Any] = {
        "1": graph_unit_id_msg,
        "2": [{"2": 23, "4": int(x)} for x in list(related_node_def_ids)],
        "3": str(graph_name),
        "5": 9,
        "13": {"1": {"1": node_graph_message}},
    }
    return graph_unit


def create_gia(
    *,
    signal_def_gia: Path,
    output_name: str,
    graph_id_int: int,
    graph_name: str,
) -> Dict[str, Any]:
    # Load 3 signal node_def units from provided gia (must contain units named 发送信号/监听信号/向服务器节点图发送信号)
    tpl_send_unit, tpl_listen_unit, tpl_server_unit = signal_gia_export._load_signal_node_def_templates_from_gia(
        Path(signal_def_gia).resolve()
    )

    spec = _parse_send_node_def_for_ports(send_unit=dict(tpl_send_unit))
    send_id = int(spec.send_node_def_id_int)
    related_ids = [send_id, send_id + 1, send_id + 2]

    graph_unit = _build_node_graph_unit(
        graph_id_int=int(graph_id_int),
        graph_name=str(graph_name),
        spec=spec,
        related_node_def_ids=related_ids,
    )

    export_uid = 341416358
    export_ts = int(time.time())
    export_tag = f"{export_uid}-{export_ts}-{1073742107}-\\\\{Path(output_name).stem}.gia"

    root_message: Dict[str, Any] = {
        "1": graph_unit,
        "2": [dict(tpl_send_unit), dict(tpl_listen_unit), dict(tpl_server_unit)],
        "3": str(export_tag),
        "5": "6.3.0",
    }

    out_path = resolve_output_file_path_in_out_dir(Path(str(Path(output_name).stem) + ".gia"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(wrap_gia_container(encode_message(root_message)))

    meta_path = out_path.with_suffix(".signal_meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "signal_name": spec.signal_name,
                "send_node_def_id_int": spec.send_node_def_id_int,
                "signal_name_port_index_int": spec.signal_name_port_index_int,
                "params": [{"name": n, "type_id_int": t, "port_index_int": p} for (n, t, p) in spec.params],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {"output_gia_file": str(out_path), "signal_meta_json": str(meta_path), "signal_name": spec.signal_name}


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="从一个“信号定义样本 .gia”生成调用该信号的节点图 .gia（用于真源校验对照）。")
    parser.add_argument(
        "--signal-def-gia",
        default=str(Path("private_extensions/ugc_file_tools/builtin_resources/gia_templates/signals/signal_node_defs_minimal.gia")),
        help="输入：包含 发送信号/监听信号/向服务器节点图发送信号 的信号定义样本 .gia",
    )
    parser.add_argument("--output", default="从信号定义生成节点图.gia", help="输出文件名（写入 ugc_file_tools/out/）")
    parser.add_argument("--graph-id-int", type=int, default=1073741825, help="节点图 graph_id_int（server）")
    parser.add_argument("--graph-name", default="从信号定义生成节点图", help="节点图名称")
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = create_gia(
        signal_def_gia=Path(args.signal_def_gia),
        output_name=str(args.output),
        graph_id_int=int(args.graph_id_int),
        graph_name=str(args.graph_name),
    )

    print("=" * 80)
    print("节点图 .gia 生成完成：")
    for k in sorted(result.keys()):
        print(f"- {k}: {result.get(k)}")
    print("=" * 80)


if __name__ == "__main__":
    main()



