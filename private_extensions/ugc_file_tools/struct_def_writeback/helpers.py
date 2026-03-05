from __future__ import annotations

import copy
import struct
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_json_tree import (
    deep_replace_int_inplace,
    ensure_dict as _ensure_path_dict,
    ensure_list as _ensure_path_list,
    ensure_list_allow_scalar as _ensure_path_list_allow_scalar,
    load_gil_payload_as_dump_json_object,
    set_int_node as _set_int_node,
    set_text_node_utf8 as _set_text_node_utf8,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)

def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    return load_gil_payload_as_dump_json_object(
        Path(input_gil_file_path).resolve(),
        max_depth=32,
        prefer_raw_hex_for_utf8=False,
    )


def _decode_struct_id_from_blob_bytes(blob_bytes: bytes) -> int:
    decoded = decode_bytes_to_python(blob_bytes)
    if not isinstance(decoded, Mapping):
        raise ValueError("struct blob decode result is not dict")
    wrapper = decoded.get("field_1")
    if not isinstance(wrapper, Mapping):
        raise ValueError("struct blob missing field_1 wrapper")
    struct_message = wrapper.get("message")
    if not isinstance(struct_message, Mapping):
        raise ValueError("struct blob missing field_1.message")
    struct_id_node = struct_message.get("field_1")
    if not isinstance(struct_id_node, Mapping) or not isinstance(struct_id_node.get("int"), int):
        raise ValueError("struct blob missing struct_id varint")
    return int(struct_id_node["int"])


def _try_decode_struct_id_from_blob_bytes(blob_bytes: bytes) -> Optional[int]:
    """
    尝试从结构体定义 blob 中提取 struct_id。

    注意：部分存档的 `root4/10/6` 列表内可能混入“非标准结构体 blob”的条目（仍为 <binary_data>），
    其顶层并不包含 `field_1.message.field_1=int(struct_id)` 形态。

    该函数用于扫描/挑模板时的容错：
    - 结构不匹配时返回 None（跳过该条目）
    - 不使用 try/except
    """
    decoded = decode_bytes_to_python(blob_bytes)
    if not isinstance(decoded, Mapping):
        return None
    wrapper = decoded.get("field_1")
    if not isinstance(wrapper, Mapping):
        return None
    struct_message = wrapper.get("message")
    if not isinstance(struct_message, Mapping):
        return None
    struct_id_node = struct_message.get("field_1")
    if not isinstance(struct_id_node, Mapping) or not isinstance(struct_id_node.get("int"), int):
        return None
    return int(struct_id_node["int"])


def _choose_next_struct_id(existing_ids: Sequence[int]) -> int:
    cleaned = [int(v) for v in existing_ids if isinstance(v, int)]
    if not cleaned:
        return 1077936000
    return max(cleaned) + 1


def _collect_reserved_struct_ids_from_payload_root(payload_root: Mapping[str, Any]) -> List[int]:
    """
    从 payload_root['5']['1'] 收集一组“候选 ID”列表。

    说明（经验性结论）：
    - 在部分存档中，这里会包含（至少一部分）结构体定义使用过的 struct_id；
    - 但它 **不是** 完整的“结构体槽位表”，struct_id 也并非必须出现在这里（用户样本中可见 6133+ 的结构体定义）。

    因此：脚本仅在“该列表与现有 struct_id 有交集”时，把它当作可选候选池；否则默认直接走 max+1 自增。
    """
    section5 = payload_root.get("5")
    if not isinstance(section5, Mapping):
        return []
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        return []

    reserved: List[int] = []
    for entry in entry_list:
        if not isinstance(entry, Mapping):
            continue
        value = entry.get("1")
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], int):
            continue
        candidate = int(value[0])
        if 1077936000 <= candidate <= 1077937000:
            reserved.append(candidate)
    return sorted(set(reserved))


def _set_default_string_node(node: Dict[str, Any], text: str) -> None:
    # 默认字符串在当前样本中被编码为一个“嵌套 message（field_1:string）”：
    # bytes = encode_message({"1": "<text>"})
    nested_bytes = encode_message({"1": str(text)})
    node["raw_hex"] = nested_bytes.hex()
    node["utf8"] = str(text)


