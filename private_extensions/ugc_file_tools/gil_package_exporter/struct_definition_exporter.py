from __future__ import annotations

import base64
import json
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .claude_files import _ensure_claude_for_directory
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file, _write_text_file


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

_TYPE_ID_TO_DICT_TYPE: Dict[int, str] = {
    1: "Entity",
    2: "Guid",
    3: "Int32",
    4: "Bool",
    5: "Float",
    6: "String",
    12: "Vector3",
    17: "Camp",
    20: "ConfigId",
    21: "ComponentId",
}


_STRUCT_ID_DECL_PATTERN = re.compile(r"^\s*STRUCT_ID\s*=\s*['\"](\d+)['\"]\s*$", re.MULTILINE)


def _collect_existing_struct_id_texts_from_resource_library(output_package_root: Path) -> set[str]:
    """
    Graph_Generater 校验会加载资源库中的结构体定义；STRUCT_ID 在全库范围内必须唯一。

    若当前项目存档再次声明已存在于资源库其他位置的 STRUCT_ID，会触发“重复的结构体 ID”错误。
    这里通过扫描：
    - `assets/资源库/共享/管理配置/结构体定义/**.py`
    - `assets/资源库/项目存档/*/管理配置/结构体定义/**.py`（排除当前输出项目）
    提前识别并跳过写入。
    """
    # output_package_root: .../Graph_Generater/assets/资源库/项目存档/<package_id>
    resources_root = output_package_root.parent.parent
    shared_struct_root = resources_root / "共享" / "管理配置" / "结构体定义"
    project_archive_root = resources_root / "项目存档"

    existing: set[str] = set()

    def scan_struct_root(struct_root: Path) -> None:
        if not struct_root.is_dir():
            return
        for py_file in struct_root.rglob("*.py"):
            if not py_file.is_file():
                continue
            if "__pycache__" in py_file.parts:
                continue
            if py_file.name.startswith("_"):
                continue
            content = py_file.read_text(encoding="utf-8")
            match = _STRUCT_ID_DECL_PATTERN.search(content)
            if match is not None:
                existing.add(match.group(1))

    scan_struct_root(shared_struct_root)

    if project_archive_root.is_dir():
        for package_dir in project_archive_root.iterdir():
            if not package_dir.is_dir():
                continue
            if package_dir.resolve() == output_package_root.resolve():
                continue
            scan_struct_root(package_dir / "管理配置" / "结构体定义")

    return existing


