from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Sequence

import ugc_file_tools.struct_def_writeback as struct_writer
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)


def _find_basic_template_blob_text(struct_blob_list: Sequence[Any]) -> str:
    """优先选择“看起来像基础结构体”的模板（struct_message.field_2.int != 2），否则失败。

    说明：
    - 局内存档结构体使用 `field_2.int == 2` 作为类型标记；
    - 基础结构体通常不存在该标记或不等于 2；
    - 若 base .gil 中只包含局内存档结构体模板，直接用其作为基础结构体模板会导致导入失败或结构漂移。
    """
    from ugc_file_tools.decode_gil import decode_bytes_to_python

    for entry in struct_blob_list:
        blob_bytes: bytes | None = None
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(entry)
        elif isinstance(entry, Mapping):
            blob_bytes = encode_message(dict(entry))
        else:
            continue

        decoded = decode_bytes_to_python(blob_bytes)
        if not isinstance(decoded, Mapping):
            continue
        wrapper = decoded.get("field_1") or decoded.get("field_2")
        if not isinstance(wrapper, Mapping):
            continue
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, Mapping):
            continue
        field_2 = struct_message.get("field_2")
        if isinstance(field_2, Mapping) and field_2.get("int") == 2:
            continue
        # 统一返回 <binary_data> 形式（便于后续复用 decode_path）
        return format_binary_data_hex_text(blob_bytes)

    # 兜底：若目标存档只有局内存档结构体模板，也允许继续导入基础结构体。
    # 导入时会显式移除/清理 struct_message.field_2（避免把基础结构体错误标记为 ingame_save）。
    for entry in struct_blob_list:
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            return str(entry)
        if isinstance(entry, Mapping):
            return format_binary_data_hex_text(encode_message(dict(entry)))

    raise ValueError("目标 .gil 的 root4/10/6 缺少可用结构体模板（结构体段为空或结构不符合预期）。")


def _decode_struct_template_to_decoded_field_map(*, blob_text: str) -> Dict[str, Any]:
    from ugc_file_tools.decode_gil import decode_bytes_to_python

    blob_bytes = parse_binary_data_hex_text(blob_text)
    decoded = decode_bytes_to_python(blob_bytes)
    if not isinstance(decoded, dict):
        raise ValueError("struct template blob 解码失败（不是 dict）")
    return decoded