def _encode_varint(value: int) -> bytes:
    if not isinstance(value, int):
        raise TypeError(f"varint value must be int, got {type(value).__name__}")
    if value < 0:
        value = int(value) & 0xFFFFFFFF
    parts: List[int] = []
    remaining = int(value)
    while True:
        byte_value = remaining & 0x7F
        remaining >>= 7
        if remaining:
            parts.append(byte_value | 0x80)
        else:
            parts.append(byte_value)
            break
    return bytes(parts)


def _encode_packed_varints(values: Sequence[int]) -> bytes:
    chunks: List[bytes] = []
    for item in values:
        chunks.append(_encode_varint(int(item)))
    return b"".join(chunks)


def _encode_float32_list(values: Sequence[float]) -> bytes:
    chunks: List[bytes] = []
    for item in values:
        # 样本中浮点数列表的每个元素占 8 bytes：float32 + 4 bytes padding(0)。
        # 若仅写入 4 bytes 的 packed float32，游戏侧可能无法导入（但我们的解析器可兼容）。
        chunks.append(struct.pack("<f", float(item)) + b"\x00\x00\x00\x00")
    return b"".join(chunks)


def _get_utf8_from_text_node(node: Any) -> str:
    if not isinstance(node, Mapping):
        return ""
    if isinstance(node.get("utf8"), str):
        return str(node["utf8"])
    raw_hex = node.get("raw_hex")
    if isinstance(raw_hex, str):
        return bytes.fromhex(raw_hex).decode("utf-8", errors="replace")
    return ""


def _get_struct_message_from_decoded_blob(decoded_blob: Mapping[str, Any], wrapper_key: str) -> Dict[str, Any]:
    wrapper = decoded_blob.get(wrapper_key)
    if not isinstance(wrapper, Mapping):
        raise ValueError(f"template missing {wrapper_key} wrapper")
    struct_message = wrapper.get("message")
    if not isinstance(struct_message, dict):
        raise ValueError(f"template missing {wrapper_key}.message")
    return struct_message


def _iter_field_entries(struct_message: Mapping[str, Any]) -> List[Dict[str, Any]]:
    field_3_value = struct_message.get("field_3")
    if field_3_value is None:
        return []
    if isinstance(field_3_value, list):
        return [entry for entry in field_3_value if isinstance(entry, dict)]
    if isinstance(field_3_value, Mapping):
        if isinstance(field_3_value, dict):
            return [field_3_value]
        raise ValueError("unexpected struct_message.field_3 mapping (not dict)")
    raise ValueError("unexpected struct_message.field_3 shape")


