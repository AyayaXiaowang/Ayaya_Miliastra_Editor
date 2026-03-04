from __future__ import annotations

"""
add_signal_definition_to_gil.py

目标：
- 在 `.gil` 的“节点图段 / 复合节点库段”（payload_root['10']）中新增“信号定义”；
- 对齐编辑器行为：每个信号会生成 3 个节点定义：
  - 发送信号
  - 监听信号
  - 向服务器节点图发送信号
- 同时写入信号表（signal entries）与节点定义表（node defs / meta index）。

实现策略（模板驱动，fail-closed）：
- 纯 Python `.gil → dump-json`（数值键结构；bytes 以 "<binary_data> .." 表示），避免 DLL 不稳定导致写回链路崩溃
- 从 `--template-gil` 提取：
  - 一个“无参数信号”的 3 个节点定义作为 base 模板
-  - （可选）若干参数类型的端口模板（按 type_id，供 template 模式克隆）
- 在目标 `--input-gil` 中：
  - 追加新的 node_def（3 个）
  - 追加 node_def meta（root4/10/5/2）
  - 追加 signal entry（root4/10/5/3）
- 使用 `gil_dump_codec.protobuf_like.encode_message` 重编码 payload_root，并按原 `.gil` header/footer 封装输出。

注意：
- 本脚本不尝试“自动放置节点到某张图里”，仅保证信号与对应节点定义已创建；
- 现在支持两种参数口构建模式：
  - template：参数口通过“模板信号”克隆（旧逻辑；需要 template 存档内覆盖目标参数类型）
  - semantic：参数口按 type_id 语义规则构造（新逻辑；不再要求 template 覆盖每个 type_id）
"""

import argparse
import copy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.gil_dump_codec.dump_json_tree import (
    ensure_dict as _ensure_path_dict,
    ensure_list as _ensure_path_list,
    ensure_list_allow_scalar as _ensure_path_list_allow_scalar,
    load_gil_payload_as_dump_json_object,
    set_int_node as _set_int_node,
    set_text_node_utf8 as _set_text_node_utf8,
)
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import (
    binary_data_text_to_decoded_field_map,
    binary_data_text_to_numeric_message,
    decoded_field_map_to_binary_data_text,
    numeric_message_to_binary_data_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import (
    load_graph_generater_type_registry,
    map_graph_variable_cn_type_to_var_type_int,
    parse_typed_dict_alias,
)


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    """
    读取 `.gil` 的 payload bytes 并转换为 dump-json 风格的“数值键 dict”。

    说明：
    - 过去该模块曾依赖外部 DLL 做 gil→dump-json；但中间产物稳定性不足，易触发异常。
    - 这里改为纯 Python protobuf-like 解码（lossless decoded_field_map）并桥接为“数值键结构”，
      避免导出链路因 DLL 不稳定而导致主程序退出。
    """
    # 关键：信号写回需要在“不触碰既有 NodeGraph blob bytes”的前提下做增量 patch。
    #
    # 说明：
    # - `.gil` 的 node graphs 位于 payload_root['10']['1'] 的深层 bytes blob（section10/10.1.1），
    #   若在 dump-json 阶段对 blob 做“嵌套 message 解码”，再全量重编码 payload，会导致 blob 字节被重排/重写，
    #   最常见的现象是：图内信号节点的 META value 变空（官方侧可能表现为无法打开/运行时解析失败）。
    # - 因此这里显式降低 max_depth，只解码到“信号表/节点定义”所需深度；对更深层 bytes 一律保持为 `<binary_data>`，
    #   从而确保未修改的 blob 能字节级保真 roundtrip。
    raw_dump_object = load_gil_payload_as_dump_json_object(
        Path(input_gil_file_path).resolve(),
        # max_depth 需要同时满足两点：
        # - 足够深：能解码到 node_def['4']（meta），以便从 base 推断已占用的 node_def_id/端口索引；
        # - 足够浅：不要把 NodeGraph blob bytes（section10/10.1.1）当作嵌套 message 展开，否则全量重编码会误改 blob。
        #
        # 经验：5 层刚好能覆盖 node_def meta（用于分配与对齐），并阻止深入解码 node graphs。
        max_depth=5,
        prefer_raw_hex_for_utf8=False,
    )
    _normalize_signal_binary_fields_inplace(_get_payload_root(raw_dump_object))
    return raw_dump_object


def _normalize_signal_binary_fields_inplace(payload_root: Dict[str, Any]) -> None:
    """
    对齐信号写回侧的 dump-json 口径：
    - signal entry 的参数定义（entry['4']）为 `<binary_data>`（可能为 list 或 scalar）
    - server_meta_text（entry['7']）为 `<binary_data>`
    - node_def 的参数口定义（node_def['102']）为 `<binary_data>`（可能为 list 或 scalar）
    """
    if not isinstance(payload_root, dict):
        return
    section10 = payload_root.get("10")
    if not isinstance(section10, dict):
        return

    section5 = section10.get("5")
    if isinstance(section5, dict):
        signal_list = section5.get("3")
        if isinstance(signal_list, list):
            for entry in signal_list:
                if not isinstance(entry, dict):
                    continue
                params_value = entry.get("4")
                if isinstance(params_value, list):
                    new_params: List[Any] = []
                    for p in params_value:
                        if isinstance(p, dict):
                            new_params.append(format_binary_data_hex_text(encode_message(dict(p))))
                        else:
                            new_params.append(p)
                    entry["4"] = new_params
                elif isinstance(params_value, dict):
                    entry["4"] = format_binary_data_hex_text(encode_message(dict(params_value)))

                server_meta = entry.get("7")
                if isinstance(server_meta, dict):
                    entry["7"] = format_binary_data_hex_text(encode_message(dict(server_meta)))

    node_defs = section10.get("2")
    if isinstance(node_defs, list):
        for wrapper in node_defs:
            if not isinstance(wrapper, dict):
                continue
            inner = wrapper.get("1")
            if not isinstance(inner, dict):
                continue
            ports_value = inner.get("102")
            if isinstance(ports_value, list):
                new_ports: List[Any] = []
                for p in ports_value:
                    if isinstance(p, dict):
                        new_ports.append(format_binary_data_hex_text(encode_message(dict(p))))
                    else:
                        new_ports.append(p)
                inner["102"] = new_ports
            elif isinstance(ports_value, dict):
                inner["102"] = format_binary_data_hex_text(encode_message(dict(ports_value)))


def _get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    return payload_root


def _extract_nested_int(node: Any, path: Sequence[str]) -> Optional[int]:
    cursor: Any = node
    for key in path:
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, int):
        return int(cursor)
    if isinstance(cursor, Mapping) and isinstance(cursor.get("int"), int):
        return int(cursor.get("int"))
    return None


