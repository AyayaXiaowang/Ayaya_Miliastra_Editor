from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .claude_files import _ensure_claude_for_directory
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file


# 约定：信号参数类型与节点图 VarType 复用同一套 type_id（与结构体字段类型一致）。
_TYPE_ID_TO_PARAM_TYPE: Dict[int, str] = {
    1: "实体",
    2: "GUID",
    3: "整数",
    4: "布尔值",
    5: "浮点数",
    6: "字符串",
    7: "GUID列表",
    8: "整数列表",
    9: "布尔值列表",
    10: "浮点数列表",
    11: "字符串列表",
    12: "三维向量",
    13: "实体列表",
    15: "三维向量列表",
    17: "阵营",
    20: "配置ID",
    21: "元件ID",
    22: "配置ID列表",
    23: "元件ID列表",
    24: "阵营列表",
    25: "结构体",
    26: "结构体列表",
    27: "字典",
}


def _decode_base64_bytes_without_padding(base64_text: str) -> bytes:
    cleaned_text = str(base64_text or "").strip()
    if cleaned_text == "":
        return b""
    padding = "=" * ((4 - (len(cleaned_text) % 4)) % 4)
    return base64.b64decode(cleaned_text + padding)


def _extract_int_field(decoded: Mapping[str, Any], field_key: str) -> int:
    node = decoded.get(field_key)
    if isinstance(node, int):
        return int(node)
    if not isinstance(node, Mapping):
        raise ValueError(f"expected {field_key} to be dict, got: {type(node).__name__}")
    value = node.get("int")
    if not isinstance(value, int):
        raise ValueError(f"expected {field_key}.int to be int, got: {value!r}")
    return int(value)


def _extract_optional_int_field(decoded: Mapping[str, Any], field_key: str) -> int | None:
    node = decoded.get(field_key)
    if node is None:
        return None
    if isinstance(node, int):
        return int(node)
    if not isinstance(node, Mapping):
        return None
    value = node.get("int")
    if not isinstance(value, int):
        return None
    return int(value)


def _infer_missing_send_to_server_port_index(*, send_port_index_int: int, listen_port_index_int: int) -> int:
    """
    兼容历史坏数据：部分信号参数定义缺失 field_6（send_to_server 端口）。
    这类样本通常仍满足 send/listen 连续分配，故可按旧约定推断第三个端口。
    """
    candidate_from_listen = int(listen_port_index_int) + 1
    candidate_from_send = int(send_port_index_int) + 2
    if int(candidate_from_listen) == int(candidate_from_send):
        return int(candidate_from_listen)
    return int(max(candidate_from_listen, candidate_from_send))


def _extract_text_from_length_delimited_node(node: Any) -> str:
    """
    decode_gil 的 length-delimited 字段通常形如：
    - {raw_hex: "...", utf8: "..."}（utf8 可能因环境编码被替换，这里优先 raw_hex 自解码）
    """
    if isinstance(node, Mapping):
        raw_hex = node.get("raw_hex")
        if isinstance(raw_hex, str) and raw_hex != "":
            return bytes.fromhex(raw_hex).decode("utf-8")
        utf8_value = node.get("utf8")
        if isinstance(utf8_value, str) and utf8_value.strip() != "":
            return utf8_value.strip()
    return ""


def _extract_node_def_id_from_pyugc_meta(meta_object: Any) -> int:
    if not isinstance(meta_object, Mapping):
        raise ValueError(f"expected meta dict, got: {type(meta_object).__name__}")
    node_def_id_value = meta_object.get("5@int")
    if not isinstance(node_def_id_value, int):
        raise ValueError(f"expected meta['5@int'] int, got: {node_def_id_value!r}")
    return int(node_def_id_value)


def _walk_with_path(python_object: Any, path_parts: Optional[List[str]] = None) -> List[Tuple[List[str], Any]]:
    """
    返回 (path_parts, value) 扁平列表，供“按结构模式”定位信号列表。
    """
    collected: List[Tuple[List[str], Any]] = []
    current_path_parts = path_parts if path_parts is not None else []

    if isinstance(python_object, dict):
        collected.append((current_path_parts, python_object))
        for key, child in python_object.items():
            collected.extend(_walk_with_path(child, current_path_parts + [str(key)]))
        return collected

    if isinstance(python_object, list):
        collected.append((current_path_parts, python_object))
        for index, child in enumerate(python_object):
            collected.extend(_walk_with_path(child, current_path_parts + [f"[{index}]"]))
        return collected

    collected.append((current_path_parts, python_object))
    return collected