def _decode_field_entry(entry: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    message_value = entry.get("message")
    if isinstance(message_value, dict):
        return "message", message_value

    # 某些字段（例如字符串列表/浮点数列表）会被 decode_gil 的“文本优先”策略
    # 误判为 raw_hex+utf8；这里对 raw_hex 再解一次，恢复为 message。
    raw_hex_value = entry.get("raw_hex")
    if isinstance(raw_hex_value, str) and raw_hex_value:
        decoded = decode_bytes_to_python(bytes.fromhex(raw_hex_value))
        if isinstance(decoded, dict):
            return "raw_hex", decoded
    raise ValueError("field entry missing message/raw_hex")


def _commit_field_entry(entry: Dict[str, Any], entry_kind: str, field_msg: Dict[str, Any]) -> None:
    if entry_kind != "raw_hex":
        return
    # 归一化为 numeric_message，再重编码回 raw_hex（保持 bytes 不漂移）
    dump_json_message = decoded_field_map_to_numeric_message(field_msg, prefer_raw_hex_for_utf8=True)
    if not isinstance(dump_json_message, dict):
        raise TypeError("decoded field map did not convert to dict numeric_message")
    encoded_bytes = encode_message(dict(dump_json_message))
    entry.pop("message", None)
    entry.pop("utf8", None)
    entry["raw_hex"] = encoded_bytes.hex()


def _find_field_message(
    struct_message: Mapping[str, Any],
    field_name: str,
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    target = str(field_name)
    for entry in _iter_field_entries(struct_message):
        entry_kind, field_msg = _decode_field_entry(entry)
        name = _get_utf8_from_text_node(field_msg.get("field_501")) or _get_utf8_from_text_node(field_msg.get("field_5"))
        if str(name) == target:
            return entry, entry_kind, field_msg
    raise ValueError(f"field not found in template struct: {field_name!r}")


def _get_type_value_container(field_msg: Mapping[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    field_3 = field_msg.get("field_3")
    if not isinstance(field_3, Mapping):
        raise ValueError("field_msg.field_3 missing")
    inner = field_3.get("message")
    if not isinstance(inner, dict):
        raise ValueError("field_msg.field_3.message missing")
    type_keys = [k for k in inner.keys() if k not in {"field_1", "field_2"}]
    if not type_keys:
        raise ValueError("field value inner message missing type value key")
    if len(type_keys) != 1:
        raise ValueError(f"field value inner message has unexpected keys: {sorted(inner.keys())}")
    key = str(type_keys[0])
    container = inner.get(key)
    if not isinstance(container, dict):
        raise ValueError("type value container is not dict")
    return key, container, inner


def _set_default_bool_node(container_node: Dict[str, Any], value: bool) -> None:
    """
    写入 type_id=4（布尔值）的默认值。

    实测：
    - 模板的 False 通常表现为：{"raw_hex": ""}
    - 写入 True 不能用 raw_hex="01"（游戏导入会失败），应使用：{"message": {"field_1": int(1)}} 的形态
      （用户提供的 `结构体布尔是.gil` 中已验证，且字典 bool value 也是该形态）。
    """
    container_node.clear()
    if bool(value):
        container_node["message"] = {"field_1": {}}
        field_1 = container_node["message"].get("field_1")
        if not isinstance(field_1, dict):
            raise ValueError("bool message.field_1 is not dict")
        _set_int_node(field_1, 1)
        return
    container_node["raw_hex"] = ""


def _set_default_int_in_message_container(container_node: Dict[str, Any], value: int) -> None:
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected container_node.message dict")
    field_1 = message.get("field_1")
    if not isinstance(field_1, dict):
        raise ValueError("expected container_node.message.field_1 dict")
    _set_int_node(field_1, int(value))


def _set_default_float_in_message_container(container_node: Dict[str, Any], value: float) -> None:
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected container_node.message dict")
    field_1 = message.get("field_1")
    if not isinstance(field_1, dict):
        raise ValueError("expected container_node.message.field_1 dict")
    float_value = float(value)
    bits = struct.unpack("<I", struct.pack("<f", float_value))[0]
    field_1["fixed32_int"] = int(bits)
    field_1["fixed32_float"] = float_value


def _set_default_vector3_in_message_container(container_node: Dict[str, Any], x: float, y: float, z: float) -> None:
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected vector3 container message dict")
    field_1 = message.get("field_1")
    if not isinstance(field_1, dict):
        raise ValueError("expected vector3 message.field_1 dict")
    vec_msg = field_1.get("message")
    if not isinstance(vec_msg, dict):
        raise ValueError("expected vector3 message.field_1.message dict")
    vec_msg.setdefault("field_1", {})
    vec_msg.setdefault("field_2", {})
    vec_msg.setdefault("field_3", {})
    for key, float_value in (("field_1", float(x)), ("field_2", float(y)), ("field_3", float(z))):
        node = vec_msg.get(key)
        if not isinstance(node, dict):
            raise ValueError("vector3 component node is not dict")
        bits = struct.unpack("<I", struct.pack("<f", float_value))[0]
        node["fixed32_int"] = int(bits)
        node["fixed32_float"] = float_value


def _set_default_packed_varint_list(container_node: Dict[str, Any], values: Sequence[int]) -> None:
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected packed list container message dict")
    raw_node = message.get("field_1")
    if not isinstance(raw_node, dict):
        raise ValueError("expected packed list message.field_1 dict")
    raw_node["raw_hex"] = _encode_packed_varints(values).hex()


def _set_default_float_list(container_node: Dict[str, Any], values: Sequence[float]) -> None:
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected float list container message dict")
    raw_node = message.get("field_1")
    if not isinstance(raw_node, dict):
        raise ValueError("expected float list message.field_1 dict")
    raw_node["raw_hex"] = _encode_float32_list(values).hex()


def _set_default_string_list_raw(container_node: Dict[str, Any], values: Sequence[str]) -> None:
    raw_bytes = encode_message({"1": [str(v) for v in values]})
    container_node["raw_hex"] = raw_bytes.hex()


def _set_default_dict_string_bool(container_node: Dict[str, Any], keys: Sequence[str], values: Sequence[bool]) -> None:
    if len(keys) != len(values):
        raise ValueError("dict keys/values length mismatch")
    message = container_node.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected dict container message dict")
    key_nodes = message.get("field_501")
    value_nodes = message.get("field_502")
    if not isinstance(key_nodes, list) or not isinstance(value_nodes, list):
        raise ValueError("expected dict key/value node lists")
    if len(key_nodes) < len(keys) or len(value_nodes) < len(values):
        raise ValueError("template dict has fewer entries than requested")

    for index, (key_text, bool_value) in enumerate(zip(keys, values)):
        key_item = key_nodes[index]
        value_item = value_nodes[index]
        if not isinstance(key_item, dict) or not isinstance(value_item, dict):
            raise ValueError("dict key/value item is not dict")
        key_msg = key_item.get("message")
        value_msg = value_item.get("message")
        if not isinstance(key_msg, dict) or not isinstance(value_msg, dict):
            raise ValueError("dict key/value item missing message")

        key_text_node = key_msg.get("field_16")
        if not isinstance(key_text_node, dict):
            raise ValueError("dict key item missing field_16")
        _set_default_string_node(key_text_node, str(key_text))

        bool_node = value_msg.get("field_14")
        if not isinstance(bool_node, dict):
            raise ValueError("dict value item missing field_14")
        _set_default_bool_node(bool_node, bool(bool_value))


def _collect_all_binary_data_texts(obj: Any) -> List[str]:
    results: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, str) and x.startswith("<binary_data>"):
            results.append(x)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return results


def _replace_binary_data_bytes_in_object(
    obj: Any,
    *,
    old_bytes: bytes,
    new_bytes: bytes,
) -> None:
    if not old_bytes:
        raise ValueError("old_bytes is empty")
    if len(old_bytes) != len(new_bytes):
        raise ValueError("byte replacement must keep length to avoid corrupting unknown layouts")

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in list(x.items()):
                if isinstance(v, str) and v.startswith("<binary_data>"):
                    raw = parse_binary_data_hex_text(v)
                    replaced = raw.replace(old_bytes, new_bytes)
                    x[k] = format_binary_data_hex_text(replaced)
                    continue
                walk(v)
            return
        if isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)


def _replace_int_values_in_object(obj: Any, *, old_value: int, new_value: int) -> None:
    deep_replace_int_inplace(obj, old=int(old_value), new=int(new_value))


def _sanitize_decoded_invalid_field0_message_nodes(obj: Any) -> None:
    """
    decode_gil 在某些 bytes 字段上会“误判为 nested message”，并把原始 bytes `00 00` 解成：
      {"message": {"field_0": {"int": 0, ...}}}
    或（重复 0 的变体）：
      {"message": {"field_0": [{"int": 0, ...}, ...]}}

    但 field_number=0 在 protobuf 中是非法的，我们的 encoder 也拒绝编码。
    为了在“仅修改其它字段（例如重命名）”时仍能把 blob 重新编码回去，这里把该形态归一为：
      {"raw_hex": "0000"}
    或按重复次数保持字节长度：
      {"raw_hex": "0000" * N}
    以保持 bytes 等价，并移除非法的 field_0。
    """
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict) and set(msg.keys()) == {"field_0"}:
            field0 = msg.get("field_0")
            if isinstance(field0, dict) and field0.get("int") == 0:
                obj.pop("message", None)
                obj.pop("utf8", None)
                obj["raw_hex"] = "0000"
                return
            if isinstance(field0, list) and all(
                isinstance(item, dict) and item.get("int") == 0 for item in field0
            ):
                # field_0 是非法字段号；该形态通常来自“全 0 bytes 被误判为 repeated varint(field_0=0)”。
                # 这里将其归一化回 raw bytes：每个 (tag=0, value=0) 对应 2 bytes => "0000" * N。
                obj.pop("message", None)
                obj.pop("utf8", None)
                obj["raw_hex"] = "0000" * len(field0)
                return

        for v in obj.values():
            _sanitize_decoded_invalid_field0_message_nodes(v)
        return

    if isinstance(obj, list):
        for v in obj:
            _sanitize_decoded_invalid_field0_message_nodes(v)
        return


def _ensure_struct_visible_in_tabs(
    payload_root: Dict[str, Any],
    *,
    struct_id_int: int,
    template_struct_id_int: int,
) -> List[List[Dict[str, Any]]]:
    """
    将新结构体注册到“结构体页签”列表中（否则可能导入失败/界面不可见）。

    已确认的结构：
    - payload_root['6']['1'][22]['3']：未分类页签，list 在 key '5'
    - payload_root['6']['1'][22]['2']['4'][*]：自定义页签列表，每个页签的 list 在 key '5'
      （例如 test7 的 struct_all_supported(6130) 位于 '自定义页签_1' 的 list5）

    行为：
    - 优先把新 struct_id 追加到“包含 template_struct_id 的页签 list”中；
    - 若找不到模板所在页签，则追加到未分类页签 list。
    """
    section6 = payload_root.get("6")
    if not isinstance(section6, dict):
        raise ValueError("payload_root 缺少 '6' 或不是 dict，无法写入结构体页签注册。")
    entry_list = section6.get("1")
    if not isinstance(entry_list, list) or len(entry_list) <= 22 or not isinstance(entry_list[22], dict):
        raise ValueError("payload_root['6']['1'][22] 缺失或结构不符合预期。")
    entry22 = entry_list[22]

    def ensure_list(container: Dict[str, Any]) -> List[Dict[str, Any]]:
        value = container.get("5")
        if value is None:
            container["5"] = []
            return container["5"]
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            # 兼容：repeated 字段在“只有 1 个元素”时可能被 dump 为 dict 标量
            container["5"] = [value]
            return container["5"]
        raise ValueError("结构体页签的 '5' 不是 list。")

    candidate_lists: List[List[Dict[str, Any]]] = []

    sub3 = entry22.get("3")
    if isinstance(sub3, dict):
        candidate_lists.append(ensure_list(sub3))

    sub2 = entry22.get("2")
    if isinstance(sub2, dict):
        tabs = sub2.get("4")
        if isinstance(tabs, list):
            for tab in tabs:
                if not isinstance(tab, dict):
                    continue
                candidate_lists.append(ensure_list(tab))

    def has_struct_id(items: List[Dict[str, Any]], sid: int) -> bool:
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("1") == 4100 and item.get("2") == int(sid):
                return True
        return False

    target_lists = [lst for lst in candidate_lists if has_struct_id(lst, int(template_struct_id_int))]
    if not target_lists:
        target_lists = candidate_lists[:1] if candidate_lists else []
    if not target_lists:
        raise ValueError("未找到可写入的结构体页签 list（payload_root['6']['1'][22] 缺少页签结构）。")

    for lst in target_lists:
        if has_struct_id(lst, int(struct_id_int)):
            continue
        lst.append({"1": 4100, "2": int(struct_id_int)})

    return target_lists


def _find_template_struct_node_defs(
    node_defs: Sequence[Any],
    *,
    template_struct_id: int,
) -> Dict[str, Dict[str, Any]]:
    """
    在 root4/10/2 中定位某个结构体对应的 3 个节点定义：
    - 拼装结构体 / 拆分结构体 / 修改结构体

    定位规则：节点 entry['1']['200'] 为上述名称之一，且其内部 binary_data 包含 template_struct_id 的 varint 字节序列。
    """
    wanted_names = {"拼装结构体", "拆分结构体", "修改结构体"}
    template_pat = _encode_varint(int(template_struct_id))

    best: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    for entry in node_defs:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("1")
        if not isinstance(inner, dict):
            continue
        # dump-json 的文本字段可能是 str，也可能是 {raw_hex, utf8} 的 text node。
        name_raw = inner.get("200")
        name = str(name_raw) if isinstance(name_raw, str) else _get_utf8_from_text_node(name_raw)
        if name not in wanted_names:
            continue

        def count_int_occurrences(x: Any, wanted: int) -> int:
            if isinstance(x, dict):
                total = 0
                for v in x.values():
                    total += count_int_occurrences(v, wanted)
                return total
            if isinstance(x, list):
                total = 0
                for v in x:
                    total += count_int_occurrences(v, wanted)
                return total
            if isinstance(x, int) and int(x) == int(wanted):
                return 1
            return 0

        binary_texts = _collect_all_binary_data_texts(inner)
        hit = 0
        for text in binary_texts:
            raw = parse_binary_data_hex_text(text)
            hit += raw.count(template_pat)
        hit += count_int_occurrences(inner, int(template_struct_id))
        if hit <= 0:
            continue

        existing = best.get(str(name))
        if existing is None or hit > int(existing[0]):
            best[str(name)] = (int(hit), entry)

    result: Dict[str, Dict[str, Any]] = {}
    for name in wanted_names:
        if str(name) not in best:
            raise ValueError(f"未在 node10/2 中找到模板结构体节点定义：{name}（struct_id={template_struct_id}）")
        result[str(name)] = best[str(name)][1]
    return result


def _extract_node_type_id_from_node_def(entry: Mapping[str, Any]) -> int | None:
    if not isinstance(entry, Mapping):
        return None
    inner = entry.get("1")
    if not isinstance(inner, Mapping):
        return None
    field_4 = inner.get("4")
    if not isinstance(field_4, Mapping):
        return None
    node_a = field_4.get("1")
    node_b = field_4.get("2")
    if not isinstance(node_a, Mapping) or not isinstance(node_b, Mapping):
        return None
    value_a = node_a.get("5")
    value_b = node_b.get("5")
    if not isinstance(value_a, int) or not isinstance(value_b, int):
        return None
    if int(value_a) != int(value_b):
        # 其它节点类型可能会出现不一致，这里仅用于“模板结构体节点”时才要求一致。
        return None
    return int(value_a)


def _collect_existing_node_type_ids(node_defs: Sequence[Any]) -> List[int]:
    values: List[int] = []
    for entry in node_defs:
        if not isinstance(entry, Mapping):
            continue
        inner = entry.get("1")
        if not isinstance(inner, Mapping):
            continue
        field_4 = inner.get("4")
        if not isinstance(field_4, Mapping):
            continue
        for key in ("1", "2"):
            node = field_4.get(key)
            if not isinstance(node, Mapping):
                continue
            value = node.get("5")
            if isinstance(value, int):
                values.append(int(value))
    return values


def _collect_existing_struct_ref_ids(struct_blob_list: Sequence[Any]) -> List[int]:
    """
    收集当前存档中所有结构体定义 blob 内出现的“引用 id”（field_4.varint），用于分配不冲突的新值。

    说明：
    - 目前仅覆盖已确认的两种位置：
      - 结构体字段(type_id=25)：value_container.message.field_502.message.field_4
      - 结构体列表字段(type_id=26)：item.message.field_35.message.field_502.message.field_4
    """
    ref_ids: List[int] = []

    for entry in struct_blob_list:
        if not isinstance(entry, str) or not entry.startswith("<binary_data>"):
            continue
        blob_bytes = parse_binary_data_hex_text(entry)
        decoded = decode_bytes_to_python(blob_bytes)
        if not isinstance(decoded, Mapping):
            continue
        wrapper = decoded.get("field_1")
        if not isinstance(wrapper, Mapping):
            continue
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, Mapping):
            continue
        fields = struct_message.get("field_3")
        if not isinstance(fields, list):
            continue

        for field_entry in fields:
            if not isinstance(field_entry, Mapping):
                continue
            field_msg_value = field_entry.get("message")
            if not isinstance(field_msg_value, Mapping):
                raw_hex_value = field_entry.get("raw_hex")
                if isinstance(raw_hex_value, str) and raw_hex_value:
                    field_msg_value = decode_bytes_to_python(bytes.fromhex(raw_hex_value))
            if not isinstance(field_msg_value, Mapping):
                continue

            type_id_node = field_msg_value.get("field_502")
            type_id = type_id_node.get("int") if isinstance(type_id_node, Mapping) else None
            if type_id not in (25, 26):
                continue

            inner = (
                field_msg_value.get("field_3", {}).get("message")
                if isinstance(field_msg_value.get("field_3"), Mapping)
                else None
            )
            if not isinstance(inner, Mapping):
                continue
            type_keys = [k for k in inner.keys() if k not in {"field_1", "field_2"}]
            if len(type_keys) != 1:
                continue
            container = inner.get(type_keys[0])
            if not isinstance(container, Mapping):
                continue
            container_msg = container.get("message")
            if not isinstance(container_msg, Mapping):
                continue

            if type_id == 25:
                field_502 = container_msg.get("field_502")
                if not isinstance(field_502, Mapping):
                    continue
                field_502_msg = field_502.get("message")
                if not isinstance(field_502_msg, Mapping):
                    continue
                field_4 = field_502_msg.get("field_4")
                if isinstance(field_4, Mapping) and isinstance(field_4.get("int"), int):
                    ref_ids.append(int(field_4["int"]))

            if type_id == 26:
                items = container_msg.get("field_1")
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    item_msg = item.get("message")
                    if not isinstance(item_msg, Mapping):
                        continue
                    field_35 = item_msg.get("field_35")
                    if not isinstance(field_35, Mapping):
                        continue
                    field_35_msg = field_35.get("message")
                    if not isinstance(field_35_msg, Mapping):
                        continue
                    field_502 = field_35_msg.get("field_502")
                    if not isinstance(field_502, Mapping):
                        continue
                    field_502_msg = field_502.get("message")
                    if not isinstance(field_502_msg, Mapping):
                        continue
                    field_4 = field_502_msg.get("field_4")
                    if isinstance(field_4, Mapping) and isinstance(field_4.get("int"), int):
                        ref_ids.append(int(field_4["int"]))

    return ref_ids