def _decoded_field_map_to_numeric_message_node(value: Any) -> Any:
    """
    将 decoded_field_map（field_* keys）尽量规约回“数值键 message”形态：
    - 顶层/嵌套 dict：`field_123` → `"123"`
    - 其余 keys（例如 `message`/`int`）保持不变

    注意：不做值层面的类型强转（例如 `{int: 1}` 不会被改成 `1`），由上层 `_extract_nested_int` 等工具处理。
    """
    if isinstance(value, list):
        return [_decoded_field_map_to_numeric_message_node(x) for x in list(value)]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in dict(value).items():
            if isinstance(k, str) and k.startswith("field_") and k[6:].isdigit():
                out[str(k[6:])] = _decoded_field_map_to_numeric_message_node(v)
            else:
                out[str(k)] = _decoded_field_map_to_numeric_message_node(v)
        return out
    return value


def _build_node_def_meta_dict(*, node_def_id_int: int, scope_code_int: int) -> Dict[str, Any]:
    # 对齐样本（pyugc 的 node meta）：
    # - send/listen: field_2=20000
    # - send_to_server: field_2=20002
    return {"1": 10001, "2": int(scope_code_int), "3": 22001, "5": int(node_def_id_int)}


def _build_node_def_meta_binary_text(*, node_def_id_int: int, scope_code_int: int) -> str:
    return numeric_message_to_binary_data_text(_build_node_def_meta_dict(node_def_id_int=node_def_id_int, scope_code_int=scope_code_int))


def _extract_node_def_id_from_node_def_object(node_def_object: Mapping[str, Any]) -> int:
    node_def_id_value = _extract_nested_int(node_def_object, ["4", "1", "5"])
    if not isinstance(node_def_id_value, int):
        raise ValueError("node def missing 4/1/5")
    return int(node_def_id_value)


def _extract_signal_entries_from_payload_root(payload_root: Mapping[str, Any]) -> List[Dict[str, Any]]:
    section10 = payload_root.get("10")
    if not isinstance(section10, Mapping):
        return []
    section5 = section10.get("5")
    if not isinstance(section5, Mapping):
        return []
    signal_list = section5.get("3")
    raw_entries: list[Any] = []
    if isinstance(signal_list, list):
        raw_entries = list(signal_list)
    elif isinstance(signal_list, dict):
        raw_entries = [signal_list]
    elif isinstance(signal_list, str) and signal_list.startswith("<binary_data>"):
        raw_entries = [signal_list]
    else:
        return []

    results: list[Dict[str, Any]] = []
    for item in list(raw_entries):
        if isinstance(item, dict):
            results.append(item)
            continue
        if isinstance(item, str) and item.startswith("<binary_data>"):
            decoded = binary_data_text_to_decoded_field_map(str(item))
            if not isinstance(decoded, dict):
                continue
            normalized = _decoded_field_map_to_numeric_message_node(decoded)
            if isinstance(normalized, dict):
                results.append(normalized)
            continue
    return results


def _extract_node_def_wrappers_from_payload_root(payload_root: Mapping[str, Any]) -> List[Dict[str, Any]]:
    section10 = payload_root.get("10")
    if not isinstance(section10, Mapping):
        return []
    node_defs = section10.get("2")
    if not isinstance(node_defs, list):
        return []
    return [item for item in node_defs if isinstance(item, dict)]


def _index_node_defs_by_id(payload_root: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    mapping: Dict[int, Dict[str, Any]] = {}

    # 优先：使用 `section10/5/2` 的 meta index 与 `section10/2` 的 wrappers 位置对齐来索引。
    #
    # 背景：
    # - 信号写回为了避免误改 NodeGraph blob，会使用较浅的 dump 解码深度；
    # - 在该深度下，node_def 内部 meta（`node_def['4']['1']`）可能无法完全展开，
    #   从而导致“按 meta 路径提取 node_def_id”失败；
    # - 但 `section10/5/2` 的 meta index 列表在 dump-json 中更稳定，且与 wrappers 数量一致，
    #   因此可用它作为 node_def_id 的真源索引。
    section10 = payload_root.get("10")
    if isinstance(section10, Mapping):
        sec5 = section10.get("5")
        meta_list_value = sec5.get("2") if isinstance(sec5, Mapping) else None
        meta_list: list[Any] = []
        if isinstance(meta_list_value, list):
            meta_list = list(meta_list_value)
        elif isinstance(meta_list_value, Mapping):
            meta_list = [meta_list_value]

        wrappers = _extract_node_def_wrappers_from_payload_root(payload_root)
        if meta_list and wrappers and len(meta_list) == len(wrappers):
            for i in range(len(wrappers)):
                meta_item = meta_list[i]
                wrapper = wrappers[i]
                inner = wrapper.get("1")
                if not (isinstance(meta_item, Mapping) and isinstance(inner, dict)):
                    continue
                node_def_id = meta_item.get("5")
                if not isinstance(node_def_id, int):
                    node_def_id = meta_item.get("field_5")
                if not isinstance(node_def_id, int):
                    continue
                mapping.setdefault(int(node_def_id), inner)
            if mapping:
                return mapping

    # fallback：从 node_def 内部 meta 推断（要求 dump 解码足够深）
    for wrapper in _extract_node_def_wrappers_from_payload_root(payload_root):
        inner = wrapper.get("1")
        if not isinstance(inner, dict):
            continue
        try_id = _extract_nested_int(inner, ["4", "1", "5"])
        if not isinstance(try_id, int):
            continue
        mapping[int(try_id)] = inner
    return mapping


def _normalize_repeated_binary_field(parent: Dict[str, Any], key: str) -> List[str]:
    value = parent.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.startswith("<binary_data>")]
    if isinstance(value, str) and value.startswith("<binary_data>"):
        return [value]
    return []


def _extract_type_id_from_send_param_item(decoded: Mapping[str, Any]) -> int:
    type_id_value = _extract_nested_int(decoded, ["field_4", "message", "field_3"])
    if not isinstance(type_id_value, int):
        raise ValueError("param item missing field_4.message.field_3.int(type_id)")
    return int(type_id_value)


def _extract_type_id_from_listen_param_port(port_object: Mapping[str, Any]) -> int:
    type_id_value = _extract_nested_int(port_object, ["4", "3"])
    if not isinstance(type_id_value, int):
        raise ValueError("listen param port missing 4/3(type_id)")
    return int(type_id_value)