def _read_varint(data: bytes, start_offset: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    offset = start_offset
    while True:
        if offset >= len(data):
            raise ValueError("varint truncated")
        byte_value = data[offset]
        offset += 1
        result |= (byte_value & 0x7F) << shift
        if (byte_value & 0x80) == 0:
            return result, offset
        shift += 7
        if shift >= 64:
            raise ValueError("varint too large")


def _decode_packed_varints(data: bytes) -> List[int]:
    values: List[int] = []
    offset = 0
    while offset < len(data):
        value, offset = _read_varint(data, offset)
        values.append(int(value))
    return values


def _extract_int(node: object) -> int:
    if not isinstance(node, Mapping):
        raise ValueError(f"expected int node dict, got: {type(node).__name__}")
    value = node.get("int")
    if not isinstance(value, int):
        raise ValueError(f"expected int, got: {value!r}")
    return int(value)


def _extract_utf8(node: object) -> str:
    if not isinstance(node, Mapping):
        return ""
    value = node.get("utf8")
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_raw_hex_bytes(node: object) -> bytes:
    if not isinstance(node, Mapping):
        return b""
    raw_hex = node.get("raw_hex")
    if not isinstance(raw_hex, str):
        return b""
    return bytes.fromhex(raw_hex)


def _format_float(value: float) -> str:
    # 使用 float32 的源数据，避免出现 1.230000019 这类噪声。
    rounded = round(float(value), 6)
    text = f"{rounded:.6f}".rstrip("0").rstrip(".")
    if text == "":
        return "0"
    return text


def _format_vector3(x: float, y: float, z: float) -> str:
    return f"{_format_float(x)},{_format_float(y)},{_format_float(z)}"


def _parse_vector3_from_raw_bytes(raw_bytes: bytes) -> str:
    """
    Vector3 在样本中存在多种常见编码：
    - 12 bytes：3 个 float32（x,y,z）直接 packed
    - 24 bytes：每个 float32 后带 4 bytes padding（与部分 float 列表一致）
    - 16 bytes：12 bytes 数据 + 4 bytes padding（见少量样本）
    - 空 bytes：等价于默认值 0,0,0
    """
    if raw_bytes == b"":
        return "0,0,0"
    if len(raw_bytes) == 12:
        x, y, z = struct.unpack("<fff", raw_bytes)
        return _format_vector3(float(x), float(y), float(z))
    if len(raw_bytes) == 24:
        x = struct.unpack("<f", raw_bytes[0:4])[0]
        y = struct.unpack("<f", raw_bytes[8:12])[0]
        z = struct.unpack("<f", raw_bytes[16:20])[0]
        return _format_vector3(float(x), float(y), float(z))
    if len(raw_bytes) == 16:
        x, y, z = struct.unpack("<fff", raw_bytes[:12])
        return _format_vector3(float(x), float(y), float(z))
    raise ValueError(f"unexpected vector3 byte size: {len(raw_bytes)}")


def _type_id_to_param_type(type_id: int) -> str:
    param_type = _TYPE_ID_TO_PARAM_TYPE.get(int(type_id))
    if not isinstance(param_type, str) or not param_type:
        raise ValueError(f"unsupported struct field type_id: {type_id}")
    return param_type


def _type_id_to_dict_type(type_id: int) -> str:
    dict_type = _TYPE_ID_TO_DICT_TYPE.get(int(type_id))
    if not isinstance(dict_type, str) or not dict_type:
        raise ValueError(f"unsupported dict inner type_id: {type_id}")
    return dict_type


def _parse_bool_from_raw_hex(node: Mapping[str, object]) -> bool:
    # 兼容两种常见编码：
    # - raw_hex packed varint："" -> False, "01" -> True（用于布尔列表/部分场景）
    # - message.field_1 varint：{message:{field_1:int}}（用于“布尔值字段”(type_id=4) 与 dict<bool> value 的 True）
    message = node.get("message")
    if isinstance(message, Mapping):
        value = _extract_int(message.get("field_1"))
        return bool(int(value) != 0)
    raw_bytes = _extract_raw_hex_bytes(node)
    if raw_bytes == b"":
        return False
    values = _decode_packed_varints(raw_bytes)
    if not values:
        return False
    return bool(int(values[0]) != 0)


def _parse_float_from_message_or_raw(node: Mapping[str, object]) -> float:
    """
    兼容两种常见编码：
    - message.field_1.fixed32_float
    - raw_hex = packed bytes（4 bytes float32 或 8 bytes: float32 + padding）
    """
    message = node.get("message")
    if isinstance(message, Mapping):
        inner_value = message.get("field_1")
        if isinstance(inner_value, Mapping) and isinstance(inner_value.get("fixed32_float"), float):
            return float(inner_value["fixed32_float"])

    raw_bytes = _extract_raw_hex_bytes(node)
    if raw_bytes == b"":
        return 0.0
    if len(raw_bytes) == 4:
        return float(struct.unpack("<f", raw_bytes)[0])
    if len(raw_bytes) == 8:
        return float(struct.unpack("<f", raw_bytes[:4])[0])
    raise ValueError(f"unexpected float byte size: {len(raw_bytes)}")


def _parse_vector3_from_message(node: Mapping[str, object]) -> str:
    """
    兼容两种常见编码：
    - message.field_1.message.field_1/2/3.fixed32_float
    - message.field_1.raw_hex（可为空 bytes，表示 0,0,0）
    """
    message = node.get("message")
    if isinstance(message, Mapping):
        field_1 = message.get("field_1")
        if isinstance(field_1, Mapping):
            vec_message = field_1.get("message")
            if isinstance(vec_message, Mapping):
                x = vec_message.get("field_1", {}).get("fixed32_float")
                y = vec_message.get("field_2", {}).get("fixed32_float")
                z = vec_message.get("field_3", {}).get("fixed32_float")
                if not isinstance(x, float) or not isinstance(y, float) or not isinstance(z, float):
                    raise ValueError("vector3 components missing")
                return _format_vector3(float(x), float(y), float(z))

            raw_bytes = _extract_raw_hex_bytes(field_1)
            return _parse_vector3_from_raw_bytes(raw_bytes)

    raw_bytes = _extract_raw_hex_bytes(node)
    return _parse_vector3_from_raw_bytes(raw_bytes)


def _parse_dict_scalar_value(type_id: int, node: object) -> object:
    """
    解析字典 key/value 节点（field_16 / field_14），按 key_type_id/value_type_id 的标量类型解析为导出值。
    目前覆盖 `_TYPE_ID_TO_DICT_TYPE` 中出现的标量类型。
    """
    if not isinstance(node, Mapping):
        # 字典节点缺失时按默认值处理
        if int(type_id) == 4:
            return "False"
        if int(type_id) == 6:
            return ""
        if int(type_id) == 5:
            return "0"
        if int(type_id) == 12:
            return "0,0,0"
        return "0"

    if int(type_id) == 6:
        return _extract_utf8(node)
    if int(type_id) == 4:
        return "True" if _parse_bool_from_raw_hex(node) else "False"
    if int(type_id) == 5:
        return _format_float(_parse_float_from_message_or_raw(node))
    if int(type_id) == 12:
        return _parse_vector3_from_message(node)

    if int(type_id) in {1, 2, 3, 17, 20, 21}:
        return str(int(_parse_int_from_message_or_raw(node)))

    raise ValueError(f"unsupported dict inner type_id: {type_id}")

def _parse_int_from_message_or_raw(node: Mapping[str, object]) -> int:
    if "message" in node:
        message = node.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("expected message dict")
        return _extract_int(message.get("field_1"))

    raw_bytes = _extract_raw_hex_bytes(node)
    if raw_bytes == b"":
        return 0
    values = _decode_packed_varints(raw_bytes)
    if not values:
        return 0
    return int(values[0])


def _parse_float32_list_from_raw_hex(raw_hex_node: Mapping[str, object]) -> List[float]:
    raw_bytes = _extract_raw_hex_bytes(raw_hex_node)
    if raw_bytes == b"":
        return []

    floats: List[float] = []
    if len(raw_bytes) % 8 == 0:
        for offset in range(0, len(raw_bytes), 8):
            chunk = raw_bytes[offset : offset + 8]
            float32_value = struct.unpack("<f", chunk[:4])[0]
            floats.append(float(float32_value))
        return floats

    if len(raw_bytes) % 4 == 0:
        for offset in range(0, len(raw_bytes), 4):
            chunk = raw_bytes[offset : offset + 4]
            float32_value = struct.unpack("<f", chunk)[0]
            floats.append(float(float32_value))
        return floats

    raise ValueError(f"unexpected float list byte size: {len(raw_bytes)}")


def _parse_string_list_from_raw_hex(raw_hex_node: Mapping[str, object]) -> List[str]:
    raw_bytes = _extract_raw_hex_bytes(raw_hex_node)
    if raw_bytes == b"":
        return []
    decoded = decode_bytes_to_python(raw_bytes)
    if not isinstance(decoded, Mapping):
        raise ValueError("string list payload is not a dict")
    field1 = decoded.get("field_1")
    if not isinstance(field1, list):
        return []
    results: List[str] = []
    for entry in field1:
        text = _extract_utf8(entry)
        results.append(text)
    return results


def _iter_struct_field_messages(field_3_value: object) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []

    if isinstance(field_3_value, Mapping) and "message" in field_3_value:
        candidate = field_3_value.get("message")
        if isinstance(candidate, dict):
            results.append(candidate)
        return results

    if isinstance(field_3_value, list):
        for entry in field_3_value:
            if not isinstance(entry, Mapping):
                continue
            message_value = entry.get("message")
            if isinstance(message_value, dict):
                results.append(message_value)
                continue

            # 某些字段（如字符串列表/浮点数列表）会被 decode_gil 的“文本优先”策略
            # 误判为 raw_hex+utf8；这里对 raw_hex 再解一次，恢复为 message。
            raw_hex_value = entry.get("raw_hex")
            if isinstance(raw_hex_value, str) and raw_hex_value:
                decoded = decode_bytes_to_python(bytes.fromhex(raw_hex_value))
                if isinstance(decoded, dict):
                    results.append(decoded)
                    continue
    return results


def _build_default_value_node(
    *,
    type_id: int,
    param_type: str,
    field_msg: Mapping[str, object],
    struct_id_mapping: Mapping[int, str],
) -> Dict[str, object]:
    inner: Optional[Mapping[str, object]] = None
    field_3_node = field_msg.get("field_3")
    if isinstance(field_3_node, Mapping):
        message_value = field_3_node.get("message")
        if isinstance(message_value, Mapping):
            inner = message_value
        else:
            # decode_gil 的“文本优先”策略可能把本应是 nested message 的 bytes 误判为 raw_hex；
            # 这里对 raw_hex 再解一次，恢复为 message 结构。
            raw_hex_value = field_3_node.get("raw_hex")
            if isinstance(raw_hex_value, str) and raw_hex_value:
                decoded = decode_bytes_to_python(bytes.fromhex(raw_hex_value))
                if isinstance(decoded, Mapping):
                    inner = decoded
    if not isinstance(inner, Mapping):
        return {"param_type": param_type, "value": ""}

    type_keys = [k for k in inner.keys() if k not in {"field_1", "field_2"}]
    if not type_keys:
        return {"param_type": param_type, "value": ""}
    if len(type_keys) != 1:
        raise ValueError(f"unexpected inner keys for field: {sorted(inner.keys())}")
    type_value_container = inner[type_keys[0]]
    if not isinstance(type_value_container, Mapping):
        raise ValueError("unexpected type_value_container shape")

    # --------- 标量类型
    if type_id == 1:
        # 实体：空 raw_hex 表示“无初始值”
        return {"param_type": param_type, "value": ""}

    if type_id in {2, 3, 17}:
        # GUID / 整数 / 阵营：均为 varint
        message = type_value_container.get("message")
        if isinstance(message, Mapping):
            value = _extract_int(message.get("field_1"))
            return {"param_type": param_type, "value": str(int(value))}
        value = _parse_int_from_message_or_raw(type_value_container)
        return {"param_type": param_type, "value": str(int(value))}

    if type_id in {20, 21}:
        # 配置ID / 元件ID：有两种常见编码
        # - message.field_1 是空 raw_hex（表示 0）
        # - message.field_1 是 varint（少见）
        message = type_value_container.get("message")
        if isinstance(message, Mapping):
            field_1 = message.get("field_1")
            if isinstance(field_1, Mapping) and isinstance(field_1.get("int"), int):
                return {"param_type": param_type, "value": str(int(field_1["int"]))}
            if isinstance(field_1, Mapping) and isinstance(field_1.get("raw_hex"), str):
                raw_bytes = bytes.fromhex(str(field_1["raw_hex"]))
                if raw_bytes == b"":
                    return {"param_type": param_type, "value": "0"}
                values = _decode_packed_varints(raw_bytes)
                value = int(values[0]) if values else 0
                return {"param_type": param_type, "value": str(value)}
            return {"param_type": param_type, "value": "0"}

        raw_bytes = _extract_raw_hex_bytes(type_value_container)
        if raw_bytes == b"":
            return {"param_type": param_type, "value": "0"}
        values = _decode_packed_varints(raw_bytes)
        value = int(values[0]) if values else 0
        return {"param_type": param_type, "value": str(value)}

    if type_id == 4:
        return {"param_type": param_type, "value": "True" if _parse_bool_from_raw_hex(type_value_container) else "False"}

    if type_id == 5:
        # 兼容两种常见编码：
        # - 直接 fixed32：{fixed32_float: ...}
        # - message.field_1.fixed32_float：{message: {field_1: {fixed32_float: ...}}}
        direct_float = type_value_container.get("fixed32_float")
        if isinstance(direct_float, (int, float)):
            return {"param_type": param_type, "value": _format_float(float(direct_float))}

        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            return {"param_type": param_type, "value": ""}
        inner_value = message.get("field_1")
        if not isinstance(inner_value, Mapping):
            return {"param_type": param_type, "value": ""}
        float_value = inner_value.get("fixed32_float")
        if not isinstance(float_value, (int, float)):
            return {"param_type": param_type, "value": ""}
        return {"param_type": param_type, "value": _format_float(float(float_value))}

    if type_id == 6:
        text_value = _extract_utf8(type_value_container)
        return {"param_type": param_type, "value": text_value}

    if type_id == 12:
        return {"param_type": param_type, "value": _parse_vector3_from_message(type_value_container)}

    # --------- 列表类型
    if type_id in {7, 8, 9, 24}:
        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("packed list value missing message wrapper")
        raw_node = message.get("field_1")
        if not isinstance(raw_node, Mapping):
            raise ValueError("packed list value missing field_1")
        raw_bytes = _extract_raw_hex_bytes(raw_node)
        values = _decode_packed_varints(raw_bytes) if raw_bytes else []
        if type_id == 9:
            return {"param_type": param_type, "value": ["True" if int(v) != 0 else "False" for v in values]}
        return {"param_type": param_type, "value": [str(int(v)) for v in values]}

    if type_id == 10:
        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("float list missing message wrapper")
        raw_node = message.get("field_1")
        if not isinstance(raw_node, Mapping):
            raise ValueError("float list missing field_1")
        float_values = _parse_float32_list_from_raw_hex(raw_node)
        return {"param_type": param_type, "value": [_format_float(v) for v in float_values]}

    if type_id == 11:
        return {"param_type": param_type, "value": _parse_string_list_from_raw_hex(type_value_container)}

    if type_id == 13:
        # 实体列表：当前已确认“无初始值”会落为一个难以解释的 00 00 形式；先按空列表处理。
        return {"param_type": param_type, "value": []}

    if type_id == 15:
        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("vector3 list missing message wrapper")
        items = message.get("field_1")
        if not isinstance(items, list):
            return {"param_type": param_type, "value": []}
        result: List[str] = []
        for entry in items:
            if not isinstance(entry, Mapping):
                continue
            vec_msg = entry.get("message")
            if not isinstance(vec_msg, Mapping):
                continue
            x = vec_msg.get("field_1", {}).get("fixed32_float")
            y = vec_msg.get("field_2", {}).get("fixed32_float")
            z = vec_msg.get("field_3", {}).get("fixed32_float")
            if not isinstance(x, float) or not isinstance(y, float) or not isinstance(z, float):
                continue
            result.append(_format_vector3(x, y, z))
        return {"param_type": param_type, "value": result}

    if type_id in {22, 23}:
        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("id list missing message wrapper")
        items = message.get("field_1")
        if not isinstance(items, list):
            return {"param_type": param_type, "value": []}
        values: List[str] = []
        for entry in items:
            if not isinstance(entry, Mapping):
                continue
            entry_msg = entry.get("message")
            if not isinstance(entry_msg, Mapping):
                continue
            # 经验：这类 list item 里数值放在 field_2.varint
            value_node = entry_msg.get("field_2")
            if isinstance(value_node, Mapping) and isinstance(value_node.get("int"), int):
                values.append(str(int(value_node["int"])))
        return {"param_type": param_type, "value": values}

    # --------- 结构体/字典
    if type_id == 25:
        # structId 来自字段类型声明（也可从 value_container.field_501 取）
        field_type_meta = field_msg.get("field_1", {}).get("message", {}).get("field_2", {}).get("message")
        referenced_id = None
        if isinstance(field_type_meta, Mapping):
            referenced_id = field_type_meta.get("field_2")
        struct_id_int = _extract_int(referenced_id) if referenced_id is not None else 0
        if struct_id_int <= 0:
            struct_id_int = _extract_int(type_value_container.get("message", {}).get("field_501"))
        struct_id_text = struct_id_mapping.get(int(struct_id_int), str(int(struct_id_int))) if struct_id_int > 0 else ""
        value_obj: Dict[str, object] = {"structId": struct_id_text, "type": "Struct", "value": []}

        # 结构体值在原始数据中通常带一个“引用链接 id”（便于 UI 跳转）；引擎侧不依赖，但保留可追溯信息
        ref_id_int: Optional[int] = None
        struct_value_msg = type_value_container.get("message")
        if isinstance(struct_value_msg, Mapping):
            field_502_msg = struct_value_msg.get("field_502", {}).get("message") if isinstance(struct_value_msg.get("field_502"), Mapping) else None
            if isinstance(field_502_msg, Mapping):
                ref_node = field_502_msg.get("field_4")
                if isinstance(ref_node, Mapping) and isinstance(ref_node.get("int"), int):
                    ref_id_int = int(ref_node["int"])
        if ref_id_int is not None:
            value_obj["metadata"] = {"ugc_ref_id_int": int(ref_id_int)}

        return {"param_type": param_type, "value": value_obj}

    if type_id == 26:
        field_type_meta = field_msg.get("field_1", {}).get("message", {}).get("field_2", {}).get("message")
        referenced_id = None
        if isinstance(field_type_meta, Mapping):
            referenced_id = field_type_meta.get("field_2")
        struct_id_int = _extract_int(referenced_id) if referenced_id is not None else 0
        struct_id_text = struct_id_mapping.get(int(struct_id_int), str(int(struct_id_int))) if struct_id_int > 0 else ""
        value_items: List[Dict[str, object]] = []
        list_msg = type_value_container.get("message")
        if isinstance(list_msg, Mapping):
            raw_items = list_msg.get("field_1")
            if isinstance(raw_items, list):
                for raw_item in raw_items:
                    if not isinstance(raw_item, Mapping):
                        continue
                    item_msg = raw_item.get("message")
                    if not isinstance(item_msg, Mapping):
                        continue

                    item_ref_id: Optional[int] = None
                    field_35_msg = item_msg.get("field_35", {}).get("message") if isinstance(item_msg.get("field_35"), Mapping) else None
                    if isinstance(field_35_msg, Mapping):
                        field_502_msg = field_35_msg.get("field_502", {}).get("message") if isinstance(field_35_msg.get("field_502"), Mapping) else None
                        if isinstance(field_502_msg, Mapping):
                            ref_node = field_502_msg.get("field_4")
                            if isinstance(ref_node, Mapping) and isinstance(ref_node.get("int"), int):
                                item_ref_id = int(ref_node["int"])

                    value_item: Dict[str, object] = {"type": "Struct", "structId": struct_id_text, "value": []}
                    if item_ref_id is not None:
                        value_item["metadata"] = {"ugc_ref_id_int": int(item_ref_id)}
                    value_items.append(value_item)

        return {"param_type": param_type, "value": {"structId": struct_id_text, "value": value_items}}

    if type_id == 27:
        message = type_value_container.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("dict value missing message wrapper")
        key_type_id = _extract_int(message.get("field_503"))
        value_type_id = _extract_int(message.get("field_504"))
        key_nodes = message.get("field_501")
        value_nodes = message.get("field_502")
        if isinstance(key_nodes, Mapping):
            key_nodes = [key_nodes]
        if isinstance(value_nodes, Mapping):
            value_nodes = [value_nodes]
        if not isinstance(key_nodes, list) or not isinstance(value_nodes, list):
            return {
                "param_type": param_type,
                "value": {
                    "type": "Dict",
                    "key_type": _type_id_to_dict_type(key_type_id),
                    "value_type": _type_id_to_dict_type(value_type_id),
                    "value": [],
                },
            }
        if len(key_nodes) != len(value_nodes):
            raise ValueError("dict keys/values length mismatch")

        dict_entries: List[Dict[str, object]] = []
        for key_item, value_item in zip(key_nodes, value_nodes):
            if not isinstance(key_item, Mapping) or not isinstance(value_item, Mapping):
                continue
            key_msg = key_item.get("message")
            value_msg = value_item.get("message")
            if not isinstance(key_msg, Mapping) or not isinstance(value_msg, Mapping):
                continue

            key_value = _parse_dict_scalar_value(key_type_id, key_msg.get("field_16"))
            value_value = _parse_dict_scalar_value(value_type_id, value_msg.get("field_14"))

            dict_entries.append(
                {
                    "key": {"param_type": _type_id_to_param_type(key_type_id), "value": key_value},
                    "value": {"param_type": _type_id_to_param_type(value_type_id), "value": value_value},
                }
            )

        return {
            "param_type": param_type,
            "value": {
                "type": "Dict",
                "key_type": _type_id_to_dict_type(key_type_id),
                "value_type": _type_id_to_dict_type(value_type_id),
                "value": dict_entries,
            },
        }

    raise ValueError(f"unhandled field type_id: {type_id}")


def _parse_struct_definition_payload(
    struct_message: Mapping[str, object],
    *,
    struct_id_mapping: Mapping[int, str],
) -> Tuple[int, str, List[Dict[str, object]]]:
    struct_id_int = _extract_int(struct_message.get("field_1"))
    struct_name = _extract_utf8(struct_message.get("field_501"))
    field_3_value = struct_message.get("field_3")
    field_messages = _iter_struct_field_messages(field_3_value)

    fields: List[Dict[str, object]] = []
    for field_msg in field_messages:
        field_name = _extract_utf8(field_msg.get("field_501")) or _extract_utf8(field_msg.get("field_5"))
        field_no = _extract_int(field_msg.get("field_503"))
        type_meta = field_msg.get("field_1", {}).get("message") if isinstance(field_msg.get("field_1"), Mapping) else None
        if not isinstance(type_meta, Mapping):
            raise ValueError("field_1.message missing in field entry")
        type_id = _extract_int(type_meta.get("field_1"))
        param_type = _type_id_to_param_type(type_id)

        default_value_node = _build_default_value_node(
            type_id=type_id,
            param_type=param_type,
            field_msg=field_msg,
            struct_id_mapping=struct_id_mapping,
        )

        fields.append(
            {
                "_field_no": int(field_no),
                "field_name": field_name,
                "param_type": param_type,
                "default_value": default_value_node,
            }
        )

    fields.sort(key=lambda entry: int(entry.get("_field_no") or 0))
    for entry in fields:
        entry.pop("_field_no", None)
    return struct_id_int, struct_name, fields


def _build_struct_definition_py(
    *,
    struct_id_text: str,
    struct_type: str,
    struct_name: str,
    fields: Sequence[Mapping[str, object]],
) -> str:
    payload = {
        "type": "Struct",
        "struct_type": str(struct_type),
        "struct_name": struct_name,
        "fields": list(fields),
    }
    dumped_payload = json.dumps(payload, ensure_ascii=False, indent=4)
    dumped_payload = dumped_payload.replace("\n", "\n    ")
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from typing import Any, Dict",
            "",
            f"STRUCT_ID = {struct_id_text!r}",
            f"STRUCT_TYPE = {str(struct_type)!r}",
            "",
            "STRUCT_PAYLOAD: Dict[str, Any] = " + dumped_payload,
            "",
        ]
    )


