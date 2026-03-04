from __future__ import annotations

import copy
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import ugc_file_tools.struct_def_writeback as struct_writer
from ugc_file_tools.repo_paths import repo_root
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.struct_type_id_registry import (
    resolve_struct_field_type_id,
    validate_struct_type_id_registry_against_genshin_ts_or_raise,
)


@dataclass(frozen=True, slots=True)
class IngameSaveStructImportOptions:
    mode: str  # "merge" | "overwrite"
    include_struct_ids: list[str] | None = None  # 可选：仅导入指定 STRUCT_ID（作用域仍为 共享+项目）


# 结构体字段默认值 message 内，“按 type_id 分流”的 value 容器字段号（经验值，来自样本与模板结构体）。
_TYPE_ID_TO_DEFAULT_CONTAINER_FIELD_NO: Dict[int, int] = {
    1: 11,  # entity
    2: 12,  # guid
    3: 13,  # int32
    4: 14,  # bool
    5: 15,  # float
    6: 16,  # string
    7: 17,  # guid list
    8: 18,  # int list
    9: 19,  # bool list
    12: 22,  # vector3
    13: 23,  # entity list
    17: 27,  # camp
    20: 30,  # config id
    21: 31,  # component id
    22: 32,  # config id list
    23: 33,  # component id list
    24: 34,  # camp list
    25: 35,  # struct (经验值：样本中 struct value_container 常见为 field_35)
    26: 35,  # struct list（同样以 field_35 作为容器；默认值通常为空）
    27: 36,  # dict（默认值通常为空；容器字段号为经验值，缺样本时仅用于避免 crash）
}


def _int_node(value: int) -> Dict[str, int]:
    node: Dict[str, int] = {"int": int(value)}
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF
    return node


def _text_node(text: str) -> Dict[str, str]:
    raw_bytes = str(text).encode("utf-8")
    return {"raw_hex": raw_bytes.hex(), "utf8": str(text)}


def _build_default_string_value_node(text: str) -> Dict[str, Any]:
    # 字符串默认值在结构体字段中通常为 bytes（嵌套 message.field_1:string）
    if str(text) == "":
        return {"raw_hex": "", "utf8": ""}
    nested_bytes = encode_message({"1": str(text)})
    return {"raw_hex": nested_bytes.hex(), "utf8": str(text)}


def _parse_vector3_text(text: str) -> Tuple[float, float, float]:
    parts = str(text).split(",")
    if len(parts) != 3:
        raise ValueError(f"vector3 期望格式 'x,y,z'，但收到: {text!r}")
    return float(parts[0].strip()), float(parts[1].strip()), float(parts[2].strip())