def _collect_param_templates_from_template_payload(
    template_payload_root: Mapping[str, Any],
) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    返回：
    - send_param_item_template_by_type_id: type_id -> decode_gil 输出（field_* dict）
    - listen_param_port_template_by_type_id: type_id -> dump-json 端口 dict（用于追加到 103 列表）
    - server_param_item_template_by_type_id: type_id -> decode_gil 输出（field_* dict）
    """
    node_defs_by_id = _index_node_defs_by_id(template_payload_root)
    signal_entries = _extract_signal_entries_from_payload_root(template_payload_root)

    send_param_item_template_by_type_id: Dict[int, Dict[str, Any]] = {}
    listen_param_port_template_by_type_id: Dict[int, Dict[str, Any]] = {}
    server_param_item_template_by_type_id: Dict[int, Dict[str, Any]] = {}

    def _decode_signal_param_defs(entry: Mapping[str, Any]) -> Dict[str, int]:
        """
        从 signal entry 的 field 4（repeated binary）解析 param_name -> type_id。
        注意：server node_def 的 param item 内部 type 字段与 signal param type_id 不一定一致，
        因此这里以“param_name 对齐”作为桥梁建立映射。
        """
        params_value = entry.get("4")
        texts: List[str] = []
        if isinstance(params_value, list):
            texts = [t for t in params_value if isinstance(t, str) and t.startswith("<binary_data>")]
        elif isinstance(params_value, str) and params_value.startswith("<binary_data>"):
            texts = [params_value]
        if not texts:
            return {}
        mapping: Dict[str, int] = {}
        for t in texts:
            decoded = binary_data_text_to_decoded_field_map(t)
            name = str(decoded.get("field_1", {}).get("utf8") or "").strip()
            type_id = decoded.get("field_2", {}).get("int")
            if name and isinstance(type_id, int):
                mapping[name] = int(type_id)
        return mapping

    for entry in signal_entries:
        send_meta = entry.get("1")
        listen_meta = entry.get("2")
        if not (isinstance(send_meta, Mapping) and isinstance(listen_meta, Mapping)):
            continue
        send_id = send_meta.get("5")
        listen_id = listen_meta.get("5")
        if not (isinstance(send_id, int) and isinstance(listen_id, int)):
            continue

        send_def = node_defs_by_id.get(int(send_id))
        listen_def = node_defs_by_id.get(int(listen_id))
        if not (isinstance(send_def, dict) and isinstance(listen_def, dict)):
            continue

        signal_param_name_to_type_id = _decode_signal_param_defs(entry)

        # send: 102 = param items (binary_data)
        for param_item_text in _normalize_repeated_binary_field(send_def, "102"):
            decoded = binary_data_text_to_decoded_field_map(param_item_text)
            type_id = _extract_type_id_from_send_param_item(decoded)
            send_param_item_template_by_type_id.setdefault(int(type_id), decoded)

        # send_to_server: 102 = param items (binary_data)
        server_meta_text = entry.get("7")
        if isinstance(server_meta_text, str) and server_meta_text.startswith("<binary_data>"):
            server_decoded = binary_data_text_to_decoded_field_map(server_meta_text)
            server_id = _extract_nested_int(server_decoded, ["field_5", "int"])
            if not isinstance(server_id, int):
                server_id = _extract_nested_int(server_decoded, ["field_5"])
            server_def = node_defs_by_id.get(int(server_id)) if isinstance(server_id, int) else None
            if isinstance(server_def, dict) and signal_param_name_to_type_id:
                for param_item_text in _normalize_repeated_binary_field(server_def, "102"):
                    decoded = binary_data_text_to_decoded_field_map(param_item_text)
                    param_name = str(decoded.get("field_1", {}).get("utf8") or "").strip()
                    type_id = signal_param_name_to_type_id.get(param_name)
                    if isinstance(type_id, int):
                        server_param_item_template_by_type_id.setdefault(int(type_id), decoded)

        # listen: 103 = output ports (dict), 参数口直接是 dict
        ports = listen_def.get("103")
        if isinstance(ports, list):
            for port in ports:
                if not isinstance(port, dict):
                    continue
                port_name = str(port.get("1") or "").strip()
                if not port_name.startswith("参数_"):
                    continue
                type_id = _extract_type_id_from_listen_param_port(port)
                listen_param_port_template_by_type_id.setdefault(int(type_id), port)

    return send_param_item_template_by_type_id, listen_param_port_template_by_type_id, server_param_item_template_by_type_id


def _choose_base_signal_node_def_templates_from_template_payload(
    template_payload_root: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    从 template 中挑一个“无参数信号”，返回三种 node_def 的 raw dict（发送/监听/向服务器发送）。
    """
    node_defs_by_id = _index_node_defs_by_id(template_payload_root)

    for entry in _extract_signal_entries_from_payload_root(template_payload_root):
        params = entry.get("4")
        params_is_empty = (params is None) or (isinstance(params, list) and len(params) == 0)
        if not params_is_empty:
            continue

        send_meta = entry.get("1")
        listen_meta = entry.get("2")
        server_meta_value = entry.get("7")
        if not (isinstance(send_meta, Mapping) and isinstance(listen_meta, Mapping)):
            continue

        send_id = _extract_nested_int(send_meta, ["5"])
        listen_id = _extract_nested_int(listen_meta, ["5"])
        if not (isinstance(send_id, int) and isinstance(listen_id, int)):
            continue

        server_id: Optional[int] = None
        if isinstance(server_meta_value, str) and server_meta_value.startswith("<binary_data>"):
            server_decoded = binary_data_text_to_decoded_field_map(server_meta_value)
            server_id = _extract_nested_int(server_decoded, ["field_5", "int"])
            if not isinstance(server_id, int):
                server_id = _extract_nested_int(server_decoded, ["field_5"])
        elif isinstance(server_meta_value, Mapping):
            server_id = _extract_nested_int(server_meta_value, ["5"])
            if not isinstance(server_id, int):
                server_id = _extract_nested_int(server_meta_value, ["field_5"])
        if not isinstance(server_id, int):
            raise ValueError("cannot decode server node_def_id from signal entry 7")

        send_def = node_defs_by_id.get(int(send_id))
        listen_def = node_defs_by_id.get(int(listen_id))
        server_def = node_defs_by_id.get(int(server_id))
        if not (isinstance(send_def, dict) and isinstance(listen_def, dict) and isinstance(server_def, dict)):
            continue

        return copy.deepcopy(send_def), copy.deepcopy(listen_def), copy.deepcopy(server_def)

    raise ValueError("template 中未找到“无参数信号”，无法选择基础 node_def 模板")