def _export_struct_definitions_from_pyugc_dump(
    *,
    pyugc_object: Any,
    output_package_root: Path,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"struct_definitions": [], "struct_definitions_count": 0}
    if not isinstance(pyugc_object, dict):
        return result
    root4 = pyugc_object.get("4")
    if not isinstance(root4, dict):
        return result
    node_graph_root = root4.get("10")
    if not isinstance(node_graph_root, dict):
        return result

    struct_blob_texts = node_graph_root.get("6")
    if struct_blob_texts is None:
        # 单条记录时，pyugc 可能保留为 data 节点：key 会带 @data 后缀
        struct_blob_texts = node_graph_root.get("6@data")
    blob_texts: List[str] = []
    if isinstance(struct_blob_texts, str):
        if struct_blob_texts.strip():
            blob_texts = [struct_blob_texts]
    elif isinstance(struct_blob_texts, list):
        flattened: List[str] = []
        for item in struct_blob_texts:
            if isinstance(item, str) and item.strip():
                flattened.append(item)
                continue
            if isinstance(item, list):
                flattened.extend([text for text in item if isinstance(text, str) and text.strip()])
        blob_texts = flattened
    else:
        return result
    if not blob_texts:
        return result
    basic_struct_def_dir = output_package_root / "管理配置" / "结构体定义" / "基础结构体"
    ingame_save_struct_def_dir = output_package_root / "管理配置" / "结构体定义" / "局内存档结构体"
    raw_dir = output_package_root / "管理配置" / "结构体定义" / "原始解析"
    _ensure_directory(basic_struct_def_dir)
    _ensure_directory(ingame_save_struct_def_dir)
    _ensure_directory(raw_dir)
    _ensure_claude_for_directory(basic_struct_def_dir, purpose="管理配置：结构体定义（基础结构体，代码资源 .py）。")
    _ensure_claude_for_directory(ingame_save_struct_def_dir, purpose="管理配置：结构体定义（局内存档结构体，代码资源 .py）。")
    _ensure_claude_for_directory(raw_dir, purpose="存放从 .gil 中解析得到的结构体定义原始结构与二次解码结果，用于对照与继续逆向。")

    # 兼容旧版导出：早期版本会以“纯数值 struct_id”落盘；导出前清理旧文件，避免重复定义影响校验。
    for struct_def_dir in (basic_struct_def_dir, ingame_save_struct_def_dir):
        for py_file in struct_def_dir.glob("结构体_*.py"):
            if not py_file.is_file():
                continue
            stem = py_file.stem
            if not stem.startswith("结构体_"):
                continue
            remainder = stem[len("结构体_") :]
            if "_" not in remainder:
                continue
            candidate_id = remainder.split("_", 1)[0]
            if candidate_id.isdigit():
                py_file.unlink()

    decoded_struct_blobs: List[Tuple[int, int, str, bytes, Dict[str, object]]] = []
    for blob_index, blob_text in enumerate(blob_texts):
        decoded_bytes = base64.b64decode(blob_text)
        decoded_object = decode_bytes_to_python(decoded_bytes)
        if not isinstance(decoded_object, Mapping):
            _write_json_file(
                raw_dir / f"struct_blob_{int(blob_index)}.unknown.json",
                {
                    "blob_index": int(blob_index),
                    "byte_size": len(decoded_bytes),
                    "base64": blob_text,
                    "decoded": decoded_object,
                    "reason": "struct blob is not a dict message",
                },
            )
            continue

        struct_message = decoded_object.get("field_1", {}).get("message")
        if not isinstance(struct_message, Mapping):
            # decode_gil 的“文本优先”策略可能把本应是 nested message 的 bytes（field_1 wrapper）
            # 误判为 raw_hex+utf8；这里对 raw_hex 再解一次，恢复为 message 结构。
            field_1_node = decoded_object.get("field_1")
            if isinstance(field_1_node, Mapping):
                raw_hex = field_1_node.get("raw_hex")
                if isinstance(raw_hex, str) and raw_hex:
                    decoded_again = decode_bytes_to_python(bytes.fromhex(raw_hex))
                    if isinstance(decoded_again, Mapping):
                        struct_message = decoded_again

        if not isinstance(struct_message, Mapping):
            _write_json_file(
                raw_dir / f"struct_blob_{int(blob_index)}.unknown.json",
                {
                    "blob_index": int(blob_index),
                    "byte_size": len(decoded_bytes),
                    "base64": blob_text,
                    "decoded": dict(decoded_object),
                    "reason": "struct blob missing field_1.message",
                },
            )
            continue
        struct_id_int = _extract_int(struct_message.get("field_1"))
        struct_name = _extract_utf8(struct_message.get("field_501"))
        if struct_id_int is None:
            _write_json_file(
                raw_dir / f"struct_blob_{int(blob_index)}.unknown.json",
                {
                    "blob_index": int(blob_index),
                    "byte_size": len(decoded_bytes),
                    "base64": blob_text,
                    "decoded": dict(decoded_object),
                    "reason": "struct blob missing struct_id (field_1)",
                },
            )
            continue
        decoded_struct_blobs.append(
            (
                int(blob_index),
                int(struct_id_int),
                struct_name,
                decoded_bytes,
                dict(decoded_object),
            )
        )

    # struct_id 作为编辑器/资源侧的主键：保持为“10 位纯数字文本”以通过 Graph_Generater 校验。
    # 注意：Graph_Generater 的校验会加载共享与当前项目存档的结构体定义；若与共享重复会直接报错。
    struct_id_mapping: Dict[int, str] = {}
    for _blob_index, struct_id_int, _struct_name, _decoded_bytes, _decoded_object in decoded_struct_blobs:
        struct_id_mapping[int(struct_id_int)] = str(int(struct_id_int))

    existing_struct_ids_in_library: set[str] = set()
    if output_package_root.parent.name == "项目存档":
        resources_root = output_package_root.parent.parent
        if (resources_root / "共享").is_dir():
            existing_struct_ids_in_library = _collect_existing_struct_id_texts_from_resource_library(output_package_root)

    discovered_struct_ids: List[str] = []
    written_struct_ids: List[str] = []
    skipped_existing_struct_ids: List[str] = []
    for blob_index, struct_id_int, struct_name, decoded_bytes, decoded_object in decoded_struct_blobs:
        struct_message = decoded_object.get("field_1", {}).get("message")
        if not isinstance(struct_message, Mapping):
            field_1_node = decoded_object.get("field_1")
            if isinstance(field_1_node, Mapping):
                raw_hex = field_1_node.get("raw_hex")
                if isinstance(raw_hex, str) and raw_hex:
                    decoded_again = decode_bytes_to_python(bytes.fromhex(raw_hex))
                    if isinstance(decoded_again, Mapping):
                        struct_message = decoded_again

        if not isinstance(struct_message, Mapping):
            _write_json_file(
                raw_dir / f"struct_blob_{int(blob_index)}.unknown.json",
                {
                    "blob_index": int(blob_index),
                    "byte_size": len(decoded_bytes),
                    "base64": base64.b64encode(decoded_bytes).decode("ascii"),
                    "decoded": dict(decoded_object),
                    "reason": "struct blob missing field_1.message (decoded_struct_blobs)",
                },
            )
            continue

        # struct_type 目前以 field_2 的存在与取值做经验性区分：
        # - 缺失 field_2：基础结构体（basic）
        # - field_2.int == 2：局内存档结构体（ingame_save）
        struct_type = "basic"
        field_2_node = struct_message.get("field_2")
        if isinstance(field_2_node, Mapping) and isinstance(field_2_node.get("int"), int):
            if int(field_2_node["int"]) == 2:
                struct_type = "ingame_save"

        exported_struct_id = struct_id_mapping.get(int(struct_id_int), str(int(struct_id_int)))
        discovered_struct_ids.append(exported_struct_id)

        raw_struct_id_text = str(int(struct_id_int))
        raw_file_name = f"struct_def_{raw_struct_id_text}_{blob_index}.decoded.json"
        _write_json_file(
            raw_dir / raw_file_name,
            {
                "struct_id_int": int(struct_id_int),
                "exported_struct_id": exported_struct_id,
                "struct_name": struct_name,
                "blob_index": int(blob_index),
                "byte_size": len(decoded_bytes),
                "decoded": decoded_object,
            },
        )

        # 共享中已存在同 STRUCT_ID：跳过写入代码资源，避免触发 Graph_Generater 的“重复结构体 ID”校验错误。
        if exported_struct_id in existing_struct_ids_in_library:
            skipped_existing_struct_ids.append(exported_struct_id)
            continue

        _raw_struct_id_int, _raw_struct_name, fields = _parse_struct_definition_payload(
            struct_message,
            struct_id_mapping=struct_id_mapping,
        )

        safe_name = _sanitize_filename(struct_name, max_length=80)
        py_filename = f"结构体_{exported_struct_id}_{safe_name}.py"
        py_path = (ingame_save_struct_def_dir if struct_type == "ingame_save" else basic_struct_def_dir) / py_filename
        code = _build_struct_definition_py(
            struct_id_text=exported_struct_id,
            struct_type=struct_type,
            struct_name=struct_name or raw_struct_id_text,
            fields=fields,
        )
        _write_text_file(py_path, code)
        written_struct_ids.append(exported_struct_id)

    discovered_struct_ids = sorted(set(discovered_struct_ids), key=lambda text: int(text) if text.isdigit() else text)
    written_struct_ids = sorted(set(written_struct_ids), key=lambda text: int(text) if text.isdigit() else text)
    skipped_existing_struct_ids = sorted(
        set(skipped_existing_struct_ids), key=lambda text: int(text) if text.isdigit() else text
    )

    result["struct_definitions_discovered"] = discovered_struct_ids
    result["struct_definitions_discovered_count"] = len(discovered_struct_ids)
    result["struct_definitions"] = written_struct_ids
    result["struct_definitions_count"] = len(written_struct_ids)
    result["struct_definitions_skipped_existing"] = skipped_existing_struct_ids
    result["struct_definitions_skipped_existing_count"] = len(skipped_existing_struct_ids)
    return result


__all__ = ["_export_struct_definitions_from_pyugc_dump"]