def _build_decoded_blob_from_basic_struct_py(
    *,
    struct_id_int: int,
    struct_name: str,
    struct_payload: Mapping[str, Any],
    template_decoded: Mapping[str, Any],
    struct_internal_id_int: int,
    field_prototypes_source_decoded: Mapping[str, Any] | None = None,
    source_id_to_target_struct_id: Mapping[str, int] | None = None,
    allocate_next_struct_ref_id: Callable[[], int] | None = None,
) -> Dict[str, Any]:
    """将代码级 STRUCT_PAYLOAD（基础结构体）转换为 decoded field-map（供 encode_message 写回）。"""
    import copy

    from ugc_file_tools.project_archive_importer.ingame_save_structs_importer import (
        build_field_entry_message as _build_field_entry_message,
        normalize_struct_payload_to_fields as _normalize_struct_payload_to_fields,
    )
    from ugc_file_tools.struct_type_id_registry import (
        try_resolve_struct_field_type_id,
        validate_struct_type_id_registry_against_genshin_ts_or_raise,
    )

    validate_struct_type_id_registry_against_genshin_ts_or_raise()

    normalized_name, normalized_fields = _normalize_struct_payload_to_fields(struct_payload)
    name_text = str(struct_name or "").strip() or str(normalized_name or "").strip()
    if name_text == "":
        raise ValueError("结构体名称为空（STRUCT_PAYLOAD.struct_name/name）")

    def _normalize_default_value_obj(*, param_type: str, default_value_obj: object) -> object:
        """
        基础结构体默认值策略（保守）：
        - 代码级定义如果没有显式默认值，则写入该类型的“空/零”默认值；
          这样可以避免把模板结构体（例如 struct_all_supported）里的示例默认值继承到新结构体，
          从而触发真源更严格的导入校验。
        - 对结构体/结构体列表/字典：当前不尝试写入“引用默认值”（例如 default.structId），
          因为这些 ID 在项目存档中是 Graph_Generater 资源 ID，不等价于真源 struct_id。
        """
        t = str(param_type or "").strip()
        # 结构体/结构体列表/字典：保留原始 default（通常携带 structId 等），后续在写回阶段做真源 struct_id 映射。
        if t in {"结构体", "结构体列表", "字典"}:
            return default_value_obj
        if default_value_obj is not None:
            return default_value_obj
        if t in {"整数", "阵营", "配置ID", "元件ID", "GUID"}:
            return "0"
        if t == "布尔值":
            return False
        if t == "浮点数":
            return "0"
        if t == "字符串":
            return ""
        if t == "三维向量":
            return "0,0,0"
        if t.endswith("列表"):
            return []
        return None

    new_decoded: Dict[str, Any] = copy.deepcopy(dict(template_decoded))

    def _get_struct_message(decoded: Dict[str, Any], wrapper_key: str) -> Dict[str, Any] | None:
        wrapper = decoded.get(wrapper_key)
        if not isinstance(wrapper, dict):
            return None
        msg = wrapper.get("message")
        if not isinstance(msg, dict):
            return None
        return msg

    def _extract_field_entry_prototypes(*, decoded: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        """从模板结构体中提取“按 type_id 分组”的字段 entry 原型，避免手工拼结构导致真源导入失败。"""
        struct_msg = _get_struct_message(decoded, "field_1") or _get_struct_message(decoded, "field_2")
        if struct_msg is None:
            return {}
        by_type: Dict[int, Dict[str, Any]] = {}
        for entry in struct_writer._iter_field_entries(struct_msg):
            entry_kind, field_msg = struct_writer._decode_field_entry(entry)
            _ = entry_kind
            if not isinstance(field_msg, dict):
                continue
            field_502 = field_msg.get("field_502")
            type_id_int: int | None = None
            if isinstance(field_502, dict) and isinstance(field_502.get("int"), int):
                type_id_int = int(field_502["int"])
            if type_id_int is None:
                continue
            # 同 type_id 若出现多次，保留第一条即可（结构一致）
            by_type.setdefault(int(type_id_int), copy.deepcopy(field_msg))
        return by_type

    prototypes_by_type_id = _extract_field_entry_prototypes(
        decoded=dict(field_prototypes_source_decoded or template_decoded)
    )

    for wrapper_key in ("field_1", "field_2"):
        wrapper = new_decoded.get(wrapper_key)
        if not isinstance(wrapper, dict):
            continue
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, dict):
            continue

        struct_id_node = struct_message.get("field_1")
        if not isinstance(struct_id_node, dict):
            raise ValueError("模板结构体缺少 struct_message.field_1")
        struct_writer._set_int_node(struct_id_node, int(struct_id_int))

        struct_name_node = struct_message.get("field_501")
        if not isinstance(struct_name_node, dict):
            raise ValueError("模板结构体缺少 struct_message.field_501")
        struct_writer._set_text_node_utf8(struct_name_node, str(name_text).strip())

        # 基础结构体：不写入/不保留 ingame_save 标记（field_2.int=2）。
        # 若模板来自局内存档结构体（field_2==2），这里强制移除该字段，避免把基础结构体错误标记为 ingame_save。
        field_2_node = struct_message.get("field_2")
        if isinstance(field_2_node, dict) and field_2_node.get("int") == 2:
            struct_message.pop("field_2", None)

        internal_id_node = struct_message.get("field_503")
        if internal_id_node is None:
            internal_id_node = {}
            struct_message["field_503"] = internal_id_node
        if not isinstance(internal_id_node, dict):
            raise ValueError("struct_message.field_503 不是 dict")
        struct_writer._set_int_node(internal_id_node, int(struct_internal_id_int))

        if not normalized_fields:
            struct_message.pop("field_3", None)
        else:
            field_entries: List[Dict[str, Any]] = []
            for idx, field in enumerate(normalized_fields, start=1):
                field_name = str(field.get("field_name") or "").strip()
                param_type = str(field.get("param_type") or "").strip()
                default_value_obj = _normalize_default_value_obj(
                    param_type=param_type,
                    default_value_obj=field.get("default_value_obj"),
                )

                type_id = try_resolve_struct_field_type_id(param_type)
                if type_id is None:
                    # 兜底：复用现有构造器（但仍会缺少一些真源细节）
                    field_msg = _build_field_entry_message(
                        field_no=int(idx),
                        field_name=field_name,
                        param_type=param_type,
                        default_value_obj=default_value_obj,
                    )
                    field_entries.append({"message": field_msg})
                    continue

                proto = prototypes_by_type_id.get(int(type_id))
                if proto is None:
                    field_msg = _build_field_entry_message(
                        field_no=int(idx),
                        field_name=field_name,
                        param_type=param_type,
                        default_value_obj=default_value_obj,
                    )
                    field_entries.append({"message": field_msg})
                    continue

                field_msg = copy.deepcopy(proto)

                # 更新字段名
                for key in ("field_5", "field_501"):
                    node = field_msg.get(key)
                    if node is None:
                        node = {}
                        field_msg[key] = node
                    if not isinstance(node, dict):
                        raise ValueError(f"field name node {key} 不是 dict")
                    struct_writer._set_text_node_utf8(node, field_name)

                # 更新字段编号（field_no）
                field_503 = field_msg.get("field_503")
                if field_503 is None:
                    field_503 = {}
                    field_msg["field_503"] = field_503
                if not isinstance(field_503, dict):
                    raise ValueError("field_503 不是 dict")
                struct_writer._set_int_node(field_503, int(idx))

                # 默认值：严格沿用模板字段原型的“容器字段号 + 结构形态”，但绝不继承模板里的示例默认值。
                # 规则：先将容器清空为“空默认值”，再按代码级默认值（或类型空值）写入。
                _container_key, container, _inner = struct_writer._get_type_value_container(field_msg)
                if not isinstance(container, dict):
                    raise ValueError(
                        f"字段默认值容器不是 dict（struct_id={int(struct_id_int)} field={field_name!r} type_id={int(type_id)}）"
                    )

                # 默认值写回规则（对齐 struct_def_writeback 的写法）：
                # - 不主动 clear() 容器（除 bool setter 自己会 clear），避免破坏 message 形态；
                # - 通过“类型空值归一化”保证 default_value_obj 非空，从而覆盖模板默认值。
                if default_value_obj is not None:
                    if int(type_id) in {3, 20, 21}:
                        value_int = (
                            int(default_value_obj)
                            if isinstance(default_value_obj, (int, float))
                            else int(str(default_value_obj or "0").strip() or "0")
                        )
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        struct_writer._set_default_int_in_message_container(container, int(value_int))
                    elif int(type_id) == 4:
                        if isinstance(default_value_obj, bool):
                            is_true = bool(default_value_obj)
                        else:
                            is_true = str(default_value_obj or "").strip().lower() in {"1", "true", "yes", "y", "on"}
                        struct_writer._set_default_bool_node(container, bool(is_true))
                    elif int(type_id) == 5:
                        value_float = (
                            float(default_value_obj)
                            if isinstance(default_value_obj, (int, float))
                            else float(str(default_value_obj or "0").strip() or "0")
                        )
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        struct_writer._set_default_float_in_message_container(container, float(value_float))
                    elif int(type_id) == 6:
                        struct_writer._set_default_string_node(container, str(default_value_obj))
                    elif int(type_id) in {7, 8, 22, 23, 24}:
                        if isinstance(default_value_obj, (list, tuple)):
                            values = [int(v) for v in default_value_obj]
                        else:
                            raise ValueError(
                                f"packed varint list default 期望 list/tuple（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {type(default_value_obj).__name__}"
                            )
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        struct_writer._set_default_packed_varint_list(container, values)
                    elif int(type_id) == 9:
                        if isinstance(default_value_obj, (list, tuple)):
                            values_bool: List[int] = []
                            for v in default_value_obj:
                                if isinstance(v, bool):
                                    values_bool.append(1 if v else 0)
                                else:
                                    values_bool.append(1 if str(v).strip().lower() in {"1", "true", "yes", "y", "on"} else 0)
                        else:
                            raise ValueError(
                                f"bool list default 期望 list/tuple（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {type(default_value_obj).__name__}"
                            )
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        struct_writer._set_default_packed_varint_list(container, values_bool)
                    elif int(type_id) == 10:
                        if isinstance(default_value_obj, (list, tuple)):
                            values_f = [float(v) for v in default_value_obj]
                        else:
                            raise ValueError(
                                f"float list default 期望 list/tuple（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {type(default_value_obj).__name__}"
                            )
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        struct_writer._set_default_float_list(container, values_f)
                    elif int(type_id) == 11:
                        if isinstance(default_value_obj, (list, tuple)):
                            values_s = [str(v) for v in default_value_obj]
                        else:
                            raise ValueError(
                                f"string list default 期望 list/tuple（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {type(default_value_obj).__name__}"
                            )
                        struct_writer._set_default_string_list_raw(container, values_s)
                    elif int(type_id) == 12:
                        text = str(default_value_obj).strip()
                        if text == "" or text == "0,0,0":
                            x, y, z = 0.0, 0.0, 0.0
                        else:
                            parts = [p.strip() for p in text.split(",")]
                            if len(parts) != 3:
                                raise ValueError(
                                    f"vector3 default 期望 'x,y,z'（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {text!r}"
                                )
                            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        message = container.get("message")
                        if not isinstance(message, dict):
                            message = {}
                            container.pop("raw_hex", None)
                            container["message"] = message
                        field_1 = message.get("field_1")
                        if not isinstance(field_1, dict):
                            field_1 = {}
                            message["field_1"] = field_1
                        vec_msg = field_1.get("message")
                        if not isinstance(vec_msg, dict):
                            vec_msg = {}
                            field_1["message"] = vec_msg
                        struct_writer._set_default_vector3_in_message_container(container, x, y, z)
                    elif int(type_id) in {25, 26}:
                        # 结构体 / 结构体列表：default_value_obj 通常形如 {"structId": "<GG_STRUCT_ID>", "value": ...}
                        if not isinstance(source_id_to_target_struct_id, Mapping):
                            raise ValueError("内部错误：source_id_to_target_struct_id 缺失，无法处理结构体引用默认值。")
                        if not isinstance(default_value_obj, Mapping):
                            raise ValueError(
                                f"结构体默认值期望 dict（struct_id={int(struct_id_int)} field={field_name!r}），但收到: {type(default_value_obj).__name__}"
                            )
                        raw_struct_id = str(default_value_obj.get("structId") or "").strip()
                        if raw_struct_id == "":
                            # 没有显式 structId：写空默认值
                            pass
                        else:
                            target_sid = source_id_to_target_struct_id.get(raw_struct_id)
                            if not isinstance(target_sid, int):
                                raise ValueError(
                                    f"结构体默认值引用了未知 structId={raw_struct_id!r}（无法映射为真源 struct_id）。"
                                    f"field={field_name!r} struct={name_text!r}"
                                )
                            # template: container.message.field_501 是被引用的 struct_id
                            message = container.get("message")
                            if not isinstance(message, dict):
                                message = {}
                                container.pop("raw_hex", None)
                                container["message"] = message
                            field_501 = message.get("field_501")
                            if not isinstance(field_501, dict):
                                field_501 = {}
                                message["field_501"] = field_501
                            struct_writer._set_int_node(field_501, int(target_sid))

                            # 清理模板中的示例默认值，避免携带“测试数据/示例 ref_id”导致真源校验失败。
                            # - type_id=26（结构体列表）：模板通常自带若干示例 item（且每个 item 内含 ref_id），必须清空为 []。
                            # - type_id=25（结构体）：模板通常自带一份示例 struct value，清空为“无默认值”即可。
                            if int(type_id) == 26:
                                message["field_1"] = []
                            if int(type_id) == 25:
                                message["field_1"] = {"raw_hex": ""}

                            if int(type_id) == 25:
                                # template: message.field_502.message.field_4 是 ugc_ref_id_int（必须全局唯一）
                                if allocate_next_struct_ref_id is None:
                                    raise ValueError("内部错误：allocate_next_struct_ref_id 缺失，无法分配结构体引用 id。")
                                field_502 = message.get("field_502")
                                if not isinstance(field_502, dict):
                                    field_502 = {"message": {}}
                                    message["field_502"] = field_502
                                f502_msg = field_502.get("message")
                                if not isinstance(f502_msg, dict):
                                    f502_msg = {}
                                    field_502["message"] = f502_msg
                                field_4 = f502_msg.get("field_4")
                                if not isinstance(field_4, dict):
                                    field_4 = {}
                                    f502_msg["field_4"] = field_4
                                struct_writer._set_int_node(field_4, int(allocate_next_struct_ref_id()))
                    else:
                        pass

                field_entries.append({"message": field_msg})

            struct_message["field_3"] = field_entries

    return new_decoded

