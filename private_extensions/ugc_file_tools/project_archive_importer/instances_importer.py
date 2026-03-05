from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from ugc_file_tools.gia_export.templates import build_component_template_root_id_int
from ugc_file_tools.gil.name_unwrap import normalize_dump_json_name_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.project_archive_importer.custom_variable_writeback import (
    load_level_variable_payloads_by_file_id,
    upsert_custom_variables_from_level_variable_payloads,
)


@dataclass(frozen=True, slots=True)
class InstancesImportOptions:
    mode: str = "overwrite"  # "merge" | "overwrite"
    include_instance_json_files: List[Path] | None = None  # 仅写回指定实体摆放文件（绝对路径，指向项目存档内 实体摆放/*.json）
    # 同名冲突策略（导出中心 selection-json 透传；按 instance_json_file 精确匹配）。
    # item schema（dict）：
    # - instance_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_instance_name: str（仅 action="add" 时需要）
    instance_conflict_resolutions: List[Dict[str, str]] | None = None


_ALL_DIGITS_RE = re.compile(r"^\d+$")


def _bump_root_id_int_0x4040(value: int) -> int:
    """
    对齐 templates_importer 的 bump 策略：low16 固定在 0x4000~0x7FFF（<0x8000）。

    用途：当“稳定哈希 ID（crc32 low14）”发生冲突时，在同一次写回中生成一个不冲突的备选 ID。
    """
    base = int(value) & 0xFFFF0000
    low = int(value) & 0xFFFF
    low2 = int(low) + 1
    if low2 > 0x7FFF:
        low2 = 0x4000
    if low2 < 0x4000:
        low2 = 0x4000
    return int(base | int(low2))


def _coerce_numeric_id_int_allow_string(*, id_text: str, used_id_ints: set[int], label: str) -> int:
    """
    `.gil` 的 root4/5/1(instance_id) 与 entry['2'][0]['1'](template_id) 都是 int。

    兼容项目存档中的“非数字 ID”（如 shape_editor_* / instance_*__<pkg>）：
    - 数字：直接 int(text)
    - 非数字：按 `.gia` 导出同口径构造稳定的 0x4040xxxx（low16<0x8000）ID，并在冲突时 bump
    """
    text = str(id_text or "").strip()
    if text == "":
        raise ValueError(f"{label} is empty")
    if _ALL_DIGITS_RE.match(text):
        value = int(text)
    else:
        value = int(build_component_template_root_id_int(template_key=text))
        while int(value) in used_id_ints:
            value = _bump_root_id_int_0x4040(int(value))
    used_id_ints.add(int(value))
    return int(value)


_BUILTIN_EXEMPLAR_INSTANCE_ENTRY_TYPE_10005018: Dict[str, Any] = {
    # 从“可见实体样本（空模型载体）”抽取的最小可克隆实例形态（template_type_code=10005018）。
    #
    # 说明：
    # - 新增实例需要克隆一个“同 template_type 的样本 entry”，否则 section6/7 等结构差异会导致进游戏不可见；
    # - seed/test2.gil 可能包含多种 10005018 用途的实例样本（场景/武器/路标等）；为避免克隆夹带特效/挂载，
    #   这里提供一个对齐真源“空模型实体”的 canonical exemplar，用于新增 10005018 实例时固定口径。
    #
    # 注意：写回时会覆写以下关键字段：
    # - entry['1'] instance_id
    # - entry['2'] template 引用
    # - entry['5'] name meta
    # - entry['6']/id=1 transform（pos/rot/scale/guid）
    # - entry['8'] template_type_code
    "1": 1077936129,
    "2": {"1": 10005018, "2": 1},
    "5": [
        {"1": 1, "11": "空模型"},
        {"1": 13, "22": "<binary_data> "},
        {"1": 14, "23": {"1": "MPActionGroup"}},
        {"1": 38, "48": {"1": 1.0}},
        # 对齐真源样本“只有一个空模型实体的存档.gil”：无装饰物时 meta40.field50 为 empty bytes（而不是 message）。
        {"1": 40, "50": "<binary_data> "},
        {"1": 61, "65": "<binary_data> "},
        {"1": 62, "66": "<binary_data> "},
        {"1": 19, "28": "<binary_data> "},
        {"1": 20, "29": "<binary_data> "},
        {"1": 52, "62": "<binary_data> "},
    ],
    "6": [
        {
            "1": 1,
            "11": {
                "1": {"1": 3.288931369781494, "2": 3.288931369781494, "3": -1.1920928955078125e-06},
                "2": "<binary_data> ",
                "3": {"1": 1.0, "2": 1.0, "3": 1.0},
                "501": 4294967295,
            },
        },
        {"1": 2, "12": "<binary_data> "},
        {"1": 3, "13": "<binary_data> "},
        {"1": 4, "14": {"1": 1}},
        {"1": 5, "15": {"1": 1, "2": 1}},
        {"1": 6, "16": "<binary_data> "},
        {
            "1": 7,
            "17": {
                "1": 1000.0,
                "3": 500.0,
                "4": 1,
                "5": 1,
                "6": {"2": 10200002},
                "8": 0.10000000149011612,
                "9": 0.10000000149011612,
                "10": 0.10000000149011612,
                "11": 0.10000000149011612,
                "12": 0.10000000149011612,
                "13": 0.10000000149011612,
                "14": 0.10000000149011612,
                "15": 0.10000000149011612,
            },
        },
        {"1": 8, "18": {"1": 1, "501": 1}},
        {
            "1": 11,
            "21": {
                "1": {
                    "1": "GI_RootNode",
                    "2": "<binary_data> ",
                    "3": "<binary_data> ",
                    "502": "中心原点",
                    "504": 1,
                    "505": "RootNode",
                }
            },
        },
        {"1": 12, "22": {"501": 1}},
        {"1": 16, "26": {"2": {"1": 4, "10": "<binary_data> ", "12": "<binary_data> ", "13": "<binary_data> "}}},
        {"1": 17, "27": "<binary_data> "},
        {"1": 19, "29": {"1": 1}},
    ],
    "7": [
        {"1": 1, "2": 1, "11": "<binary_data> "},
        {"1": 3, "2": 1, "13": "<binary_data> "},
        {"1": 6, "2": 1, "16": "<binary_data> "},
        {"1": 14, "2": 1, "24": "<binary_data> "},
        {"1": 19, "2": 1, "29": "<binary_data> "},
        {
            "1": 18,
            "2": 1,
            "28": {
                "9": {
                    "3": 1,
                    "4": 1,
                    "5": "<binary_data> ",
                    "6": "<binary_data> ",
                    "7": 1.0,
                    "8": "<binary_data> ",
                    "10": "<binary_data> ",
                    "11": 1,
                    "503": "受击特效",
                    "507": 13,
                },
                "10": {
                    "3": 1,
                    "4": 1,
                    "5": "<binary_data> ",
                    "6": "<binary_data> ",
                    "7": 1.0,
                    "8": "<binary_data> ",
                    "10": "<binary_data> ",
                    "11": 1,
                    "503": "被击倒特效",
                    "507": 13,
                },
                "11": "GI_RootNode",
            },
        },
    ],
    "8": 10005018,
}