def _try_find_signal_entries(pyugc_object: Any) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    优先走固定路径：root4/10/5/3
    若不存在则退化为结构扫描（按字段形态匹配）。
    """
    if isinstance(pyugc_object, Mapping):
        root4 = pyugc_object.get("4")
        if isinstance(root4, Mapping):
            section10 = root4.get("10")
            if isinstance(section10, Mapping):
                section5 = section10.get("5")
                if isinstance(section5, Mapping):
                    signal_list = section5.get("3")
                    if isinstance(signal_list, list):
                        entries = [item for item in signal_list if isinstance(item, dict)]
                        if entries:
                            return "4/10/5/3", entries

    best_path = ""
    best_entries: List[Dict[str, Any]] = []
    for path_parts, value in _walk_with_path(pyugc_object):
        if not isinstance(value, list) or not value:
            continue
        if not all(isinstance(item, dict) for item in value):
            continue
        # 信号条目形态（样本）：{1:meta_send, 2:meta_listen, 3@string:name, 6@int:index, 7@data:meta_server}
        required_keys = {"1", "2", "3@string", "6@int", "7@data"}
        if not all(required_keys.issubset(set(item.keys())) for item in value):
            continue
        if len(value) > len(best_entries):
            best_path = "/".join(path_parts)
            best_entries = [dict(item) for item in value]

    if best_entries:
        return best_path, best_entries
    return None


def _normalize_param_base64_list(signal_entry: Mapping[str, Any]) -> List[str]:
    """
    pyugc dump 中 repeated bytes 字段在“只有 1 个元素”时可能表现为：
    - 4@data: "<base64>"（标量）
    多个元素时则为：
    - 4: ["<base64>", ...]
    """
    result: List[str] = []

    value = signal_entry.get("4")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip() != "":
                result.append(item.strip())
        return result
    if isinstance(value, str) and value.strip() != "":
        return [value.strip()]

    single = signal_entry.get("4@data")
    if isinstance(single, str) and single.strip() != "":
        return [single.strip()]

    return []


def _type_id_to_param_type_name(type_id_int: int) -> str:
    name = _TYPE_ID_TO_PARAM_TYPE.get(int(type_id_int))
    return str(name) if isinstance(name, str) else ""


def _parse_signal_param_definition_from_base64(base64_text: str) -> Dict[str, Any]:
    decoded_bytes = _decode_base64_bytes_without_padding(base64_text)
    decoded = decode_bytes_to_python(decoded_bytes)
    if not isinstance(decoded, Mapping):
        raise ValueError("signal param decoded object is not dict")

    param_name = _extract_text_from_length_delimited_node(decoded.get("field_1"))
    type_id_int = _extract_int_field(decoded, "field_2")
    order_int = _extract_int_field(decoded, "field_3")
    send_port_index_int = _extract_int_field(decoded, "field_4")
    listen_port_index_int = _extract_int_field(decoded, "field_5")
    send_to_server_port_index_int = _extract_optional_int_field(decoded, "field_6")
    inferred_send_to_server_port_index = False
    if not isinstance(send_to_server_port_index_int, int):
        send_to_server_port_index_int = _infer_missing_send_to_server_port_index(
            send_port_index_int=int(send_port_index_int),
            listen_port_index_int=int(listen_port_index_int),
        )
        inferred_send_to_server_port_index = True

    return {
        "param_name": param_name,
        "type_id": int(type_id_int),
        "type_name": _type_id_to_param_type_name(int(type_id_int)),
        "order_int": int(order_int),
        "port_index_by_role": {
            "send": int(send_port_index_int),
            "listen": int(listen_port_index_int),
            "send_to_server": int(send_to_server_port_index_int),
        },
        "send_to_server_port_index_inferred": bool(inferred_send_to_server_port_index),
        "raw": {
            "base64": str(base64_text),
            "byte_size": len(decoded_bytes),
            "decoded": decoded,
        },
    }


def _parse_node_def_meta_from_base64(base64_text: str) -> Dict[str, Any]:
    decoded_bytes = _decode_base64_bytes_without_padding(base64_text)
    decoded = decode_bytes_to_python(decoded_bytes)
    if not isinstance(decoded, Mapping):
        raise ValueError("signal node meta decoded object is not dict")

    return {
        "base64": str(base64_text),
        "byte_size": len(decoded_bytes),
        "decoded": decoded,
        "node_def_id_int": _extract_int_field(decoded, "field_5"),
    }


def _parse_signal_entry(signal_entry: Mapping[str, Any], *, source_pyugc_path: str) -> Dict[str, Any]:
    signal_name = str(signal_entry.get("3@string") or "").strip()
    if signal_name == "":
        raise ValueError("signal entry missing 3@string name")

    signal_index_value = signal_entry.get("6@int")
    if not isinstance(signal_index_value, int):
        raise ValueError(f"signal entry missing 6@int: {signal_index_value!r}")
    signal_index_int = int(signal_index_value)

    send_meta = signal_entry.get("1")
    listen_meta = signal_entry.get("2")
    server_meta_b64 = signal_entry.get("7@data")
    if not isinstance(server_meta_b64, str) or server_meta_b64.strip() == "":
        raise ValueError("signal entry missing 7@data base64")

    send_node_def_id_int = _extract_node_def_id_from_pyugc_meta(send_meta)
    listen_node_def_id_int = _extract_node_def_id_from_pyugc_meta(listen_meta)
    send_to_server_meta = _parse_node_def_meta_from_base64(server_meta_b64.strip())
    send_to_server_node_def_id_int = int(send_to_server_meta["node_def_id_int"])

    params_base64 = _normalize_param_base64_list(signal_entry)
    params: List[Dict[str, Any]] = []
    for param_index, param_b64 in enumerate(params_base64):
        parsed_param = _parse_signal_param_definition_from_base64(param_b64)
        parsed_param["param_index"] = int(param_index)
        params.append(parsed_param)

    return {
        "schema_version": 1,
        "signal_index_int": signal_index_int,
        "signal_name": signal_name,
        "node_def_ids": {
            "send": int(send_node_def_id_int),
            "listen": int(listen_node_def_id_int),
            "send_to_server": int(send_to_server_node_def_id_int),
        },
        "params": params,
        "source_pyugc_path": source_pyugc_path,
        "raw": {
            "signal_entry_object": dict(signal_entry),
            "server_node_def_meta": send_to_server_meta,
        },
    }


def _build_signal_resource_id(*, package_id: str, signal_index_int: int) -> str:
    return f"signal_{int(signal_index_int)}__{str(package_id)}"


def _write_signals_dir_claude(signals_dir: Path) -> None:
    _ensure_claude_for_directory(signals_dir, purpose="存放从 .gil/pyugc 中解析出的“信号定义”（含参数列表与关联节点定义ID）。")


def _export_signals_from_pyugc_dump(*, pyugc_object: Any, output_package_root: Path) -> Dict[str, Any]:
    """
    从 pyugc dump 提取信号定义并落盘到：
    - 管理配置/信号/signals_index.json
    - 管理配置/信号/signal_node_defs_index.json
    - 管理配置/信号/信号_<index>_<name>.json
    """
    signals_dir = output_package_root / "管理配置" / "信号"
    _ensure_directory(signals_dir)
    _write_signals_dir_claude(signals_dir)

    found = _try_find_signal_entries(pyugc_object)
    if found is None:
        _write_json_file(signals_dir / "signals_index.json", [])
        _write_json_file(signals_dir / "signal_node_defs_index.json", [])
        return {
            "signals_count": 0,
            "signals_index": "管理配置/信号/signals_index.json",
            "signal_node_defs_index": "管理配置/信号/signal_node_defs_index.json",
            "source_pyugc_path": None,
        }

    source_list_path, signal_entries = found

    package_id = output_package_root.name
    signals_index: List[Dict[str, Any]] = []
    node_defs_index: List[Dict[str, Any]] = []

    for entry_index, entry in enumerate(signal_entries):
        signal_payload = _parse_signal_entry(entry, source_pyugc_path=f"{source_list_path}/[{entry_index}]")

        signal_index_int = int(signal_payload["signal_index_int"])
        signal_name = str(signal_payload["signal_name"])
        resource_id = _build_signal_resource_id(package_id=package_id, signal_index_int=signal_index_int)

        file_stem = _sanitize_filename(f"信号_{signal_index_int}_{signal_name}", max_length=120)
        output_path = signals_dir / f"{file_stem}.json"
        _write_json_file(output_path, signal_payload)

        rel_output = str(output_path.relative_to(output_package_root)).replace("\\", "/")
        node_def_ids = signal_payload.get("node_def_ids", {})
        signals_index.append(
            {
                "signal_id": resource_id,
                "name": signal_name,
                "signal_index_int": signal_index_int,
                "node_def_ids": dict(node_def_ids) if isinstance(node_def_ids, Mapping) else {},
                "params_count": len(signal_payload.get("params", []) if isinstance(signal_payload.get("params"), list) else []),
                "output": rel_output,
            }
        )

        if isinstance(node_def_ids, Mapping):
            for role in ["send", "listen", "send_to_server"]:
                node_def_id_value = node_def_ids.get(role)
                if not isinstance(node_def_id_value, int):
                    continue
                node_defs_index.append(
                    {
                        "node_def_id_int": int(node_def_id_value),
                        "role": str(role),
                        "signal_id": resource_id,
                        "signal_index_int": signal_index_int,
                        "signal_name": signal_name,
                        "signal_output": rel_output,
                    }
                )

    signals_index.sort(key=lambda it: int(it.get("signal_index_int", 0)))
    node_defs_index.sort(key=lambda it: int(it.get("node_def_id_int", 0)))

    _write_json_file(signals_dir / "signals_index.json", signals_index)
    _write_json_file(signals_dir / "signal_node_defs_index.json", node_defs_index)

    return {
        "signals_count": len(signals_index),
        "signals_index": "管理配置/信号/signals_index.json",
        "signal_node_defs_index": "管理配置/信号/signal_node_defs_index.json",
        "source_pyugc_path": source_list_path,
    }