def _try_choose_base_signal_node_def_templates_from_template_payload(
    template_payload_root: Mapping[str, Any],
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """
    尝试从 template 中挑一个“无参数信号”，返回三种 node_def 的 raw dict（发送/监听/向服务器发送）。

    与 `_choose_base_signal_node_def_templates_from_template_payload` 的区别：
    - 找不到可用样本时返回 None（用于“自动模板选择”场景）。
    """
    node_defs_by_id = _index_node_defs_by_id(template_payload_root)

    for entry in _extract_signal_entries_from_payload_root(template_payload_root):
        params = entry.get("4")
        params_is_empty = (params is None) or (isinstance(params, list) and len(params) == 0)
        if not params_is_empty:
            continue

        send_meta = entry.get("1")
        listen_meta = entry.get("2")
        server_meta_value = entry.get("7")
        if not (isinstance(send_meta, Mapping) and isinstance(listen_meta, Mapping)):
            continue

        send_id = _extract_nested_int(send_meta, ["5"])
        listen_id = _extract_nested_int(listen_meta, ["5"])
        if not (isinstance(send_id, int) and isinstance(listen_id, int)):
            continue

        server_id: Optional[int] = None
        if isinstance(server_meta_value, str) and server_meta_value.startswith("<binary_data>"):
            server_decoded = binary_data_text_to_decoded_field_map(server_meta_value)
            server_id = _extract_nested_int(server_decoded, ["field_5", "int"])
            if not isinstance(server_id, int):
                server_id = _extract_nested_int(server_decoded, ["field_5"])
        elif isinstance(server_meta_value, Mapping):
            server_id = _extract_nested_int(server_meta_value, ["5"])
            if not isinstance(server_id, int):
                server_id = _extract_nested_int(server_meta_value, ["field_5"])
        if not isinstance(server_id, int):
            continue

        send_def = node_defs_by_id.get(int(send_id))
        listen_def = node_defs_by_id.get(int(listen_id))
        server_def = node_defs_by_id.get(int(server_id))
        if not (isinstance(send_def, dict) and isinstance(listen_def, dict) and isinstance(server_def, dict)):
            continue

        return copy.deepcopy(send_def), copy.deepcopy(listen_def), copy.deepcopy(server_def)

    return None


def _collect_existing_node_def_ids(payload_root: Mapping[str, Any]) -> List[int]:
    ids: List[int] = []

    # 优先：来自 signal node_def meta index（section10/5/2）
    section10 = payload_root.get("10")
    if isinstance(section10, Mapping):
        sec5 = section10.get("5")
        if isinstance(sec5, Mapping):
            meta_list_value = sec5.get("2")
            items: list[Any] = []
            if isinstance(meta_list_value, list):
                items = list(meta_list_value)
            elif isinstance(meta_list_value, Mapping):
                items = [meta_list_value]
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                node_def_id = item.get("5")
                if not isinstance(node_def_id, int):
                    node_def_id = item.get("field_5")
                if isinstance(node_def_id, int):
                    ids.append(int(node_def_id))

    if ids:
        return ids

    # fallback：从 node_def wrapper 内部 meta 推断（要求 dump 解码足够深）
    for wrapper in _extract_node_def_wrappers_from_payload_root(payload_root):
        inner = wrapper.get("1")
        if not isinstance(inner, Mapping):
            continue
        node_def_id = _extract_nested_int(inner, ["4", "1", "5"])
        if isinstance(node_def_id, int):
            ids.append(int(node_def_id))
    return ids


def _collect_existing_signal_indices(payload_root: Mapping[str, Any]) -> List[int]:
    indices: List[int] = []
    for entry in _extract_signal_entries_from_payload_root(payload_root):
        value = entry.get("6")
        if isinstance(value, int):
            indices.append(int(value))
    return indices


def _collect_port_index_candidates_from_node_def(node_def_object: Any) -> List[int]:
    results: List[int] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            port_index = value.get("8")
            if isinstance(port_index, int):
                results.append(int(port_index))
            for child in value.values():
                walk(child)
            return
        if isinstance(value, list):
            for child in value:
                walk(child)
            return

    walk(node_def_object)
    return results


def _choose_next_node_def_id(
    existing_node_def_ids: Sequence[int],
    *,
    preferred_scope_prefix: int | None = None,
) -> int:
    """
    为“信号三连号（send/listen/server_send）”选择下一组 node_def_id 的 send 起点。

    重要：不同真源/版本存在两套口径：
    - 可玩真源（after_game 侧常见）：0x4000xxxx（server scope）/0x4080xxxx（client scope），且 send/listen/server 为三连号。
      - 例：send=0x40000001, listen=0x40000002, server=0x40000003
    - 历史/工具链样本中也可能出现：0x6000xxxx/0x6080xxxx 段的三连号。

    写回原则：**跟随 base `.gil` 已存在的号段**；当 base 没有任何信号时，默认按可玩真源口径从 0x4000 段开始分配，
    避免产出“结构自洽但运行时分发口径不一致”的文件。
    """
    cleaned = [int(v) for v in existing_node_def_ids if isinstance(v, int)]

    used: set[int] = {int(v) for v in cleaned}

    scope_mask = 0xFF800000
    known_prefixes = {0x40000000, 0x40800000, 0x60000000, 0x60800000}

    scope_prefix: int | None = None
    if isinstance(preferred_scope_prefix, int):
        scope_prefix = int(preferred_scope_prefix)
    else:
        # best-effort：从已存在 node_def_id 中探测信号常见号段；优先选择 0x4000/0x4080（可玩真源口径）。
        prefixes_in_use = {int(v) & int(scope_mask) for v in used}
        prefixes_in_use = {int(p) for p in prefixes_in_use if int(p) in known_prefixes}
        if 0x40000000 in prefixes_in_use:
            scope_prefix = 0x40000000
        elif 0x40800000 in prefixes_in_use:
            scope_prefix = 0x40800000
        elif 0x60000000 in prefixes_in_use:
            scope_prefix = 0x60000000
        elif 0x60800000 in prefixes_in_use:
            scope_prefix = 0x60800000
        else:
            scope_prefix = 0x40000000

    if int(scope_prefix) not in known_prefixes:
        raise ValueError(f"unsupported preferred_scope_prefix: 0x{int(scope_prefix):08X}")

    lane = sorted(v for v in used if (int(v) & int(scope_mask)) == int(scope_prefix))

    # 空 base 的默认起点：按真源习惯为 send_id % 3 == 1 且三连号不冲突。
    if int(scope_prefix) in (0x60000000, 0x60800000):
        default_start = int(scope_prefix) + 0x00000004
    else:
        default_start = int(scope_prefix) + 0x00000001

    candidate = (int(max(lane)) + 1) if lane else int(default_start)
    if (int(candidate) & int(scope_mask)) != int(scope_prefix):
        candidate = int(default_start)

    # 关键：以“号段内 offset”对齐三连号（send/listen/server），而不是用 candidate 的绝对值取模。
    # 例如：可玩真源常见 send_id=0x40000001（candidate % 3 != 1，但 (candidate - 0x40000000) % 3 == 1）。
    while (int(candidate) - int(scope_prefix)) % 3 != 1:
        candidate += 1

    # 需要确保整组三连号都不冲突（send/listen/server）。
    while any(int(candidate + offset) in used for offset in (0, 1, 2)):
        candidate += 3

    return int(candidate)


_SCALAR_SIGNAL_PARAM_TYPE_IDS: set[int] = {2, 3, 4, 5, 6}


def _choose_signal_index_for_params(params: Sequence[Mapping[str, Any]]) -> int:
    """
    `.gil` 真源样本中的 signal_index（signal_entry.field_6 / node_def.meta.field_5）。

    目前样本能确认的点：
    - 无参数：常见为 2（例如占位无参信号 `新建的没有参数的信号`）。
    - 纯标量参数（type_id ∈ {2(Gid),3(Int),4(Bol),5(Flt),6(Str)}）：
      - 双参信号：常见为 3（=param_count+1）
      - 5 参信号：可出现 6（=param_count+1）
      => 经验上可写为：max(2, param_count+1)
    - 含非标量参数（例如 Cfg/L<Gid>/Vec 等 type_id 不在上述集合内）：
      - 5 参信号在样本中仍为 2（不是 param_count+1）

    注意：这是基于当前覆盖到的真源样本做的最小规则；若后续样本出现冲突，应以真源为准并补回归。
    """
    if not isinstance(params, Sequence):
        raise TypeError("params must be Sequence[Mapping[str, Any]]")

    type_ids: list[int] = []
    for item in list(params):
        if not isinstance(item, Mapping):
            continue
        type_id = item.get("type_id", None)
        if isinstance(type_id, int):
            type_ids.append(int(type_id))

    param_count = int(len(type_ids))
    if param_count <= 0:
        return 2

    is_scalar_only = all(int(t) in _SCALAR_SIGNAL_PARAM_TYPE_IDS for t in type_ids)
    if is_scalar_only:
        return max(2, int(param_count) + 1)

    return 2


def _should_group_signal_param_ports(params: Sequence[Mapping[str, Any]]) -> bool:
    """
    真源样本对照发现：当信号包含非标量参数类型（例如 Cfg/L<Gid>/Vec），其参数端口索引更常见为：
    - send ports：连续 N 个
    - listen ports：连续 N 个
    - server ports：连续 N 个

    因此写回侧对“含非标量参数”的信号使用“按角色分块”的端口分配。
    """
    if not isinstance(params, Sequence):
        raise TypeError("params must be Sequence[Mapping[str, Any]]")
    for item in list(params):
        if not isinstance(item, Mapping):
            continue
        type_id = item.get("type_id", None)
        if isinstance(type_id, int) and int(type_id) not in _SCALAR_SIGNAL_PARAM_TYPE_IDS:
            return True
    return False


def _choose_next_port_index(payload_root: Mapping[str, Any]) -> int:
    node_defs_by_id = _index_node_defs_by_id(payload_root)
    port_indices: List[int] = []
    for node_def in node_defs_by_id.values():
        port_indices.extend(_collect_port_index_candidates_from_node_def(node_def))
    if not port_indices:
        return 1
    return max(port_indices) + 1


def _ensure_node_def_name(node_def_object: Mapping[str, Any], expected: str) -> None:
    name_value = node_def_object.get("200")
    if not isinstance(name_value, str) or name_value.strip() != str(expected):
        raise ValueError(f"node def name mismatch: expected {expected!r}, got {name_value!r}")


def _ensure_single_port_container_dict(node_def_object: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    兼容 dump-json 的不稳定输出：
    - repeated message 字段在“只有 1 个元素”时，可能被 DLL 输出为 dict（标量）或 list([dict])（repeated）。
    - 对于 node_def 的 100/101（流程端口）这类“语义上应只有 1 个元素”的字段，这里统一返回可写的 dict 视图。
    """
    value = node_def_object.get(key)
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f"expected {key} list len=1, got len={len(value)}")
        first = value[0]
        if not isinstance(first, dict):
            raise ValueError(f"expected {key}[0] dict, got {type(first).__name__}")
        return first
    raise ValueError(f"expected dict/list at key={key!r}, got {type(value).__name__}")


def _ensure_path_dict_allow_binary(parent: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    兼容浅层 dump 解码：当某些“应为 message(dict)”的字段被表示为 `<binary_data>` 时，
    先按 message 解码回 numeric_message dict，再返回可写视图。

    说明：
    - 该逻辑仅用于信号写回域内已知的 message 字段（例如 node_def['4']['1'/'2'] meta），
      避免因 dump 解码深度限制导致 `_ensure_path_dict` 直接抛错。
    """
    value = parent.get(str(key))
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        decoded = binary_data_text_to_numeric_message(str(value))
        if isinstance(decoded, Mapping):
            out = dict(decoded)
            parent[str(key)] = out
            return out
    return _ensure_path_dict(parent, str(key))


def _patch_signal_name_port_default_value_inplace(*, port_obj: Dict[str, Any], signal_name: str) -> None:
    """
    对齐“校验成功”样本：signal-specific node_def 的【信号名】端口需要携带默认值与标记位：
    - port_obj['4'].2：VarBase(StringBaseValue)=signal_name
    - port_obj['4'].6：1
    否则官方侧更严格校验可能失败（已由多份 success/fail 对照确认）。
    """
    port4 = _ensure_path_dict_allow_binary(port_obj, "4")

    # 注意：这里的 VarBase.item_type 口径与 node_graph_semantics.var_base 不同（样本对齐）：
    # - send/listen：item_type={"1":1,"100":"<binary_data> "}
    # - server-send：item_type={"1":2,"101":{"2":<port4.field_4>}}，且该端口的 port4.field_4 样本为 9
    port4_field4 = port4.get("4")
    if isinstance(port4_field4, int):
        item_type = {"1": 2, "101": {"2": int(port4_field4)}}
    else:
        item_type = {"1": 1, "100": "<binary_data> "}

    vb = {
        "1": 5,  # StringBaseValue
        "2": 1,  # alreadySetVal
        "4": dict(item_type),
        "105": {"1": str(signal_name)},
    }
    port4["2"] = vb
    port4["6"] = 1


_SERVER_SIGNAL_DESCRIPTOR_TYPE_ID_BY_VAR_TYPE: Dict[int, int] = {
    # 对齐“可运行样本”中 server-send（向服务器节点图发送信号）参数描述类型号（field_4.field_3/field_4.field_4）
    1: 1,   # 实体
    2: 14,  # GUID（样本：发送者GUID）
    3: 3,   # 整数
    4: 5,   # 布尔值
    5: 7,   # 浮点数
    6: 9,   # 字符串
    8: 4,   # 整数列表
    9: 6,   # 布尔值列表
    10: 8,  # 浮点数列表
    11: 10, # 字符串列表
}


def _map_server_signal_descriptor_type_id(*, var_type_id: int) -> int:
    vt = int(var_type_id)
    mapped = _SERVER_SIGNAL_DESCRIPTOR_TYPE_ID_BY_VAR_TYPE.get(int(vt))
    if isinstance(mapped, int):
        return int(mapped)

    # 列表类型：优先尝试“元素类型映射后 +1”规则（对齐样本：Str(9) -> L<Str>(10)）。
    if _is_list_type_id(int(vt)):
        element_vt = _resolve_element_type_id_for_list_type(int(vt))
        mapped_element_vt = _map_server_signal_descriptor_type_id(var_type_id=int(element_vt))
        return int(mapped_element_vt + 1)

    # 未覆盖类型保持原值，避免无样本类型被强行错误映射。
    return int(vt)


def _build_server_scalar_type_descriptor(*, scalar_type_id_int: int, struct_id_int: int | None) -> Dict[str, Any]:
    descriptor = _build_scalar_type_descriptor(
        type_id_int=int(scalar_type_id_int),
        struct_id_int=(int(struct_id_int) if isinstance(struct_id_int, int) else None),
        dict_key_type_id_int=None,
        dict_value_type_id_int=None,
    )
    mapped_type_id = _map_server_signal_descriptor_type_id(var_type_id=int(scalar_type_id_int))
    descriptor["3"] = int(mapped_type_id)
    descriptor["4"] = int(mapped_type_id)

    # server-send 的 bool 描述字段与 send/listen 不同：field_101 需要写 200001。
    if int(scalar_type_id_int) == 4:
        descriptor["101"] = format_binary_data_hex_text(encode_message({"1": 200001}))

    return descriptor


def _build_server_type_descriptor_from_param_spec(*, param_spec: Mapping[str, Any]) -> Dict[str, Any]:
    type_id_value = param_spec.get("type_id")
    if not isinstance(type_id_value, int):
        raise ValueError("param_spec missing type_id int")
    type_id_int = int(type_id_value)

    if int(type_id_int) == 27:
        raise ValueError("信号参数类型不支持『字典』(type_id=27)")

    struct_id_int: int | None = None
    if int(type_id_int) in (25, 26):
        struct_id_int = _parse_optional_int_like(param_spec.get("struct_id"), field_name="struct_id")
        if not isinstance(struct_id_int, int):
            raise ValueError("struct/struct_list param requires struct_id")

    if _is_list_type_id(int(type_id_int)):
        element_type_id_int = _resolve_element_type_id_for_list_type(int(type_id_int))
        element_descriptor = _build_server_scalar_type_descriptor(
            scalar_type_id_int=int(element_type_id_int),
            struct_id_int=struct_id_int,
        )
        wrapper_bytes_text = format_binary_data_hex_text(encode_message({"1": dict(element_descriptor)}))
        mapped_list_type_id = _map_server_signal_descriptor_type_id(var_type_id=int(type_id_int))
        return {
            "1": 10002,
            "102": str(wrapper_bytes_text),
            "3": int(mapped_list_type_id),
            "4": int(mapped_list_type_id),
        }

    return _build_server_scalar_type_descriptor(
        scalar_type_id_int=int(type_id_int),
        struct_id_int=struct_id_int,
    )


def _reset_send_node_def_for_new_signal(
    *,
    template_send_def: Dict[str, Any],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    listen_meta_dict: Dict[str, Any],
    server_meta_binary_text: str,
    flow_in_port_index: int,
    flow_out_port_index: int,
    signal_name_port_index: int,
    send_param_port_texts: List[str],
) -> Dict[str, Any]:
    node_def = copy.deepcopy(template_send_def)
    _ensure_node_def_name(node_def, "发送信号")

    meta = _ensure_path_dict(node_def, "4")
    meta1 = _ensure_path_dict_allow_binary(meta, "1")
    meta2 = _ensure_path_dict_allow_binary(meta, "2")
    meta1["5"] = int(node_def_id_int)
    meta2["5"] = int(node_def_id_int)
    meta["5"] = int(signal_index_int)

    _ensure_single_port_container_dict(node_def, "100")["8"] = int(flow_in_port_index)
    _ensure_single_port_container_dict(node_def, "101")["8"] = int(flow_out_port_index)

    ports_106 = _ensure_path_list(node_def, "106")
    if not (ports_106 and isinstance(ports_106[0], dict)):
        raise ValueError("send node_def missing 106 list")
    ports_106[0]["8"] = int(signal_name_port_index)
    _patch_signal_name_port_default_value_inplace(port_obj=ports_106[0], signal_name=str(signal_name))

    sig = _ensure_path_dict(node_def, "107")
    sig101 = _ensure_path_dict_allow_binary(sig, "101")
    sig101["1"] = str(signal_name)
    sig101["2"] = dict(listen_meta_dict)
    sig101["3"] = str(server_meta_binary_text)

    if send_param_port_texts:
        node_def["102"] = list(send_param_port_texts)
    else:
        node_def.pop("102", None)

    return node_def


def _reset_listen_node_def_for_new_signal(
    *,
    template_listen_def: Dict[str, Any],
    listen_param_port_template_by_type_id: Optional[Dict[int, Dict[str, Any]]],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    send_meta_binary_text: str,
    server_meta_binary_text: str,
    flow_port_index: int,
    signal_name_port_index: int,
    fixed_output_port_indices: Tuple[int, int, int],
    params: List[Dict[str, Any]],
) -> Dict[str, Any]:
    node_def = copy.deepcopy(template_listen_def)
    _ensure_node_def_name(node_def, "监听信号")

    meta = _ensure_path_dict(node_def, "4")
    meta1 = _ensure_path_dict_allow_binary(meta, "1")
    meta2 = _ensure_path_dict_allow_binary(meta, "2")
    meta1["5"] = int(node_def_id_int)
    meta2["5"] = int(node_def_id_int)
    meta["5"] = int(signal_index_int)

    _ensure_single_port_container_dict(node_def, "101")["8"] = int(flow_port_index)

    ports_106 = _ensure_path_list(node_def, "106")
    if not (ports_106 and isinstance(ports_106[0], dict)):
        raise ValueError("listen node_def missing 106 list")
    ports_106[0]["8"] = int(signal_name_port_index)
    _patch_signal_name_port_default_value_inplace(port_obj=ports_106[0], signal_name=str(signal_name))

    # 固定输出：事件源实体/事件源GUID/信号来源实体
    fixed_names = ["事件源实体", "事件源GUID", "信号来源实体"]
    ports_103 = node_def.get("103")
    if not isinstance(ports_103, list):
        raise ValueError("listen node_def missing 103 list")
    fixed_ports: List[Dict[str, Any]] = []
    for item in ports_103:
        if not isinstance(item, dict):
            continue
        name = str(item.get("1") or "").strip()
        if name in fixed_names:
            fixed_ports.append(item)
    if len(fixed_ports) != 3:
        raise ValueError(f"listen node_def fixed outputs not found or not unique: found={len(fixed_ports)}")

    name_to_port = {str(p.get("1") or "").strip(): p for p in fixed_ports}
    name_to_port["事件源实体"]["8"] = int(fixed_output_port_indices[0])
    name_to_port["事件源GUID"]["8"] = int(fixed_output_port_indices[1])
    name_to_port["信号来源实体"]["8"] = int(fixed_output_port_indices[2])

    new_ports_103: List[Dict[str, Any]] = [name_to_port[n] for n in fixed_names]

    # 参数输出追加
    for param_index, param in enumerate(params):
        if not isinstance(param, Mapping):
            continue
        param_name = str(param.get("param_name") or "").strip()
        type_id = param.get("type_id")
        port_index = param.get("port_index")
        if param_name == "" or not isinstance(type_id, int) or not isinstance(port_index, int):
            raise ValueError("listen params requires param_name/type_id/port_index")

        if listen_param_port_template_by_type_id is not None:
            template_port = listen_param_port_template_by_type_id.get(int(type_id))
            if not isinstance(template_port, dict):
                raise ValueError(f"缺少监听信号参数端口模板：type_id={type_id}")
            port_obj = copy.deepcopy(template_port)
            port_obj["1"] = str(param_name)
            port_obj["8"] = int(port_index)

            slot = _ensure_path_dict(port_obj, "3")
            slot["1"] = 4
            slot["2"] = 3 + int(param_index)
        else:
            port_obj = _build_listen_param_port_object_from_param_spec(
                param_spec=param,
                param_index=int(param_index),
            )
            port_obj["8"] = int(port_index)

        new_ports_103.append(port_obj)

    node_def["103"] = new_ports_103

    sig = _ensure_path_dict(node_def, "107")
    sig102 = _ensure_path_dict_allow_binary(sig, "102")
    sig102["1"] = str(signal_name)
    sig102["2"] = str(send_meta_binary_text)
    sig102["3"] = str(server_meta_binary_text)

    return node_def


def _reset_send_to_server_node_def_for_new_signal(
    *,
    template_server_def: Dict[str, Any],
    signal_index_int: int,
    node_def_id_int: int,
    signal_name: str,
    listen_meta_dict: Dict[str, Any],
    send_meta_binary_text: str,
    flow_in_port_index: int,
    flow_out_port_index: int,
    extra_port_index: int,
    signal_name_port_index: int,
    server_param_port_texts: List[str],
) -> Dict[str, Any]:
    node_def = copy.deepcopy(template_server_def)
    _ensure_node_def_name(node_def, "向服务器节点图发送信号")

    meta = _ensure_path_dict(node_def, "4")
    meta1 = _ensure_path_dict_allow_binary(meta, "1")
    meta1["5"] = int(node_def_id_int)
    meta["5"] = int(signal_index_int)

    _ensure_single_port_container_dict(node_def, "100")["8"] = int(flow_in_port_index)
    _ensure_single_port_container_dict(node_def, "101")["8"] = int(flow_out_port_index)

    ports_106 = _ensure_path_list(node_def, "106")
    if len(ports_106) < 2:
        raise ValueError("send_to_server node_def missing 106 list")
    if not (isinstance(ports_106[0], dict) and isinstance(ports_106[1], dict)):
        raise ValueError("send_to_server node_def invalid 106 entries")
    ports_106[0]["8"] = int(extra_port_index)
    ports_106[1]["8"] = int(signal_name_port_index)
    _patch_signal_name_port_default_value_inplace(port_obj=ports_106[1], signal_name=str(signal_name))

    sig = _ensure_path_dict(node_def, "107")
    sig101 = _ensure_path_dict_allow_binary(sig, "101")
    sig101["1"] = str(signal_name)
    sig101["2"] = dict(listen_meta_dict)
    sig101["3"] = str(send_meta_binary_text)

    if server_param_port_texts:
        node_def["102"] = list(server_param_port_texts)
    else:
        node_def.pop("102", None)

    return node_def


def _build_param_item_binary_text_from_template(
    *,
    template_decoded: Mapping[str, Any],
    param_name: str,
    port_index_int: int,
) -> str:
    decoded = copy.deepcopy(dict(template_decoded))
    field_1 = decoded.get("field_1")
    field_8 = decoded.get("field_8")
    if not (isinstance(field_1, dict) and isinstance(field_8, dict)):
        raise ValueError("param item template missing field_1/field_8 nodes")
    _set_text_node_utf8(field_1, str(param_name))
    _set_int_node(field_8, int(port_index_int))
    return decoded_field_map_to_binary_data_text(decoded)


def _build_signal_param_definition_binary_text(
    *,
    param_name: str,
    type_id_int: int,
    send_port_index: int,
    listen_port_index: int,
    send_to_server_port_index: int,
) -> str:
    # 对齐样本：field_1=param_name, field_2=type_id, field_3=1, field_4/5/6=三类节点的端口 index
    msg = {
        "1": str(param_name),
        "2": int(type_id_int),
        "3": 1,
        "4": int(send_port_index),
        "5": int(listen_port_index),
        "6": int(send_to_server_port_index),
    }
    return format_binary_data_hex_text(encode_message(msg))


_LIST_TYPE_ID_TO_ELEMENT_TYPE_ID: Dict[int, int] = {
    7: 2,  # GUID列表 -> GUID
    8: 3,  # 整数列表 -> 整数
    9: 4,  # 布尔值列表 -> 布尔值
    10: 5,  # 浮点数列表 -> 浮点数
    11: 6,  # 字符串列表 -> 字符串
    13: 1,  # 实体列表 -> 实体
    15: 12,  # 三维向量列表 -> 三维向量
    22: 20,  # 配置ID列表 -> 配置ID
    23: 21,  # 元件ID列表 -> 元件ID
    24: 17,  # 阵营列表 -> 阵营
    26: 25,  # 结构体列表 -> 结构体
}


def _parse_int_like(value: Any, *, field_name: str) -> int:
    if isinstance(value, int):
        return int(value)
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    raise ValueError(f"{field_name} must be int-like, got {value!r}")


def _parse_optional_int_like(value: Any, *, field_name: str) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return _parse_int_like(value, field_name=field_name)


def _is_list_type_id(type_id_int: int) -> bool:
    return int(type_id_int) in _LIST_TYPE_ID_TO_ELEMENT_TYPE_ID


def _resolve_element_type_id_for_list_type(list_type_id_int: int) -> int:
    element = _LIST_TYPE_ID_TO_ELEMENT_TYPE_ID.get(int(list_type_id_int))
    if not isinstance(element, int):
        raise ValueError(f"unsupported list type_id: {list_type_id_int}")
    return int(element)


def _extract_struct_id_from_struct_descriptor_binary_text(binary_text: str) -> int:
    decoded = binary_data_text_to_decoded_field_map(binary_text)
    value = _extract_nested_int(decoded, ["field_2"])
    if not isinstance(value, int):
        raise ValueError("struct descriptor missing field_2(struct_id)")
    return int(value)


def _build_scalar_type_descriptor(
    *,
    type_id_int: int,
    struct_id_int: Optional[int],
    dict_key_type_id_int: Optional[int],
    dict_value_type_id_int: Optional[int],
) -> Dict[str, Any]:
    """
    构造“type descriptor”小 dict（出现在端口/参数 item 中的 `4` 或 nested message）。

    该结构已在仓库样本中验证（尤其是 bool/struct/dict 有额外字段）：
    - 实体(1): {3,4}
    - 基础标量(2/3/5/6/12/17/20/21): {1,3,4}
    - 布尔值(4): {1,101,3,4}
    - 结构体(25): {1,104,3,4}，其中 104=encode_message({2: struct_id})
    - 字典(27): 信号参数类型不支持（Graph_Generater 亦禁止信号参数使用字典）。
    """
    tid = int(type_id_int)
    if tid == 1:
        return {"3": 1, "4": 1}
    if tid in (2, 3, 5, 6):
        return {"1": tid - 1, "3": tid, "4": tid}
    if tid == 12:
        return {"1": 7, "3": 12, "4": 12}
    if tid in (17, 20, 21):
        return {"1": 1, "3": tid, "4": tid}
    if tid == 4:
        # bool 的 type descriptor 自带一个 field 101 = <binary_data> 08 01（与样本一致）
        return {"1": 6, "101": format_binary_data_hex_text(encode_message({"1": 1})), "3": 4, "4": 4}
    if tid == 25:
        if not isinstance(struct_id_int, int):
            raise ValueError("struct type requires struct_id")
        return {
            "1": 10001,
            "104": format_binary_data_hex_text(encode_message({"2": int(struct_id_int)})),
            "3": 25,
            "4": 25,
        }
    if tid == 27:
        raise ValueError("信号参数类型不支持『字典』(type_id=27)")
    raise ValueError(f"unsupported scalar type_id: {tid}")


def _build_type_descriptor_from_param_spec(*, param_spec: Mapping[str, Any]) -> Dict[str, Any]:
    type_id_value = param_spec.get("type_id")
    if not isinstance(type_id_value, int):
        raise ValueError("param_spec missing type_id int")
    type_id_int = int(type_id_value)

    struct_id_int: Optional[int] = None
    dict_key_type_id_int: Optional[int] = None
    dict_value_type_id_int: Optional[int] = None

    if type_id_int in (25, 26):
        struct_id_int = _parse_optional_int_like(param_spec.get("struct_id"), field_name="struct_id")
        if not isinstance(struct_id_int, int):
            raise ValueError("struct/struct_list param requires struct_id")

    if type_id_int == 27:
        raise ValueError("信号参数类型不支持『字典』(type_id=27)")

    if _is_list_type_id(type_id_int):
        element_type_id_int = _resolve_element_type_id_for_list_type(type_id_int)
        element_descriptor = _build_scalar_type_descriptor(
            type_id_int=element_type_id_int,
            struct_id_int=struct_id_int,
            dict_key_type_id_int=dict_key_type_id_int,
            dict_value_type_id_int=dict_value_type_id_int,
        )
        wrapper_bytes_text = format_binary_data_hex_text(encode_message({"1": element_descriptor}))
        return {"1": 10002, "102": wrapper_bytes_text, "3": int(type_id_int), "4": int(type_id_int)}

    return _build_scalar_type_descriptor(
        type_id_int=type_id_int,
        struct_id_int=struct_id_int,
        dict_key_type_id_int=dict_key_type_id_int,
        dict_value_type_id_int=dict_value_type_id_int,
    )


def _build_param_item_binary_text_from_param_spec(
    *,
    param_spec: Mapping[str, Any],
    port_index_int: int,
    param_ordinal: int,
    for_server_node: bool = False,
) -> str:
    param_name = str(param_spec.get("param_name") or "").strip()
    if param_name == "":
        raise ValueError("param_spec missing param_name")
    type_id_value = param_spec.get("type_id")
    if not isinstance(type_id_value, int):
        raise ValueError("param_spec missing type_id int")
    type_id_int = int(type_id_value)

    # 对齐“校验成功”样本：field_3.field_2 表达参数序号（第 0 个参数省略该字段）。
    field_3_msg: Dict[str, Any] = {"1": 3}
    if int(param_ordinal) > 0:
        field_3_msg["2"] = int(param_ordinal)

    type_descriptor = (
        _build_server_type_descriptor_from_param_spec(param_spec=param_spec)
        if bool(for_server_node)
        else _build_type_descriptor_from_param_spec(param_spec=param_spec)
    )
    msg = {
        "1": str(param_name),
        "2": 1,
        "3": field_3_msg,
        "4": dict(type_descriptor),
        "8": int(port_index_int),
    }
    return format_binary_data_hex_text(encode_message(msg))


def _build_listen_param_port_object_from_param_spec(
    *,
    param_spec: Mapping[str, Any],
    param_index: int,
) -> Dict[str, Any]:
    """
    构造 listen node_def['103'] 里的“参数输出口”dict。
    约定与样本一致：slot_index 从 3 开始（0/1/2 被固定输出占用）。
    """
    param_name = str(param_spec.get("param_name") or "").strip()
    type_id_value = param_spec.get("type_id")
    if param_name == "" or not isinstance(type_id_value, int):
        raise ValueError("param_spec missing param_name/type_id")
    return {
        "1": str(param_name),
        "2": 1,
        "3": {"1": 4, "2": 3 + int(param_index)},
        "4": _build_type_descriptor_from_param_spec(param_spec=param_spec),
        # "8" 由调用方填充（port_index）
    }


def _parse_signal_specs_from_json(spec_object: Any) -> List[Dict[str, Any]]:
    if not isinstance(spec_object, Mapping):
        raise TypeError("spec json must be dict")
    signals_value = spec_object.get("signals")
    if not isinstance(signals_value, list):
        raise TypeError("spec json missing signals: expected list")
    signals: List[Dict[str, Any]] = []
    for item in signals_value:
        if isinstance(item, dict):
            signals.append(item)
    return signals


def _parse_type_id(type_value: Any) -> int:
    if isinstance(type_value, int):
        tid = int(type_value)
        if tid == 27:
            raise ValueError("信号参数类型不支持『字典』(type_id=27)")
        return tid
    text = str(type_value or "").strip()
    if text == "":
        raise ValueError("signal param type 不能为空")
    if text.isdigit():
        return int(text)
    # 与 Graph_Generater 对齐：信号参数类型只允许 VARIABLE_TYPES（不支持别名字典写法）
    is_typed_dict, _, _ = parse_typed_dict_alias(text)
    if is_typed_dict:
        raise ValueError(
            f"unsupported signal param type: {text!r}（信号参数不支持别名字典写法）"
        )
    tr = load_graph_generater_type_registry()
    if text not in set(tr.VARIABLE_TYPES):
        raise ValueError(
            f"unsupported signal param type: {text!r}（以 Graph_Generater.engine.type_registry.VARIABLE_TYPES 为准）"
        )
    if text == tr.TYPE_DICT:
        raise ValueError("信号参数类型不支持『字典』(type='字典')")
    return int(map_graph_variable_cn_type_to_var_type_int(text))