def _collect_existing_struct_internal_ids(struct_blob_list: Sequence[Any]) -> List[int]:
    """
    收集当前存档中所有结构体定义 blob 的“内部结构体类型 id”（struct_message.field_503.int）。

    现象依据：
    - test7 中两个结构体的 field_503 分别为 4 与 6（互不相同）；
    - 当我们克隆 6130 到 6132 时若不更新该值，会造成重复（两者都为 6），
      很可能触发游戏侧导入校验失败。
    """
    values: List[int] = []
    for entry in struct_blob_list:
        blob_bytes: bytes | None = None
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(entry)
        elif isinstance(entry, Mapping):
            blob_bytes = encode_message(entry)
        else:
            continue

        decoded = decode_bytes_to_python(blob_bytes)
        if not isinstance(decoded, Mapping):
            continue
        wrapper = decoded.get("field_1")
        if not isinstance(wrapper, Mapping):
            continue
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, Mapping):
            continue
        field_503 = struct_message.get("field_503")
        if isinstance(field_503, Mapping) and isinstance(field_503.get("int"), int):
            values.append(int(field_503["int"]))
    return values


__all__ = [
    "_dump_gil_to_raw_json_object",
    "_ensure_path_dict",
    "_ensure_path_list",
    "_ensure_path_list_allow_scalar",
    "_decode_struct_id_from_blob_bytes",
    "_try_decode_struct_id_from_blob_bytes",
    "_choose_next_struct_id",
    "_collect_reserved_struct_ids_from_payload_root",
    "_set_text_node_utf8",
    "_set_int_node",
    "_set_default_string_node",
    "_encode_varint",
    "_encode_packed_varints",
    "_encode_float32_list",
    "_get_utf8_from_text_node",
    "_get_struct_message_from_decoded_blob",
    "_iter_field_entries",
    "_decode_field_entry",
    "_commit_field_entry",
    "_find_field_message",
    "_get_type_value_container",
    "_set_default_bool_node",
    "_set_default_int_in_message_container",
    "_set_default_float_in_message_container",
    "_set_default_vector3_in_message_container",
    "_set_default_packed_varint_list",
    "_set_default_float_list",
    "_set_default_string_list_raw",
    "_set_default_dict_string_bool",
    "_collect_all_binary_data_texts",
    "_replace_binary_data_bytes_in_object",
    "_replace_int_values_in_object",
    "_sanitize_decoded_invalid_field0_message_nodes",
    "_ensure_struct_visible_in_tabs",
    "_find_template_struct_node_defs",
    "_extract_node_type_id_from_node_def",
    "_collect_existing_node_type_ids",
    "_collect_existing_struct_ref_ids",
    "_collect_existing_struct_internal_ids",
]