def _build_default_value_container_node(*, type_id: int, value_obj: object) -> Tuple[str, Dict[str, Any]]:
    field_no = _TYPE_ID_TO_DEFAULT_CONTAINER_FIELD_NO.get(int(type_id))
    if field_no is None:
        # 默认值容器字段号缺失：不写入任何默认值容器字段（视为“空默认值”）。
        # 该行为用于确保“结构体定义同步”不会因为少量未覆盖 type_id 阻断整体导入。
        return "", {"raw_hex": ""}
    container_key = f"field_{int(field_no)}"

    # --------- 标量
    if int(type_id) in {1, 2, 3, 17, 20, 21}:
        value_int = int(value_obj) if isinstance(value_obj, (int, float)) else int(str(value_obj or "0").strip() or "0")
        if int(type_id) == 1:
            # entity：空 raw_hex 表示“无初始值”
            return container_key, {"raw_hex": ""} if value_int == 0 else {"message": {"field_1": _int_node(int(value_int))}}
        if int(type_id) == 17:
            # camp：常见为 packed varint raw_hex
            raw_bytes = struct_writer._encode_varint(int(value_int)) if value_int != 0 else b""
            return container_key, {"raw_hex": raw_bytes.hex()}
        return container_key, {"message": {"field_1": _int_node(int(value_int))}}

    if int(type_id) == 4:
        if isinstance(value_obj, bool):
            is_true = bool(value_obj)
        else:
            is_true = str(value_obj or "").strip().lower() in {"1", "true", "yes", "y", "on"}
        if not is_true:
            return container_key, {"raw_hex": ""}
        return container_key, {"message": {"field_1": _int_node(1)}}

    if int(type_id) == 5:
        value_float = float(value_obj) if isinstance(value_obj, (int, float)) else float(str(value_obj or "0").strip() or "0")
        return container_key, {"message": {"field_1": {"fixed32_float": float(value_float)}}}

    if int(type_id) == 6:
        return container_key, _build_default_string_value_node("" if value_obj is None else str(value_obj))

    if int(type_id) == 12:
        if value_obj is None or str(value_obj).strip() == "" or str(value_obj).strip() == "0,0,0":
            raw_bytes = b""
        else:
            x, y, z = _parse_vector3_text(str(value_obj))
            raw_bytes = struct.pack("<fff", float(x), float(y), float(z))
        # 兼容局内存档结构体样本：field_22.message.field_1.raw_hex
        return container_key, {"message": {"field_1": {"raw_hex": raw_bytes.hex()}}}

    # --------- 列表（packed varint）
    if int(type_id) in {7, 8, 9, 22, 23, 24}:
        values: List[int] = []
        if isinstance(value_obj, list):
            for item in value_obj:
                if int(type_id) == 9:
                    if isinstance(item, bool):
                        values.append(1 if item else 0)
                    else:
                        values.append(1 if str(item).strip().lower() in {"1", "true", "yes", "y", "on"} else 0)
                else:
                    values.append(int(item))
        packed = struct_writer._encode_packed_varints(values) if values else b""
        return container_key, {"message": {"field_1": {"raw_hex": packed.hex()}}}

    if int(type_id) == 13:
        # entity list：默认按空列表处理（当前只写回空）
        return container_key, {"raw_hex": ""}

    if int(type_id) in {25, 26, 27}:
        # 结构体/结构体列表/字典：默认值写回形态依赖更多样本。
        # 当前导入链路主要用于“结构体定义同步”，默认值多为 None/空容器，这里先写回空以保证可编码与可导入基础形态。
        return container_key, {"raw_hex": ""}

    raise ValueError(f"未实现该字段类型默认值写回：type_id={int(type_id)}")


def _build_field_entry_message(
    *,
    field_no: int,
    field_name: str,
    param_type: str,
    default_value_obj: object,
) -> Dict[str, Any]:
    # 真源口径（单一真源）：param_type -> VarType(type_id)
    type_id = resolve_struct_field_type_id(str(param_type))

    type_meta = {
        "field_1": _int_node(int(type_id)),
        "field_2": {"raw_hex": ""},
    }

    container_key, container_node = _build_default_value_container_node(
        type_id=int(type_id),
        value_obj=default_value_obj,
    )
    default_value_message: Dict[str, Any] = {
        "field_1": _int_node(int(type_id)),
        "field_2": {"message": copy.deepcopy(type_meta)},
    }
    if container_key.startswith("field_"):
        default_value_message[container_key] = container_node

    field_name_text = str(field_name).strip()
    if field_name_text == "":
        raise ValueError("field_name 不能为空")

    return {
        "field_1": {"message": type_meta},
        "field_3": {"message": default_value_message},
        "field_5": _text_node(field_name_text),
        "field_501": _text_node(field_name_text),
        "field_502": _int_node(int(type_id)),
        "field_503": _int_node(int(field_no)),
    }


def build_field_entry_message(
    *,
    field_no: int,
    field_name: str,
    param_type: str,
    default_value_obj: object,
) -> Dict[str, Any]:
    """
    Public API (no leading underscores).

    Import policy: cross-module imports must not import underscored private names.
    """
    return _build_field_entry_message(
        field_no=field_no,
        field_name=field_name,
        param_type=param_type,
        default_value_obj=default_value_obj,
    )