def _coerce_section_message(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(value, max_depth=16)
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
        return dict(msg)
    return None


def _ensure_list_allow_scalar(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _try_extract_instance_transform_container(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    尝试从实例 entry 中读取 transform 容器（section6 id=1 的 item['11']）。

    注意：这是“只读”版本，不会像 `_ensure_instance_transform_container` 一样补段/写回。
    """
    sections = entry.get("6")
    if isinstance(sections, dict):
        sections = [sections]
    if sections is None:
        sections = []
    if not isinstance(sections, list):
        return None
    for item in sections:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        container = item.get("11")
        if isinstance(container, dict):
            return container
    return None


def _normalize_guid_int(value: Any) -> Optional[int]:
    if isinstance(value, list) and value and isinstance(value[0], int):
        value = value[0]
    if not isinstance(value, int):
        return None
    v = int(value)
    # 常见占位：-1 / 0xFFFFFFFF / 0
    if v in (-1, 0, 4294967295):
        return None
    if v < 0:
        return None
    # GUID 经验上为 32-bit；这里不强制截断，交由 encoder 处理（负数会映射为 uint32）
    return int(v)


def _collect_used_instance_guid_ints_from_payload_root(payload_root: Dict[str, Any]) -> set[int]:
    used: set[int] = set()
    for section_key in ("5", "8"):
        section_msg = _coerce_section_message(payload_root.get(section_key))
        if section_msg is None:
            continue
        for rec in _ensure_list_allow_scalar(section_msg.get("1")):
            if not isinstance(rec, dict):
                continue
            transform = _try_extract_instance_transform_container(rec)
            if not isinstance(transform, dict):
                continue
            gid = _normalize_guid_int(transform.get("501"))
            if isinstance(gid, int):
                used.add(int(gid))
    return used


def _allocate_next_guid(existing_ids: set[int], start: int) -> int:
    """
    顺序分配一个不冲突的 GUID（类似 UI record 的 GUID 分配策略）。

    注意：此处约束为正数，避免 `-1/0xFFFFFFFF` 这类占位值。
    """
    candidate = int(start)
    if candidate <= 0:
        candidate = 1
    while candidate in existing_ids:
        candidate += 1
        if candidate <= 0:
            candidate = 1
    return int(candidate)


_SEED_INSTANCE_EXEMPLARS_CACHE: Tuple[
    Dict[str, Any],
    Dict[int, Dict[str, Any]],  # template_id_int -> exemplar entry
    Dict[int, Dict[str, Any]],  # template_type_code_int(entry['8']) -> exemplar entry
] | None = None


def _load_seed_instance_exemplars() -> Tuple[Dict[str, Any], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    为“极空 base .gil / 空实体段”提供可克隆样本：
    - 当目标 `.gil` 的 root4/5/1 为空时，允许新增实体时无法找到可克隆 entry；
    - 此时使用 ugc_file_tools/builtin_resources 内的 seed `.gil` 提供最小样本 entry 形态（仅作为 clone 原型，不会把 seed 实例本体写入目标）。
    """
    global _SEED_INSTANCE_EXEMPLARS_CACHE
    if _SEED_INSTANCE_EXEMPLARS_CACHE is not None:
        return _SEED_INSTANCE_EXEMPLARS_CACHE

    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    ugc_root = ugc_file_tools_builtin_resources_root()
    # 选择更“像真源”的 seed：用于“新增实例”的克隆原型（需要包含较完整的 section6/7 等结构）。
    seed_gil_path = (ugc_root / "seeds" / "template_instance_exemplars.gil").resolve()
    if not seed_gil_path.is_file():
        raise FileNotFoundError(str(seed_gil_path))

    seed_dump = dump_gil_to_raw_json_object(seed_gil_path)
    seed_root = get_payload_root(seed_dump)
    seed_instance_section = seed_root.get("5")
    if not isinstance(seed_instance_section, dict):
        raise ValueError("seed gil 缺少实体摆放段 root4/5（期望为 dict）。")

    seed_entries = seed_instance_section.get("1")
    if isinstance(seed_entries, dict):
        seed_entries = [seed_entries]
    if seed_entries is None:
        seed_entries = []
    if not isinstance(seed_entries, list):
        raise ValueError("seed gil 字段 root4/5/1 结构异常（期望为 list/dict/None）。")

    any_exemplar: Optional[Dict[str, Any]] = None
    exemplar_by_template_id: Dict[int, Dict[str, Any]] = {}
    exemplar_by_template_type_code: Dict[int, Dict[str, Any]] = {}
    for entry in seed_entries:
        if not isinstance(entry, dict):
            continue
        instance_id_int = _extract_instance_id_int(entry)
        if not isinstance(instance_id_int, int):
            continue
        if any_exemplar is None:
            any_exemplar = entry
        template_id_int = _extract_template_id_int_from_instance_entry(entry)
        if isinstance(template_id_int, int) and int(template_id_int) not in exemplar_by_template_id:
            exemplar_by_template_id[int(template_id_int)] = entry
        template_type_code_int = _extract_template_type_code_int_from_instance_entry(entry)
        if (
            isinstance(template_type_code_int, int)
            and int(template_type_code_int) not in exemplar_by_template_type_code
        ):
            exemplar_by_template_type_code[int(template_type_code_int)] = entry

    if any_exemplar is None:
        raise RuntimeError("seed gil 的 root4/5/1 未找到任何可克隆的实体 entry（内部错误）。")

    _SEED_INSTANCE_EXEMPLARS_CACHE = (
        any_exemplar,
        dict(exemplar_by_template_id),
        dict(exemplar_by_template_type_code),
    )
    return _SEED_INSTANCE_EXEMPLARS_CACHE


def _ensure_path_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list_allow_scalar(root: Dict[str, Any], key: str) -> List[Any]:
    """
    dump-json 中 repeated 字段在“只有 1 个元素”时可能被输出为标量（int/dict/str）。
    这里将其统一为 list 视图，便于追加/遍历。
    """
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    new_value = [value]
    root[key] = new_value
    return new_value


def _extract_first_int_from_repeated_field(node: Dict[str, Any], key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _extract_instance_id_int(entry: Dict[str, Any]) -> Optional[int]:
    value = entry.get("1")
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    if isinstance(value, int):
        return int(value)
    return None


def _extract_template_id_int_from_instance_entry(entry: Dict[str, Any]) -> Optional[int]:
    value = entry.get("2")
    if isinstance(value, list) and value and isinstance(value[0], dict):
        first = value[0]
        if isinstance(first.get("1"), int):
            return int(first.get("1"))
    if isinstance(value, dict) and isinstance(value.get("1"), int):
        return int(value.get("1"))
    return None


def _extract_template_type_code_int_from_template_entry(entry: Dict[str, Any]) -> Optional[int]:
    value = entry.get("2")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _extract_template_type_code_int_from_instance_entry(entry: Dict[str, Any]) -> Optional[int]:
    value = entry.get("8")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _set_instance_name(entry: Dict[str, Any], name: str) -> None:
    meta_list = _ensure_path_list_allow_scalar(entry, "5")

    name_item: Optional[Dict[str, Any]] = None
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") == 1:
            name_item = item
            break
    if name_item is None:
        name_item = {"1": 1, "11": {"1": str(name)}}
        meta_list.insert(0, name_item)
        return

    container = name_item.get("11")
    if not isinstance(container, dict):
        container = {}
        name_item["11"] = container
    container["1"] = str(name)


def _set_instance_root27_attachment_id_stream(entry: Dict[str, Any], attachment_ids: List[int]) -> None:
    """
    root5-style instance decorations：
    - root27.2(attachments) 每条挂载 entry['1'] 为 attachment_id_int（常见 0x40000001...）。
    - 父实例（root4/5/1）需要在 meta(id=40).field50 写入 message：
        - field501 = `<binary_data> <varint_stream(attachment_ids)>`

    观测样本（单个装饰物）：
    - attachment_id=0x40000001(1073741825) 的 varint bytes 为：81 80 80 80 04
    """
    ids = list(attachment_ids or [])
    if not ids:
        return
    if not all(isinstance(x, int) for x in ids):
        raise TypeError("attachment_ids must be List[int]")

    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_varint, format_binary_data_hex_text

    raw = b"".join(encode_varint(int(x)) for x in ids)

    meta_list = _ensure_path_list_allow_scalar(entry, "5")
    item40: Optional[Dict[str, Any]] = None
    for it in meta_list:
        if not isinstance(it, dict):
            continue
        if it.get("1") == 40:
            item40 = it
            break
    if item40 is None:
        item40 = {"1": 40}
        meta_list.append(item40)

    field50 = item40.get("50")
    if not isinstance(field50, dict):
        field50 = {}
        item40["50"] = field50
    field50["501"] = format_binary_data_hex_text(raw)


def _try_extract_instance_name(entry: Dict[str, Any]) -> str:
    """
    从实例 entry（root4/5/1）抽取实例名（meta id=1）。

    经验结构（对齐 `_set_instance_name`）：
    - entry['5'] 为 meta repeated
      - item['1']==1 的 item['11']['1'] 或 item['11'] 为名称字符串
    """
    meta_list = entry.get("5")
    if isinstance(meta_list, dict):
        meta_list = [meta_list]
    if meta_list is None:
        meta_list = []
    if not isinstance(meta_list, list):
        return ""
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        v11 = item.get("11")
        if isinstance(v11, str):
            name = normalize_dump_json_name_text(v11)
            if name != "":
                return str(name)
        if isinstance(v11, dict):
            name_val = v11.get("1")
            if isinstance(name_val, str):
                name = normalize_dump_json_name_text(name_val)
                if name != "":
                    return str(name)
    return ""


def _unwrap_protobuf_field1_string_from_misdecoded_text(text: str) -> str:
    """
    兼容一种“dump-json 误判”为文本的嵌套 message 形态：
    - 期望原始 bytes 为：0x0A + <len(varint)> + <utf8_bytes>
      （即：field_1 的 wire-level 编码，通常来自嵌套 message）
    """
    s = str(text or "")
    if s == "":
        return ""
    raw = s.encode("utf-8")
    if not raw or raw[0] != 0x0A:
        return s.strip()

    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint

    length, next_offset, ok = decode_varint(raw, 1, len(raw))
    if not ok:
        return s.strip()
    end = int(next_offset) + int(length)
    if end != len(raw):
        return s.strip()
    return raw[next_offset:end].decode("utf-8", errors="strict").strip()


def _normalize_instance_conflict_resolutions(
    *,
    project_root: Path,
    instance_files: List[Path],
    raw_conflicts: List[Dict[str, str]] | None,
) -> Dict[str, Dict[str, str]]:
    """
    解析并规范化 InstancesImportOptions.instance_conflict_resolutions（selection-json 透传）为：
      resolved_instance_json_file(casefold) -> {"action": str, "new_instance_name": str?}
    """
    if raw_conflicts is None:
        return {}
    if not isinstance(raw_conflicts, list):
        raise TypeError("instance_conflict_resolutions must be list[dict[str,str]] or None")

    instances_dir = (Path(project_root).resolve() / "实体摆放").resolve()
    allowed_files_cf: set[str] = {str(Path(p).resolve()).casefold() for p in list(instance_files or [])}

    out: Dict[str, Dict[str, str]] = {}
    for idx, item in enumerate(raw_conflicts):
        if not isinstance(item, dict):
            raise TypeError(f"instance_conflict_resolutions[{idx}] must be dict")
        instance_json_file = str(item.get("instance_json_file") or "").strip()
        if instance_json_file == "":
            raise ValueError(f"instance_conflict_resolutions[{idx}].instance_json_file 不能为空")
        p = Path(instance_json_file)
        if not p.is_absolute():
            raise ValueError(
                f"instance_conflict_resolutions[{idx}].instance_json_file must be absolute path: {instance_json_file!r}"
            )
        rp = p.resolve()
        if not rp.is_file():
            raise FileNotFoundError(str(rp))
        if rp.suffix.lower() != ".json":
            raise ValueError(f"instance_conflict_resolutions[{idx}].instance_json_file 不是 .json：{str(rp)}")
        if rp.name == "instances_index.json":
            raise ValueError(
                f"instance_conflict_resolutions[{idx}].instance_json_file 不能为 instances_index.json：{str(rp)}"
            )
        if rp.name.startswith("自研_"):
            raise ValueError(
                f"instance_conflict_resolutions[{idx}].instance_json_file 不能为 自研_*.json（非 InstanceConfig）：{str(rp)}"
            )
        try:
            rp.relative_to(instances_dir)
        except ValueError:
            raise ValueError(
                f"instance_conflict_resolutions[{idx}].instance_json_file 必须位于项目存档 实体摆放/ 下："
                f"{str(rp)} (root={str(instances_dir)})"
            )
        k = str(rp).casefold()
        if k in out:
            raise ValueError(
                "instance_conflict_resolutions 中存在重复 instance_json_file（忽略大小写）："
                f"{str(rp)!r}"
            )
        if k not in allowed_files_cf:
            raise ValueError(
                "instance_conflict_resolutions 中的 instance_json_file 未在本次写回范围内："
                f"{str(rp)}"
            )

        action = str(item.get("action") or "").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(
                f"instance_conflict_resolutions[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
            )
        new_instance_name = str(item.get("new_instance_name") or "").strip()
        if action == "add" and new_instance_name == "":
            raise ValueError(f"instance_conflict_resolutions[{idx}] action=add 时 new_instance_name 不能为空")
        obj: Dict[str, str] = {"action": action}
        if action == "add":
            obj["new_instance_name"] = new_instance_name
        out[k] = obj

    return dict(out)


def _ensure_instance_transform_container(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    返回 transform dict（位于 entry['6'] 中 id=1 的 item['11']）。
    """
    items = _ensure_path_list_allow_scalar(entry, "6")
    transform_item: Optional[Dict[str, Any]] = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("1") == 1:
            transform_item = item
            break
    if transform_item is None:
        transform_item = {"1": 1, "11": {}}
        items.insert(0, transform_item)

    container = transform_item.get("11")
    if not isinstance(container, dict):
        container = {}
        transform_item["11"] = container
    return container


def _normalize_float3(values: object, *, default_value: float) -> Tuple[float, float, float]:
    if isinstance(values, (list, tuple)) and len(values) == 3:
        x, y, z = values
        return float(x), float(y), float(z)
    return float(default_value), float(default_value), float(default_value)


def _set_vector3_field(target: Dict[str, Any], key: str, values: Tuple[float, float, float], *, empty_if_zero: bool) -> None:
    if empty_if_zero and float(values[0]) == 0.0 and float(values[1]) == 0.0 and float(values[2]) == 0.0:
        target[key] = {}
        return
    target[key] = {"1": float(values[0]), "2": float(values[1]), "3": float(values[2])}


def _read_int_from_nested_mapping(obj: Dict[str, Any], *keys: str) -> Optional[int]:
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return int(current) if isinstance(current, int) else None


def _load_instance_config_json(path: Path) -> Optional[Dict[str, Any]]:
    p = Path(path).resolve()
    if not p.is_file():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return None
    instance_id = obj.get("instance_id")
    if not isinstance(instance_id, str) or instance_id.strip() == "":
        return None
    return obj


def _iter_instance_config_files(project_root: Path) -> List[Path]:
    directory = (Path(project_root) / "实体摆放").resolve()
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for p in sorted(directory.glob("*.json"), key=lambda x: x.as_posix()):
        if p.name == "instances_index.json":
            continue
        # 一些解析辅助 JSON（非 InstanceConfig）
        if p.name.startswith("自研_"):
            continue
        files.append(p.resolve())
    return files


def _resolve_included_instance_files(*, project_root: Path, include_files: List[Path]) -> List[Path]:
    instances_dir = (Path(project_root).resolve() / "实体摆放").resolve()
    if not instances_dir.is_dir():
        if not list(include_files or []):
            return []
        raise FileNotFoundError(f"项目存档缺少 实体摆放/ 目录：{str(instances_dir)}")

    out: List[Path] = []
    seen: set[str] = set()
    for idx, raw in enumerate(list(include_files)):
        p = Path(raw).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"include_instance_json_files[{idx}] 不存在：{str(p)}")
        if p.suffix.lower() != ".json":
            raise ValueError(f"include_instance_json_files[{idx}] 不是 .json：{str(p)}")
        if p.name == "instances_index.json":
            continue
        if p.name.startswith("自研_"):
            continue
        try:
            p.relative_to(instances_dir)
        except ValueError:
            raise ValueError(
                f"include_instance_json_files[{idx}] 必须位于项目存档 实体摆放/ 下：{str(p)} (root={str(instances_dir)})"
            )
        k = str(p).casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)

    out.sort(key=lambda x: x.as_posix().casefold())
    return out


def _build_template_type_code_index_from_payload_root(payload_root: Dict[str, Any]) -> Dict[int, int]:
    """
    从 payload_root['4']['1'] 提取模板 type_code，用于同步实例 entry['8']。
    """
    section = payload_root.get("4")
    if not isinstance(section, dict):
        return {}
    entries_value = section.get("1")
    entries: List[Any]
    if isinstance(entries_value, list):
        entries = entries_value
    elif entries_value is None:
        entries = []
    else:
        entries = [entries_value]

    out: Dict[int, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        template_id_int = _extract_first_int_from_repeated_field(entry, "1")
        type_code_int = _extract_template_type_code_int_from_template_entry(entry)
        if isinstance(template_id_int, int) and isinstance(type_code_int, int):
            out[int(template_id_int)] = int(type_code_int)
    return out


def import_instances_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: InstancesImportOptions,
) -> Dict[str, Any]:
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

    instance_files: List[Path]
    if options.include_instance_json_files is not None:
        instance_files = _resolve_included_instance_files(
            project_root=project_path,
            include_files=list(options.include_instance_json_files),
        )
    else:
        instance_files = _iter_instance_config_files(project_path)
    if not instance_files:
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "mode": mode,
            "filtered_by_selection": bool(options.include_instance_json_files is not None),
            "instances_total": 0,
            "instances_updated": [],
            "instances_added": [],
            "instances_skipped_existing": [],
            "instances_missing_in_target": [],
            "instances_skipped_invalid_files": [],
        }

    raw_dump_object = dump_gil_to_raw_json_object(input_path)
    payload_root = get_payload_root(raw_dump_object)

    conflict_action_by_file_cf = _normalize_instance_conflict_resolutions(
        project_root=project_path,
        instance_files=list(instance_files),
        raw_conflicts=options.instance_conflict_resolutions,
    )

    template_type_code_by_template_id = _build_template_type_code_index_from_payload_root(payload_root)

    instance_section = _ensure_path_dict(payload_root, "5")
    instance_entries = _ensure_path_list_allow_scalar(instance_section, "1")

    existing_by_instance_id: Dict[int, Dict[str, Any]] = {}
    existing_by_name: Dict[str, Dict[str, Any]] = {}
    used_instance_names_cf: set[str] = set()
    exemplar_by_template_id: Dict[int, Dict[str, Any]] = {}
    exemplar_by_template_type_code: Dict[int, Dict[str, Any]] = {}
    any_exemplar: Optional[Dict[str, Any]] = None

    for entry in instance_entries:
        if not isinstance(entry, dict):
            continue
        instance_id_int = _extract_instance_id_int(entry)
        if not isinstance(instance_id_int, int):
            continue
        existing_by_instance_id[int(instance_id_int)] = entry
        name0 = _try_extract_instance_name(entry)
        if name0 != "":
            used_instance_names_cf.add(str(name0).casefold())
            if name0 not in existing_by_name:
                existing_by_name[str(name0)] = entry
        if any_exemplar is None:
            any_exemplar = entry
        template_id_int = _extract_template_id_int_from_instance_entry(entry)
        if isinstance(template_id_int, int) and int(template_id_int) not in exemplar_by_template_id:
            exemplar_by_template_id[int(template_id_int)] = entry
        template_type_code_int = _extract_template_type_code_int_from_instance_entry(entry)
        if (
            isinstance(template_type_code_int, int)
            and int(template_type_code_int) not in exemplar_by_template_type_code
        ):
            exemplar_by_template_type_code[int(template_type_code_int)] = entry

    used_instance_id_ints: set[int] = set(existing_by_instance_id.keys())
    used_instance_guid_ints: set[int] = _collect_used_instance_guid_ints_from_payload_root(payload_root)

    bootstrapped_seed_exemplar = False
    if any_exemplar is None:
        # 极空 base / 空实体段：从 seed `.gil` 取一个可克隆的实体 entry 作为原型（不写入 seed 本体）。
        seed_any, seed_by_template_id, seed_by_template_type_code = _load_seed_instance_exemplars()
        any_exemplar = seed_any
        exemplar_by_template_id = dict(seed_by_template_id)
        exemplar_by_template_type_code = dict(seed_by_template_type_code)
        bootstrapped_seed_exemplar = True

    instances_updated: List[str] = []
    instances_added: List[str] = []
    instances_added_as_new: List[str] = []
    instances_overwritten_by_name: List[str] = []
    instances_skipped_existing: List[str] = []
    instances_skipped_by_conflict: List[str] = []
    instances_missing_in_target: List[str] = []
    instances_skipped_invalid_files: List[str] = []
    touched_template_ids: set[int] = set()
    seed_exemplar_fallback_used = False
    builtin_exemplar_fallback_used = False

    level_variable_payloads_by_file_id = load_level_variable_payloads_by_file_id(project_root=project_path)
    custom_variable_missing_files_by_instance: Dict[str, List[str]] = {}
    custom_variable_writeback_reports: List[Dict[str, Any]] = []

    def _apply_custom_variables_if_any(*, entry: Dict[str, Any], instance_obj: Dict[str, Any], instance_id_text: str) -> None:
        meta0 = instance_obj.get("metadata")
        meta = meta0 if isinstance(meta0, dict) else {}
        if bool(meta.get("is_level_entity")):
            return
        refs = normalize_custom_variable_file_refs(meta.get("custom_variable_file"))
        if not refs:
            return

        merged_payloads: list[dict[str, Any]] = []
        missing: list[str] = []
        for file_id in refs:
            payloads = level_variable_payloads_by_file_id.get(str(file_id))
            if payloads is None:
                missing.append(str(file_id))
                continue
            merged_payloads.extend([p for p in payloads if isinstance(p, dict)])

        if missing:
            custom_variable_missing_files_by_instance[str(instance_id_text)] = list(missing)

        if not merged_payloads:
            return

        wr = upsert_custom_variables_from_level_variable_payloads(
            entry,
            group_list_key="7",
            variable_payloads=merged_payloads,
            overwrite_when_type_mismatched=True,
        )
        custom_variable_writeback_reports.append(
            {
                "instance_id": str(instance_id_text),
                "custom_variable_files": list(refs),
                "writeback": dict(wr),
            }
        )

    instance_decorations_total = 0
    instance_decorations_definitions_added = 0
    instance_decorations_definitions_updated = 0
    instance_decorations_attachments_added = 0
    instance_decorations_attachments_updated = 0

    for instance_file in instance_files:
        obj = _load_instance_config_json(instance_file)
        if obj is None:
            instances_skipped_invalid_files.append(str(instance_file))
            continue

        instance_id_text = str(obj.get("instance_id") or "").strip()
        if instance_id_text == "":
            instances_skipped_invalid_files.append(str(instance_file))
            continue
        instance_id_int = _coerce_numeric_id_int_allow_string(
            id_text=instance_id_text,
            used_id_ints=used_instance_id_ints,
            label="instance_id",
        )

        name_text = str(obj.get("name") or "").strip() or instance_id_text
        template_id_text = str(obj.get("template_id") or "").strip()
        if template_id_text == "":
            raise ValueError(f"实体摆放缺少 template_id：{str(instance_file)}")

        is_shape_editor_empty_template = str(template_id_text).casefold().startswith("shape_editor_empty__")
        if is_shape_editor_empty_template:
            # shape-editor “空画布载体”：写回 `.gil` 时按真源样本使用 builtin type_code=10005018 的引用形态。
            template_id_int = 10005018
        else:
            # template_id 也支持非数字：与 templates_importer 同口径映射到稳定 0x4040xxxx
            # 注意：此处不做“与 templates_importer bump 结果完全同步”的额外匹配；若出现极端 hash 冲突，推荐更换/加前缀 key。
            template_id_int = (
                int(template_id_text)
                if _ALL_DIGITS_RE.match(template_id_text)
                else int(build_component_template_root_id_int(template_key=str(template_id_text)))
            )

        file_cf = str(Path(instance_file).resolve()).casefold()
        conflict_action = conflict_action_by_file_cf.get(file_cf, {}).get("action", "")
        if conflict_action == "skip":
            instances_skipped_by_conflict.append(instance_id_text)
            continue
        if conflict_action == "add":
            new_name = str(conflict_action_by_file_cf.get(file_cf, {}).get("new_instance_name", "") or "").strip()
            if new_name == "":
                raise ValueError(
                    f"instance_conflict_resolutions action=add 缺少 new_instance_name：{str(Path(instance_file).resolve())}"
                )
            if new_name.casefold() in used_instance_names_cf:
                raise ValueError(
                    "new_instance_name 与 base/已写回实例重名（忽略大小写）："
                    f"{new_name!r} (file={str(Path(instance_file).resolve())})"
                )
            name_text = new_name

        pos = _normalize_float3(obj.get("position"), default_value=0.0)
        rot = _normalize_float3(obj.get("rotation"), default_value=0.0)

        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        scale = _normalize_float3(meta.get("ugc_scale") if isinstance(meta, dict) else None, default_value=1.0)

        instance_deco_records: List[Any] = []
        if is_shape_editor_empty_template:
            from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
                extract_template_decoration_records_from_instance_obj,
            )

            instance_deco_records = extract_template_decoration_records_from_instance_obj(
                instance_obj=obj,
                instance_json_file=Path(instance_file).resolve(),
                parent_template_id_int=int(template_id_int),
            )

        guid_value = _read_int_from_nested_mapping(meta, "ugc_guid_int") if isinstance(meta, dict) else None
        if guid_value is None and isinstance(meta, dict):
            guid_value = _read_int_from_nested_mapping(meta, "guid")
        template_type_value = _read_int_from_nested_mapping(meta, "ugc_template_type_code_int") if isinstance(meta, dict) else None
        if template_type_value is None and isinstance(meta, dict):
            template_type_value = _read_int_from_nested_mapping(meta, "ugc_template_type_int")
        if template_type_value is None:
            template_type_value = template_type_code_by_template_id.get(int(template_id_int))
        if template_type_value is None and is_shape_editor_empty_template:
            template_type_value = 10005018

        if conflict_action == "overwrite":
            base_entry_by_name = existing_by_name.get(str(obj.get("name") or "").strip() or instance_id_text)
            if base_entry_by_name is not None:
                base_instance_id_int = _extract_instance_id_int(base_entry_by_name)
                if not isinstance(base_instance_id_int, int):
                    raise ValueError(
                        "base `.gil` 同名实例缺少可解析的 instance_id_int（内部错误）："
                        f"name={str(obj.get('name') or '').strip()!r}"
                    )

                # 覆盖：复用 base instance_id_int，并按 overwrite 口径写回关键字段
                base_entry_by_name["1"] = [int(base_instance_id_int)]
                if is_shape_editor_empty_template:
                    base_entry_by_name["2"] = {"1": 10005018, "2": 1}
                else:
                    base_entry_by_name["2"] = [{"1": int(template_id_int)}]
                _set_instance_name(base_entry_by_name, str(obj.get("name") or "").strip() or instance_id_text)
                transform2 = _ensure_instance_transform_container(base_entry_by_name)
                _set_vector3_field(transform2, "1", pos, empty_if_zero=False)
                _set_vector3_field(transform2, "2", rot, empty_if_zero=True)
                _set_vector3_field(transform2, "3", scale, empty_if_zero=False)
                if isinstance(guid_value, int):
                    transform2["501"] = (-1 if int(guid_value) == 4294967295 or int(guid_value) == -1 else int(guid_value))
                if isinstance(template_type_value, int):
                    base_entry_by_name["8"] = int(template_type_value)
                _apply_custom_variables_if_any(entry=base_entry_by_name, instance_obj=obj, instance_id_text=instance_id_text)
                if instance_deco_records:
                    from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
                        apply_instance_decorations_writeback_to_payload_root,
                    )

                    dr = apply_instance_decorations_writeback_to_payload_root(
                        payload_root=payload_root,
                        parent_instance_id_int=int(base_instance_id_int),
                        decoration_records=list(instance_deco_records),
                    )
                    attachment_ids0 = dr.get("attachment_ids")
                    if not isinstance(attachment_ids0, list) or not all(isinstance(x, int) for x in attachment_ids0):
                        raise TypeError("instance decorations writeback report missing attachment_ids: List[int]")
                    _set_instance_root27_attachment_id_stream(base_entry_by_name, [int(x) for x in attachment_ids0])
                    instance_decorations_total += int(dr.get("decorations_total") or 0)
                    instance_decorations_definitions_added += int(dr.get("definitions_added") or 0)
                    instance_decorations_definitions_updated += int(dr.get("definitions_updated") or 0)
                    instance_decorations_attachments_added += int(dr.get("attachments_added") or 0)
                    instance_decorations_attachments_updated += int(dr.get("attachments_updated") or 0)
                instances_overwritten_by_name.append(instance_id_text)
                if not is_shape_editor_empty_template:
                    touched_template_ids.add(int(template_id_int))
                continue

        existing_entry = existing_by_instance_id.get(int(instance_id_int))
        if existing_entry is not None:
            if conflict_action == "add":
                raise ValueError(
                    "instance_conflict_resolutions action=add 但 instance_id 已存在于目标 .gil（无法新增为独立实例，请更换 instance_id）："
                    f"instance_id={instance_id_text}, file={str(instance_file)}"
                )
            if mode == "merge":
                instances_skipped_existing.append(instance_id_text)
                continue

            existing_entry["1"] = [int(instance_id_int)]

            # template_id：优先写 entry['2']（list[{'1': template_id_int}])
            if is_shape_editor_empty_template:
                existing_entry["2"] = {"1": 10005018, "2": 1}
            else:
                existing_entry["2"] = [{"1": int(template_id_int)}]

            # name：entry['5'] 的 meta id=1
            _set_instance_name(existing_entry, name_text)

            # transform：entry['6'] id=1 的 item['11']
            transform = _ensure_instance_transform_container(existing_entry)
            _set_vector3_field(transform, "1", pos, empty_if_zero=False)
            _set_vector3_field(transform, "2", rot, empty_if_zero=True)
            _set_vector3_field(transform, "3", scale, empty_if_zero=False)

            if isinstance(guid_value, int):
                if int(guid_value) == 4294967295 or int(guid_value) == -1:
                    transform["501"] = -1
                else:
                    transform["501"] = int(guid_value)

            if isinstance(template_type_value, int):
                existing_entry["8"] = int(template_type_value)

            _apply_custom_variables_if_any(entry=existing_entry, instance_obj=obj, instance_id_text=instance_id_text)

            if instance_deco_records:
                from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
                    apply_instance_decorations_writeback_to_payload_root,
                )

                dr = apply_instance_decorations_writeback_to_payload_root(
                    payload_root=payload_root,
                    parent_instance_id_int=int(instance_id_int),
                    decoration_records=list(instance_deco_records),
                )
                attachment_ids0 = dr.get("attachment_ids")
                if not isinstance(attachment_ids0, list) or not all(isinstance(x, int) for x in attachment_ids0):
                    raise TypeError("instance decorations writeback report missing attachment_ids: List[int]")
                _set_instance_root27_attachment_id_stream(existing_entry, [int(x) for x in attachment_ids0])
                instance_decorations_total += int(dr.get("decorations_total") or 0)
                instance_decorations_definitions_added += int(dr.get("definitions_added") or 0)
                instance_decorations_definitions_updated += int(dr.get("definitions_updated") or 0)
                instance_decorations_attachments_added += int(dr.get("attachments_added") or 0)
                instance_decorations_attachments_updated += int(dr.get("attachments_updated") or 0)

            instances_updated.append(instance_id_text)
            if not is_shape_editor_empty_template:
                touched_template_ids.add(int(template_id_int))
            continue

        instances_missing_in_target.append(instance_id_text)

        # 新增实体当前采用“克隆既有 entry 并替换关键字段”的策略。
        # 为避免克隆残留导致 GUID 错乱：即使未提供 guid，也强制写入 -1（常见占位值）。
        if not isinstance(template_type_value, int):
            raise ValueError(
                "允许新增实体时必须能解析模板类型（entry['8'] / ugc_template_type_int）。"
                "请确保目标 .gil 已包含对应 template_id 的模板段，或在 InstanceConfig.metadata 中提供 ugc_template_type_code_int/ugc_template_type_int。"
                f"instance_id={instance_id_text}, template_id={template_id_text}, file={str(instance_file)}"
            )

        # GUID：新增实例时若未提供，则按“顺序分配”生成一个不冲突 GUID（避免多个新增实例都写 -1 导致引用冲突）。
        guid_value2 = None if not isinstance(guid_value, int) else int(guid_value)
        if isinstance(guid_value2, int) and guid_value2 in (-1, 4294967295):
            guid_value2 = None
        if guid_value2 is None:
            start = (max(used_instance_guid_ints) + 1) if used_instance_guid_ints else 1
            guid_value2 = _allocate_next_guid(used_instance_guid_ints, start=int(start))
        else:
            if int(guid_value2) in used_instance_guid_ints:
                raise ValueError(
                    "新增实体的 guid 与目标存档中已有 GUID 冲突："
                    f"guid={guid_value2}, instance_id={instance_id_text}, file={str(instance_file)}"
                )
        used_instance_guid_ints.add(int(guid_value2))

        base_entry: Optional[Dict[str, Any]] = exemplar_by_template_id.get(int(template_id_int))
        if base_entry is None and isinstance(template_type_value, int):
            base_entry = exemplar_by_template_type_code.get(int(template_type_value))

        # 10005018（空模型 / shape-editor 空画布载体）：强制使用 canonical exemplar。
        #
        # 背景：base/seed 里同一个 template_type_code 可能对应“场景/武器/路标”等不同用途的实例样本，
        # 克隆它们容易夹带不必要的组件/特效/挂载引用，导致“新增实体自带特效”。
        if isinstance(template_type_value, int) and int(template_type_value) == 10005018:
            base_entry = dict(_BUILTIN_EXEMPLAR_INSTANCE_ENTRY_TYPE_10005018)
            builtin_exemplar_fallback_used = True
        if base_entry is None:
            # fallback: 使用内置 seed（更接近真源的实例段结构），避免“随便克隆一个 entry”导致实体不可见。
            _seed_any, _seed_by_template_id, _seed_by_template_type_code = _load_seed_instance_exemplars()
            base_entry = _seed_by_template_id.get(int(template_id_int))
            if base_entry is None and isinstance(template_type_value, int):
                base_entry = _seed_by_template_type_code.get(int(template_type_value))
            if base_entry is not None:
                seed_exemplar_fallback_used = True
        if base_entry is None:
            if isinstance(template_type_value, int) and int(template_type_value) == 10005018:
                base_entry = dict(_BUILTIN_EXEMPLAR_INSTANCE_ENTRY_TYPE_10005018)
                builtin_exemplar_fallback_used = True

        if base_entry is None:
            raise ValueError(
                "无法为新增实体找到可克隆的实例样本 entry。\n"
                "- 说明：实体摆放 entry 的 section6/7 等字段在不同 template_type 下差异较大，"
                "若随便克隆任意 entry，导出产物可能在游戏内不可见。\n"
                "- 解决：请使用一个已包含同类模板实例（相同 template_type_code）的 base `.gil`，"
                "或补充/扩展 ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil 的样本覆盖。\n"
                f"instance_id={instance_id_text}, template_id={template_id_text}, template_type={template_type_value}"
            )

        cloned = json.loads(json.dumps(base_entry, ensure_ascii=False))
        cloned["1"] = [int(instance_id_int)]
        if is_shape_editor_empty_template:
            cloned["2"] = {"1": 10005018, "2": 1}
        else:
            cloned["2"] = [{"1": int(template_id_int)}]
        _set_instance_name(cloned, name_text)
        transform = _ensure_instance_transform_container(cloned)
        _set_vector3_field(transform, "1", pos, empty_if_zero=False)
        _set_vector3_field(transform, "2", rot, empty_if_zero=True)
        _set_vector3_field(transform, "3", scale, empty_if_zero=False)
        transform["501"] = int(guid_value2)
        cloned["8"] = int(template_type_value)
        _apply_custom_variables_if_any(entry=cloned, instance_obj=obj, instance_id_text=instance_id_text)
        instance_entries.append(cloned)
        existing_by_instance_id[int(instance_id_int)] = cloned
        instances_added.append(instance_id_text)
        used_instance_names_cf.add(str(name_text).casefold())
        if conflict_action == "add":
            instances_added_as_new.append(instance_id_text)
        if instance_deco_records:
            from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
                apply_instance_decorations_writeback_to_payload_root,
            )

            dr = apply_instance_decorations_writeback_to_payload_root(
                payload_root=payload_root,
                parent_instance_id_int=int(instance_id_int),
                decoration_records=list(instance_deco_records),
            )
            attachment_ids0 = dr.get("attachment_ids")
            if not isinstance(attachment_ids0, list) or not all(isinstance(x, int) for x in attachment_ids0):
                raise TypeError("instance decorations writeback report missing attachment_ids: List[int]")
            _set_instance_root27_attachment_id_stream(cloned, [int(x) for x in attachment_ids0])
            instance_decorations_total += int(dr.get("decorations_total") or 0)
            instance_decorations_definitions_added += int(dr.get("definitions_added") or 0)
            instance_decorations_definitions_updated += int(dr.get("definitions_updated") or 0)
            instance_decorations_attachments_added += int(dr.get("attachments_added") or 0)
            instance_decorations_attachments_updated += int(dr.get("attachments_updated") or 0)

        if not is_shape_editor_empty_template:
            touched_template_ids.add(int(template_id_int))

    # === 同步模板装饰物挂载（root27.2）===
    # 背景：模板写回阶段会先写 root27.1(defs) 与“基于 base `.gil`”可推断到的 root27.2(atts)。
    # 当本次写回同时新增/覆盖了实例(root5/1)，模板阶段可能无法反查到“新实例ID”，导致装饰物未挂载而游戏侧不可见。
    decorations_attachment_sync_report: Dict[str, Any] | None = None
    if touched_template_ids:
        from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
            apply_template_decorations_writeback_to_payload_root,
            extract_template_decoration_records_from_root27_definitions_in_payload_root,
        )

        records_all = extract_template_decoration_records_from_root27_definitions_in_payload_root(payload_root=payload_root)
        records = [r for r in records_all if int(r.parent_template_id_int) in touched_template_ids]
        if records:
            decorations_attachment_sync_report = apply_template_decorations_writeback_to_payload_root(
                payload_root=payload_root,
                decoration_records=list(records),
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
        "bootstrapped_seed_exemplar": bool(bootstrapped_seed_exemplar),
        "seed_exemplar_fallback_used": bool(seed_exemplar_fallback_used),
        "builtin_exemplar_fallback_used": bool(builtin_exemplar_fallback_used),
        "filtered_by_selection": bool(options.include_instance_json_files is not None),
        "instances_total": len(instance_files),
        "instances_updated": sorted(set(instances_updated)),
        "instances_added": sorted(set(instances_added)),
        "instances_added_as_new": sorted(set(instances_added_as_new)),
        "instances_overwritten_by_name": sorted(set(instances_overwritten_by_name)),
        "instances_skipped_existing": sorted(set(instances_skipped_existing)),
        "instances_skipped_by_conflict": sorted(set(instances_skipped_by_conflict)),
        "instances_missing_in_target": sorted(set(instances_missing_in_target)),
        "instances_skipped_invalid_files": sorted(set(instances_skipped_invalid_files)),
        "custom_variables_writeback": {
            "instances_with_custom_variable_file": len(custom_variable_writeback_reports),
            "missing_variable_files_by_instance": dict(custom_variable_missing_files_by_instance),
            "writeback_reports": list(custom_variable_writeback_reports),
        },
        "touched_template_ids": sorted({int(x) for x in touched_template_ids}),
        "template_decorations_attachment_sync": (dict(decorations_attachment_sync_report) if decorations_attachment_sync_report else None),
        "instance_decorations_writeback": {
            "decorations_total": int(instance_decorations_total),
            "definitions_added": int(instance_decorations_definitions_added),
            "definitions_updated": int(instance_decorations_definitions_updated),
            "attachments_added": int(instance_decorations_attachments_added),
            "attachments_updated": int(instance_decorations_attachments_updated),
        },
    }


__all__ = [
    "InstancesImportOptions",
    "import_instances_from_project_archive_to_gil",
]


