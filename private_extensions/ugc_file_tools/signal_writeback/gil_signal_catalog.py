from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object


@dataclass(frozen=True, slots=True)
class GilSignalDef:
    signal_name: str
    send_node_def_id_int: int
    listen_node_def_id_int: int
    server_send_node_def_id_int: int
    send_signal_name_port_index_int: int | None
    send_param_port_indices_int: List[int]


def _ensure_mapping(value: Any, *, hint: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping for {hint}, got {type(value).__name__}")
    return value


def _ensure_dict(value: Any, *, hint: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"expected dict for {hint}, got {type(value).__name__}")
    return value


def _ensure_list(value: Any, *, hint: str) -> List[Any]:
    if not isinstance(value, list):
        raise TypeError(f"expected list for {hint}, got {type(value).__name__}")
    return value


def _ensure_list_or_single_mapping(value: Any, *, hint: str) -> List[Any]:
    """
    兼容 repeated message 的 dump-json 形态差异：
    - 多元素：list([...])
    - 单元素：dict({...})（DLL/解码器有时会“压扁”重复字段）
    """
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return [value]
    raise TypeError(f"expected list or mapping for {hint}, got {type(value).__name__}")


def _extract_int(value: Any, *, hint: str) -> int:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, Mapping) and isinstance(value.get("int"), int):
        return int(value.get("int"))
    raise TypeError(f"expected int for {hint}, got {type(value).__name__}")


def _extract_signal_defs_from_gil_payload_root(payload_root: Mapping[str, Any]) -> List[GilSignalDef]:
    section10 = payload_root.get("10")
    section10 = _ensure_mapping(section10, hint="payload_root['10']")
    section5 = section10.get("5")
    section5 = _ensure_mapping(section5, hint="payload_root['10']['5']")
    signal_list = section5.get("3")
    signal_list = _ensure_list_or_single_mapping(signal_list, hint="payload_root['10']['5']['3']")

    out: List[GilSignalDef] = []
    for idx, entry in enumerate(signal_list):
        if not isinstance(entry, Mapping):
            continue
        entry_dict = _ensure_mapping(entry, hint=f"signal_entry[{idx}]")
        name = entry_dict.get("3")
        if not isinstance(name, str):
            continue
        signal_name = str(name).strip()
        if signal_name == "":
            continue

        send_meta = _ensure_mapping(entry_dict.get("1"), hint=f"signal_entry[{idx}]['1'](send_meta)")
        listen_meta = _ensure_mapping(entry_dict.get("2"), hint=f"signal_entry[{idx}]['2'](listen_meta)")
        server_meta = _ensure_mapping(entry_dict.get("7"), hint=f"signal_entry[{idx}]['7'](server_send_meta)")

        send_id = _extract_int(send_meta.get("5"), hint=f"signal_entry[{idx}].send_meta.5")
        listen_id = _extract_int(listen_meta.get("5"), hint=f"signal_entry[{idx}].listen_meta.5")
        server_id = _extract_int(server_meta.get("5"), hint=f"signal_entry[{idx}].server_send_meta.5")

        # params: entry['4'] can be list or scalar dict
        raw_params = entry_dict.get("4")
        params_list: List[Mapping[str, Any]] = []
        if isinstance(raw_params, list):
            params_list = [p for p in raw_params if isinstance(p, Mapping)]
        elif isinstance(raw_params, Mapping):
            params_list = [raw_params]

        send_param_port_indices: List[int] = []
        for pidx, p in enumerate(params_list):
            # send port index is stored at key '4' (int) in signal entry param spec
            port_index = p.get("4")
            if isinstance(port_index, int):
                send_param_port_indices.append(int(port_index))
            elif isinstance(port_index, Mapping) and isinstance(port_index.get("int"), int):
                send_param_port_indices.append(int(port_index.get("int")))
            else:
                raise TypeError(f"invalid signal param send port index: signal={signal_name!r} param_index={pidx} value={port_index!r}")

        # infer signal-name port index for send node:
        # - best effort: if has params, the signal-name port usually equals (min(param_port) - 1)
        # - if no params, keep None (caller may still rely on source_ref to disambiguate)
        send_signal_name_port_index: int | None = None
        if send_param_port_indices:
            send_signal_name_port_index = int(min(send_param_port_indices) - 1)

        out.append(
            GilSignalDef(
                signal_name=str(signal_name),
                send_node_def_id_int=int(send_id),
                listen_node_def_id_int=int(listen_id),
                server_send_node_def_id_int=int(server_id),
                send_signal_name_port_index_int=send_signal_name_port_index,
                send_param_port_indices_int=list(send_param_port_indices),
            )
        )
    return out


def load_signal_send_node_def_id_by_signal_name_from_gil(*, gil_file_path: Path) -> Dict[str, int]:
    """
    从真源 `.gil` 中读取信号定义表，构建 `signal_name -> send_node_def_id_int` 映射。

    用途：
    - 导出 `.gia` 时为 Send_Signal 节点写入 PinSignature.source_ref（Kind=5），避免导入后“信号名串号”。
    """
    gil_path = Path(gil_file_path).resolve()
    if not gil_path.is_file():
        raise FileNotFoundError(str(gil_path))

    raw_dump_object = load_gil_payload_as_dump_json_object(
        gil_path,
        max_depth=32,
        prefer_raw_hex_for_utf8=False,
    )
    raw_dump_object = _ensure_dict(raw_dump_object, hint="dump_json_root")
    payload_root = raw_dump_object.get("4")
    payload_root = _ensure_mapping(payload_root, hint="dump_json_root['4'](payload_root)")

    defs = _extract_signal_defs_from_gil_payload_root(payload_root)
    mapping: Dict[str, int] = {}
    for d in defs:
        key = str(d.signal_name).strip()
        if key == "":
            continue
        if key in mapping and int(mapping[key]) != int(d.send_node_def_id_int):
            raise ValueError(f"重复 signal_name 且 send_node_def_id 不一致：{key!r} {mapping[key]} vs {d.send_node_def_id_int}")
        mapping[key] = int(d.send_node_def_id_int)
    return mapping


def load_signal_send_ports_by_signal_name_from_gil(*, gil_file_path: Path) -> tuple[Dict[str, int], Dict[str, int], Dict[str, List[int]]]:
    """
    从 `.gil` 的信号表读取：
    - signal_name -> send_node_def_id_int
    - signal_name -> send_signal_name_port_index_int（可能为 None 则不包含在 dict）
    - signal_name -> send_param_port_indices_int（按参数顺序）
    """
    defs = _extract_signal_defs_from_gil_payload_root(
        _ensure_mapping(
            _ensure_dict(
                load_gil_payload_as_dump_json_object(Path(gil_file_path).resolve(), max_depth=32, prefer_raw_hex_for_utf8=False),
                hint="dump_json_root",
            ).get("4"),
            hint="payload_root",
        )
    )
    send_id_by_name: Dict[str, int] = {}
    name_port_by_name: Dict[str, int] = {}
    param_ports_by_name: Dict[str, List[int]] = {}
    for d in defs:
        send_id_by_name[str(d.signal_name)] = int(d.send_node_def_id_int)
        if isinstance(d.send_signal_name_port_index_int, int):
            name_port_by_name[str(d.signal_name)] = int(d.send_signal_name_port_index_int)
        param_ports_by_name[str(d.signal_name)] = list(d.send_param_port_indices_int)
    return send_id_by_name, name_port_by_name, param_ports_by_name