def _normalize_struct_payload_to_fields(struct_payload: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    返回：struct_name, fields

    支持两种输入 schema：
    - 新版：{type:'Struct', struct_type, struct_name, fields:[{field_name,param_type,default_value:{...}}]}
    - 教学示例旧版：{type:'结构体', struct_ype/struct_type, name, value:[{key,param_type,...}]}
    """
    payload_type = str(struct_payload.get("type") or "").strip()

    if payload_type == "Struct":
        struct_name = str(struct_payload.get("struct_name") or struct_payload.get("name") or "").strip()
        if struct_name == "":
            raise ValueError("STRUCT_PAYLOAD.struct_name 不能为空")

        # 新版：fields=[{field_name,param_type,default_value:{value:...}}]
        fields = struct_payload.get("fields")
        if isinstance(fields, Mapping):
            iterable_fields = list(fields.values())
            mode = "fields"
        elif isinstance(fields, (list, tuple)):
            iterable_fields = list(fields)
            mode = "fields"
        else:
            # 兼容：部分历史文件使用 type='Struct' 但字段仍放在 value=[{key,param_type,value?}]（锻刀当前就是此形态）
            values = struct_payload.get("value")
            if isinstance(values, Mapping):
                iterable_fields = list(values.values())
                mode = "value"
            elif isinstance(values, (list, tuple)):
                iterable_fields = list(values)
                mode = "value"
            else:
                iterable_fields = []
                mode = "fields"
        normalized: List[Dict[str, Any]] = []
        for item in iterable_fields:
            if not isinstance(item, Mapping):
                continue
            if mode == "fields":
                field_name = str(item.get("field_name") or "").strip()
                param_type = str(item.get("param_type") or "").strip()
                default_value = item.get("default_value")
                default_value_obj = None
                if isinstance(default_value, Mapping):
                    default_value_obj = default_value.get("value")
            else:
                # value schema: {key,param_type,value?:{value:...}}
                field_name = str(item.get("key") or item.get("field_name") or "").strip()
                param_type = str(item.get("param_type") or "").strip()
                value_node = item.get("value")
                default_value_obj = None
                if isinstance(value_node, Mapping) and "value" in value_node:
                    default_value_obj = value_node.get("value")
            normalized.append(
                {
                    "field_name": field_name,
                    "param_type": param_type,
                    "default_value_obj": default_value_obj,
                }
            )
        return struct_name, normalized

    if payload_type == "结构体":
        struct_name = str(struct_payload.get("name") or "").strip()
        if struct_name == "":
            raise ValueError("STRUCT_PAYLOAD.name 不能为空")
        values = struct_payload.get("value")
        if values is None:
            values = struct_payload.get("values")
        if isinstance(values, Mapping):
            iterable_values = list(values.values())
        elif isinstance(values, (list, tuple)):
            iterable_values = list(values)
        else:
            # 兼容：历史文件可能缺失 value；视为“空字段结构体”。
            iterable_values = []
        normalized = []
        for item in iterable_values:
            if not isinstance(item, Mapping):
                continue
            field_name = str(item.get("key") or "").strip()
            param_type = str(item.get("param_type") or "").strip()
            if field_name == "":
                continue
            # 旧版局内存档结构体通常不提供 default_value；这里按类型给“空默认值”。
            default_value_obj: object = ""
            if param_type in {"整数", "阵营", "配置ID", "元件ID", "GUID"}:
                default_value_obj = "0"
            elif param_type == "布尔值":
                default_value_obj = "False"
            elif param_type == "浮点数":
                default_value_obj = "0"
            elif param_type == "三维向量":
                default_value_obj = "0,0,0"
            elif param_type.endswith("列表"):
                default_value_obj = []
            normalized.append(
                {
                    "field_name": field_name,
                    "param_type": param_type,
                    "default_value_obj": default_value_obj,
                }
            )
        return struct_name, normalized

    raise ValueError(f"不支持的 STRUCT_PAYLOAD.type：{payload_type!r}")


def normalize_struct_payload_to_fields(struct_payload: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Public API (no leading underscores)."""
    return _normalize_struct_payload_to_fields(struct_payload)


def _decode_struct_name_and_internal_id_from_blob_bytes(blob_bytes: bytes) -> Tuple[str, Optional[int]]:
    decoded = decode_bytes_to_python(blob_bytes)
    if not isinstance(decoded, Mapping):
        return "", None
    wrapper = decoded.get("field_1")
    if not isinstance(wrapper, Mapping):
        return "", None
    struct_message = wrapper.get("message")
    if not isinstance(struct_message, Mapping):
        return "", None
    name = struct_writer._get_utf8_from_text_node(struct_message.get("field_501"))
    internal_id = None
    field_503 = struct_message.get("field_503")
    if isinstance(field_503, Mapping) and isinstance(field_503.get("int"), int):
        internal_id = int(field_503["int"])
    return str(name), internal_id


def _find_template_blob_text(struct_blob_list: Sequence[Any]) -> str:
    """
    优先选择“看起来像局内存档结构体”的模板（struct_message.field_2.int==2），否则回退到第一条。
    """
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
        field_2 = struct_message.get("field_2")
        if isinstance(field_2, Mapping) and field_2.get("int") == 2:
            return format_binary_data_hex_text(blob_bytes)

    for entry in struct_blob_list:
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            return entry
        if isinstance(entry, Mapping):
            return format_binary_data_hex_text(encode_message(entry))
    raise ValueError("root4/10/6 未找到可用的结构体模板 blob（没有可编码条目）")


def _iter_ingame_save_struct_py_files(project_archive_path: Path) -> List[Path]:
    directory = project_archive_path / "管理配置" / "结构体定义" / "局内存档结构体"
    if not directory.is_dir():
        return []
    return sorted([p.resolve() for p in directory.glob("*.py") if p.is_file() and not p.name.startswith("_")])


def _find_graph_generater_root_from_any_path(start_path: Path) -> Path | None:
    resolved = Path(start_path).resolve()
    for parent in [resolved, *resolved.parents]:
        if (parent / "engine").is_dir() and (parent / "assets").is_dir() and (parent / "tools").is_dir():
            return parent
    return None


def _resolve_graph_generater_root(project_archive_path: Path) -> Path:
    found = _find_graph_generater_root_from_any_path(Path(project_archive_path))
    if found is not None:
        return found
    default = repo_root().resolve()
    if default.is_dir() and (default / "engine").is_dir() and (default / "assets").is_dir():
        return default
    raise ValueError(
        "无法定位 Graph_Generater 根目录。"
        f"project_archive={str(Path(project_archive_path).resolve())}。"
        "请确认项目存档目录位于 Graph_Generater/assets/资源库/项目存档/<package_id>/ 下，或在当前工作区中能定位到包含 engine/assets/tools 的目录。"
    )


def _collect_ingame_save_struct_py_files_in_scope(project_archive_path: Path) -> List[Path]:
    """
    对齐 Graph_Generater 的代码级 Schema 作用域：
    - 共享根 + 当前项目存档根
    - 若共享与项目出现同 STRUCT_ID，则以项目定义覆盖共享定义
    """
    project_files = _iter_ingame_save_struct_py_files(Path(project_archive_path))

    gg_root = _resolve_graph_generater_root(Path(project_archive_path))
    shared_dir = gg_root / "assets" / "资源库" / "共享" / "管理配置" / "结构体定义" / "局内存档结构体"
    shared_files = (
        sorted([p.resolve() for p in shared_dir.glob("*.py") if p.is_file() and not p.name.startswith("_")])
        if shared_dir.is_dir()
        else []
    )

    # 先加载共享，再用项目覆盖同 STRUCT_ID（避免重复导入）
    by_id: Dict[str, Path] = {}
    for p in shared_files:
        struct_id, _struct_type, _payload = _load_struct_payload_from_py(Path(p))
        by_id[str(struct_id)] = Path(p)
    for p in project_files:
        struct_id, _struct_type, _payload = _load_struct_payload_from_py(Path(p))
        by_id[str(struct_id)] = Path(p)

    # 稳定排序：按路径
    return sorted([p.resolve() for p in by_id.values()], key=lambda x: x.as_posix())


def collect_ingame_save_struct_py_files_in_scope(project_archive_path: Path) -> List[Path]:
    """Public API (no leading underscores)."""
    return _collect_ingame_save_struct_py_files_in_scope(project_archive_path)


def _load_struct_payload_from_py(path: Path) -> Tuple[str, str, Dict[str, Any]]:
    env = runpy.run_path(str(path))
    struct_id = env.get("STRUCT_ID")
    struct_type = env.get("STRUCT_TYPE")
    payload = env.get("STRUCT_PAYLOAD")
    if not isinstance(struct_id, str) or not struct_id.strip():
        raise ValueError(f"STRUCT_ID missing/invalid: {str(path)}")
    if not isinstance(struct_type, str) or not struct_type.strip():
        raise ValueError(f"STRUCT_TYPE missing/invalid: {str(path)}")
    if not isinstance(payload, dict):
        raise ValueError(f"STRUCT_PAYLOAD missing/invalid: {str(path)}")
    return str(struct_id), str(struct_type), payload


def import_ingame_save_structs_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: IngameSaveStructImportOptions,
    bootstrap_template_gil_file_path: Path | None = None,
) -> Dict[str, Any]:
    # 工程化护栏：若存在 genshin-ts 导出的 VarType 报告，则对齐校验本地映射表，避免漂移。
    validate_struct_type_id_registry_against_genshin_ts_or_raise()
    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    mode = str(options.mode or "").strip().lower()
    if mode not in {"merge", "overwrite"}:
        raise ValueError(f"unsupported mode: {mode!r}")

    struct_py_files = _collect_ingame_save_struct_py_files_in_scope(project_path)
    if not struct_py_files:
        raise ValueError(f"项目存档缺少局内存档结构体定义：{str(project_path)}")

    wanted_ids = [str(x or "").strip() for x in list(getattr(options, "include_struct_ids", None) or [])]
    wanted_ids = [x for x in wanted_ids if x]
    if wanted_ids:
        by_id: Dict[str, Path] = {}
        for p in struct_py_files:
            env = runpy.run_path(str(p))
            sid = env.get("STRUCT_ID")
            if isinstance(sid, str) and sid.strip():
                by_id[str(sid).strip()] = Path(p)
        missing = sorted(list(set(wanted_ids) - set(by_id.keys())), key=lambda t: t.casefold())
        if missing:
            raise ValueError(f"选择的局内存档结构体不存在于当前作用域（共享+项目）：{missing}")
        struct_py_files = [by_id[sid] for sid in wanted_ids]

    raw_dump_object = struct_writer._dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    node_graph_root = struct_writer._ensure_path_dict(payload_root, "10")
    struct_blob_list = struct_writer._ensure_path_list_allow_scalar(node_graph_root, "6")
    if not struct_blob_list:
        bootstrap_path = Path(bootstrap_template_gil_file_path).resolve() if bootstrap_template_gil_file_path is not None else None
        if bootstrap_path is None:
            raise ValueError(
                "目标 .gil 的 root4/10/6 为空，无法导入局内存档结构体（缺少模板）。"
                "请提供 --bootstrap-template-gil 指向一份包含结构体系统模板的 .gil（例如 ugc_file_tools/builtin_resources/seeds/ingame_save_structs_bootstrap.gil）。"
            )
        if not bootstrap_path.is_file():
            raise FileNotFoundError(str(bootstrap_path))

        bootstrap_dump_object = struct_writer._dump_gil_to_raw_json_object(bootstrap_path)
        bootstrap_payload_root = bootstrap_dump_object.get("4")
        if not isinstance(bootstrap_payload_root, dict):
            raise ValueError("bootstrap template 缺少根字段 '4'（期望为 dict）。")
        bootstrap_node_graph_root = struct_writer._ensure_path_dict(bootstrap_payload_root, "10")
        bootstrap_struct_blob_list = struct_writer._ensure_path_list_allow_scalar(bootstrap_node_graph_root, "6")
        if not bootstrap_struct_blob_list:
            raise ValueError("bootstrap template 的 root4/10/6 为空，无法提供结构体模板。")

        # 将模板 struct blobs 复制到目标存档（作为后续导入/克隆的基底）
        struct_blob_list.extend(copy.deepcopy(bootstrap_struct_blob_list))

        # 若目标存档缺少 node_defs（或为空），也从模板拷贝一份，确保后续能生成结构体节点定义
        node_defs_candidate = node_graph_root.get("2")
        if not isinstance(node_defs_candidate, list) or not node_defs_candidate:
            bootstrap_node_defs = bootstrap_node_graph_root.get("2")
            if not isinstance(bootstrap_node_defs, list) or not bootstrap_node_defs:
                raise ValueError("bootstrap template 的 root4/10/2 缺失或为空，无法提供节点定义模板。")
            node_graph_root["2"] = copy.deepcopy(bootstrap_node_defs)

    node_defs = node_graph_root.get("2")
    if not isinstance(node_defs, list):
        raise ValueError("root4/10/2 缺失或不是 list，无法写入结构体节点定义注册。")

    # --------- 解析现有结构体（用 name 做弱匹配，避免每次导入都产生重复）
    existing_struct_id_to_index: Dict[int, int] = {}
    existing_struct_name_to_id_and_index: Dict[str, Tuple[int, int, Optional[int]]] = {}
    existing_struct_ids: List[int] = []
    for index, entry in enumerate(struct_blob_list):
        blob_bytes: bytes | None = None
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(entry)
        elif isinstance(entry, Mapping):
            blob_bytes = encode_message(entry)
        else:
            continue

        struct_id_int = struct_writer._decode_struct_id_from_blob_bytes(blob_bytes)
        struct_name, internal_id = _decode_struct_name_and_internal_id_from_blob_bytes(blob_bytes)
        existing_struct_id_to_index[int(struct_id_int)] = int(index)
        existing_struct_ids.append(int(struct_id_int))
        if str(struct_name).strip():
            existing_struct_name_to_id_and_index[str(struct_name).strip()] = (int(struct_id_int), int(index), internal_id)

    reserved_ids = struct_writer._collect_reserved_struct_ids_from_payload_root(payload_root)
    existing_internal_ids = struct_writer._collect_existing_struct_internal_ids(struct_blob_list)
    next_internal_id = (max(existing_internal_ids) + 2) if existing_internal_ids else 2

    # node_type_id 分配策略复用现有逻辑：只要新增了某个 struct，就补齐对应 3 个节点定义并避免冲突
    existing_node_type_ids = struct_writer._collect_existing_node_type_ids(node_defs)
    next_node_type_id = (max(existing_node_type_ids) + 1) if existing_node_type_ids else 1610612740

    # 选择一个现有结构体作为“节点定义模板”
    # 注意：跨模块复用必须走公开 API（无下划线）。
    from .struct_definitions_importer import choose_template_struct_id_for_node_defs, ensure_struct_node_defs

    template_struct_id_for_node_defs = choose_template_struct_id_for_node_defs(
        node_defs=node_defs,
        existing_struct_ids=None,
    )

    template_blob_text = _find_template_blob_text(struct_blob_list)
    template_blob_bytes = parse_binary_data_hex_text(template_blob_text)
    decoded_template = decode_bytes_to_python(template_blob_bytes)
    if not isinstance(decoded_template, dict):
        raise ValueError("template struct blob decode result is not dict")

    added_struct_names: List[str] = []
    replaced_struct_names: List[str] = []
    skipped_struct_names: List[str] = []
    imported_structs: List[Dict[str, Any]] = []

    for py_path in struct_py_files:
        source_struct_id, source_struct_type, source_payload = _load_struct_payload_from_py(py_path)
        struct_name, normalized_fields = _normalize_struct_payload_to_fields(source_payload)

        # 局内存档结构体导入：强制视为 ingame_save（写回时会设置 struct_message.field_2=2）
        _ = source_struct_id
        _ = source_struct_type

        existing = existing_struct_name_to_id_and_index.get(struct_name)
        target_struct_id: Optional[int] = None
        target_struct_internal_id: Optional[int] = None
        existing_index: Optional[int] = None
        if existing is not None:
            target_struct_id, existing_index, target_struct_internal_id = existing

        if existing_index is not None:
            if mode == "merge":
                skipped_struct_names.append(struct_name)
                continue
            # overwrite：复用已存在的 struct_id 与 internal_id
            if target_struct_id is None:
                raise ValueError("internal error: existing struct has no struct_id")
            if target_struct_internal_id is None:
                # 兼容样本中 internal_id 缺失的情况
                target_struct_internal_id = int(next_internal_id)
                next_internal_id += 2
        else:
            # 新增：分配新的 struct_id / internal_id
            chosen: Optional[int] = None
            for candidate in reserved_ids:
                if int(candidate) not in set(existing_struct_ids):
                    chosen = int(candidate)
                    break
            target_struct_id = chosen if chosen is not None else struct_writer._choose_next_struct_id(existing_struct_ids)
            existing_struct_ids.append(int(target_struct_id))

            target_struct_internal_id = int(next_internal_id)
            next_internal_id += 2

        # --------- 构造新的 decoded blob（基于模板克隆，替换 struct_id/name/fields）
        new_decoded = copy.deepcopy(decoded_template)
        for wrapper_key in ("field_1", "field_2"):
            wrapper = new_decoded.get(wrapper_key)
            if not isinstance(wrapper, dict):
                raise ValueError(f"template missing {wrapper_key} wrapper")
            struct_message = wrapper.get("message")
            if not isinstance(struct_message, dict):
                raise ValueError(f"template missing {wrapper_key}.message")

            struct_id_node = struct_message.get("field_1")
            if not isinstance(struct_id_node, dict):
                raise ValueError("template missing struct_message.field_1")
            struct_writer._set_int_node(struct_id_node, int(target_struct_id))

            struct_name_node = struct_message.get("field_501")
            if not isinstance(struct_name_node, dict):
                raise ValueError("template missing struct_message.field_501")
            struct_writer._set_text_node_utf8(struct_name_node, str(struct_name).strip())

            # 标识为 ingame_save：struct_message.field_2.int = 2
            field_2_node = struct_message.get("field_2")
            if field_2_node is None:
                field_2_node = {}
                struct_message["field_2"] = field_2_node
            if not isinstance(field_2_node, dict):
                raise ValueError("struct_message.field_2 is not dict")
            struct_writer._set_int_node(field_2_node, 2)

            struct_internal_id_node = struct_message.get("field_503")
            if struct_internal_id_node is None:
                struct_internal_id_node = {}
                struct_message["field_503"] = struct_internal_id_node
            if not isinstance(struct_internal_id_node, dict):
                raise ValueError("struct_message.field_503 is not dict")
            struct_writer._set_int_node(struct_internal_id_node, int(target_struct_internal_id))

            if not normalized_fields:
                struct_message.pop("field_3", None)
            else:
                field_entries: List[Dict[str, Any]] = []
                for field_no, field in enumerate(normalized_fields, start=1):
                    field_name_text = str(field.get("field_name") or "").strip()
                    param_type_text = str(field.get("param_type") or "").strip()
                    default_value_obj = field.get("default_value_obj")
                    field_msg = _build_field_entry_message(
                        field_no=int(field_no),
                        field_name=field_name_text,
                        param_type=param_type_text,
                        default_value_obj=default_value_obj,
                    )
                    field_entries.append({"message": field_msg})
                struct_message["field_3"] = field_entries

        # 防御性：归一化 decode_gil 的非法 field_0
        struct_writer._sanitize_decoded_invalid_field0_message_nodes(new_decoded)
        dump_json_message = struct_writer._decoded_field_map_to_dump_json_message(new_decoded)
        blob_bytes = encode_message(dump_json_message)
        blob_text = format_binary_data_hex_text(blob_bytes)

        if existing_index is not None:
            struct_blob_list[int(existing_index)] = blob_text
            replaced_struct_names.append(struct_name)
        else:
            struct_blob_list.append(blob_text)
            existing_struct_id_to_index[int(target_struct_id)] = len(struct_blob_list) - 1
            added_struct_names.append(struct_name)

            next_node_type_id = ensure_struct_node_defs(
            node_defs=node_defs,
            struct_id=int(target_struct_id),
            template_struct_id=int(template_struct_id_for_node_defs),
            next_node_type_id=int(next_node_type_id),
        )

        imported_structs.append(
            {
                "struct_name": struct_name,
                "struct_id_int": int(target_struct_id),
                "struct_internal_id_int": int(target_struct_internal_id),
                "source_py": str(py_path),
            }
        )

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "mode": mode,
        "bootstrap_template_gil": (str(Path(bootstrap_template_gil_file_path).resolve()) if bootstrap_template_gil_file_path is not None else None),
        "source_struct_py_files_count": len(struct_py_files),
        "template_struct_id_for_node_defs": int(template_struct_id_for_node_defs),
        "imported_structs": imported_structs,
        "added_struct_names": sorted(set(added_struct_names)),
        "replaced_struct_names": sorted(set(replaced_struct_names)),
        "skipped_struct_names": sorted(set(skipped_struct_names)),
        "notes": [
            "本导入器当前不写回结构体页签注册（root4/6/*），仅写回 root4/10/6 与 root4/10/2。",
            "若目标存档需要页签注册才能在编辑器可见，请改用已实现的结构体 decoded-json 导入流程，或后续补齐对应注册逻辑。",
        ],
    }


__all__ = [
    "IngameSaveStructImportOptions",
    "import_ingame_save_structs_from_project_archive_to_gil",
]


