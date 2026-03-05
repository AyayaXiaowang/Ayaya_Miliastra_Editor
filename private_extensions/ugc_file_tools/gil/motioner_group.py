from __future__ import annotations

"""
motioner_group.py

用途：
- 提供“运动器(Motioner) 组项”的识别与补丁函数。

真源样本（对照结论）：
- 在 `.gil` 的实体实例段 root4/5/1[*].7(group_list) 中，
  “加运动器”表现为新增一条 group_item：

    { "1": 4, "2": 1, "14": { "505": 1 } }

说明：
- 本模块只做纯逻辑处理（对 numeric_message/dump-json dict 就地修改），不做文件 I/O。
- fail-fast：结构不符合预期直接抛错；不使用 try/except。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


MOTIONER_GROUP_ID: int = 4
MOTIONER_GROUP_CANONICAL: JsonDict = {"1": 4, "2": 1, "14": {"505": 1}}


@dataclass(frozen=True, slots=True)
class MotionerPatchResult:
    """
    patch 结果摘要（用于 CLI/测试做断言）。
    """

    matched_entries: int
    changed_entries: int
    already_had_motioner_entries: int


def _ensure_list_allow_scalar(parent: JsonDict, key: str) -> List[Any]:
    value = parent.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        parent[key] = [value]
        return parent[key]
    if value is None:
        parent[key] = []
        return parent[key]
    raise TypeError(f"expected list/dict/None at key={key!r}, got {type(value).__name__}")


def _extract_first_int_allow_repeated(node: JsonDict, key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


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


def _is_probably_printable_text(text: str) -> bool:
    if not text:
        return False
    printable_count = 0
    for ch in text:
        if ch.isprintable() or ch in "\n\r\t":
            printable_count += 1
    return printable_count / max(len(text), 1) >= 0.92


def _sanitize_utf8_text(text: str) -> str:
    # 对齐 decode_gil：保留可见字符 + \t\r\n，剔除其他控制字符，再 strip()
    cleaned: List[str] = []
    for ch in str(text or ""):
        if ch.isprintable() or ch in "\t\r\n":
            cleaned.append(ch)
    return "".join(cleaned).strip()


def _try_extract_field1_utf8_from_wire_message_bytes(raw: bytes) -> str:
    """
    解析一种常见形态的“field_1=string”嵌套 message：
      0x0A + <len(varint)> + <utf8_bytes>
    """
    if not raw:
        return ""
    if raw[0] != 0x0A:
        return ""

    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint

    length, next_offset, ok = decode_varint(raw, 1, len(raw))
    if not ok:
        return ""
    end = int(next_offset) + int(length)
    if end != len(raw):
        return ""
    return raw[next_offset:end].decode("utf-8", errors="strict").strip()


def _try_extract_text_from_binary_data_text(binary_text: str) -> str:
    """
    从 `<binary_data> ...` 中尽力抽取可用于匹配的文本（主要用于实例名匹配）：
    - 优先按 “field_1=string 的嵌套 message” 解析
    - 否则尝试把 raw bytes 当作 UTF-8 文本解析（需满足 printable 阈值）
    """
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    raw = parse_binary_data_hex_text(binary_text)
    if not raw:
        return ""

    v1 = _try_extract_field1_utf8_from_wire_message_bytes(raw)
    if v1 != "":
        return v1

    decoded = raw.decode("utf-8", errors="replace")
    if "\ufffd" in decoded:
        return ""
    if not _is_probably_printable_text(decoded):
        return ""
    return _sanitize_utf8_text(decoded)


def try_extract_instance_name_from_entry(entry: JsonDict) -> str:
    """
    从实例 entry（root4/5/1）抽取实例名（meta id=1）。

    经验结构：
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
            if v11.startswith("<binary_data>"):
                return _try_extract_text_from_binary_data_text(v11)
            return _unwrap_protobuf_field1_string_from_misdecoded_text(v11)
        if isinstance(v11, dict):
            name_val = v11.get("1")
            if isinstance(name_val, str):
                if name_val.startswith("<binary_data>"):
                    return _try_extract_text_from_binary_data_text(name_val)
                return _unwrap_protobuf_field1_string_from_misdecoded_text(name_val)
    return ""


def has_motioner_group_in_instance_entry(entry: JsonDict) -> bool:
    group_list = entry.get("7")
    if isinstance(group_list, dict):
        group_list = [group_list]
    if not isinstance(group_list, list):
        return False

    for item in group_list:
        if not isinstance(item, dict):
            continue
        gid = _extract_first_int_allow_repeated(item, "1")
        if gid is None or int(gid) != int(MOTIONER_GROUP_ID):
            continue
        v14 = item.get("14")
        if not isinstance(v14, dict):
            return False
        v505 = _extract_first_int_allow_repeated(v14, "505")
        return isinstance(v505, int) and int(v505) == 1
    return False


def ensure_motioner_group_in_instance_entry(entry: JsonDict) -> bool:
    """
    确保实例 entry 的 group_list(key='7') 中存在“运动器”组项：
      { "1": 4, "2": 1, "14": { "505": 1 } }

    返回：
    - True：发生了就地修改
    - False：本来就满足
    """
    group_list_any = _ensure_list_allow_scalar(entry, "7")

    group_items: List[JsonDict] = []
    for it in group_list_any:
        if not isinstance(it, dict):
            raise TypeError(f"instance group_list contains non-dict item: {type(it).__name__}")
        group_items.append(it)

    motioner_items: List[JsonDict] = []
    for it in group_items:
        gid = _extract_first_int_allow_repeated(it, "1")
        if isinstance(gid, int) and int(gid) == int(MOTIONER_GROUP_ID):
            motioner_items.append(it)

    if len(motioner_items) > 1:
        raise ValueError("instance group_list contains duplicated motioner group_id=4 items")

    if not motioner_items:
        # 追加到末尾：对齐观测样本“新增项为 append”的行为，避免扰动既有 group 顺序。
        group_list_any.append(
            {"1": int(MOTIONER_GROUP_ID), "2": 1, "14": {"505": 1}}
        )
        return True

    item = motioner_items[0]
    changed = False

    v14 = item.get("14")
    if not isinstance(v14, dict):
        v14 = {}
        item["14"] = v14
        changed = True

    v505 = _extract_first_int_allow_repeated(v14, "505")
    if not (isinstance(v505, int) and int(v505) == 1):
        v14["505"] = 1
        changed = True

    if item.get("2") is None:
        item["2"] = 1
        changed = True

    return bool(changed)


def patch_payload_root_add_motioner(
    payload_root: JsonDict,
    *,
    instance_id_int: Optional[int] = None,
    instance_name: Optional[str] = None,
    match_all: bool = False,
) -> MotionerPatchResult:
    """
    在 payload_root 上执行“加运动器”补丁（就地修改）：

    - 目标段：root4/5/1[*]（实例 entries）
    - 目标字段：entry['7'] group_list

    匹配策略：
    - `match_all=True`：对所有实例 entry 尝试补丁
    - 否则：
      - 若传 `instance_id_int`：按实例 id 精确匹配
      - 若传 `instance_name`：按名字（casefold）精确匹配
      - 两者都传：必须同时满足
    """
    if not isinstance(payload_root, dict):
        raise TypeError("payload_root must be dict")

    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        raise TypeError("payload_root['5'] must be dict (instance section)")

    entries_any = section5.get("1")
    entries: List[JsonDict] = []
    if isinstance(entries_any, list):
        entries = [e for e in entries_any if isinstance(e, dict)]
    elif isinstance(entries_any, dict):
        entries = [entries_any]
    elif entries_any is None:
        entries = []
    else:
        raise TypeError(f"payload_root['5']['1'] must be list/dict/None, got {type(entries_any).__name__}")

    name_cf = str(instance_name).casefold() if instance_name is not None else None
    matched = 0
    changed = 0
    already_had = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        if not bool(match_all):
            ok = True
            if instance_id_int is not None:
                eid = _extract_first_int_allow_repeated(entry, "1")
                ok = ok and isinstance(eid, int) and int(eid) == int(instance_id_int)
            if instance_name is not None:
                nm = try_extract_instance_name_from_entry(entry)
                ok = ok and (str(nm).casefold() == str(name_cf))
            if not ok:
                continue

        matched += 1
        if has_motioner_group_in_instance_entry(entry):
            already_had += 1
            continue

        if ensure_motioner_group_in_instance_entry(entry):
            changed += 1

    return MotionerPatchResult(
        matched_entries=int(matched),
        changed_entries=int(changed),
        already_had_motioner_entries=int(already_had),
    )


__all__ = [
    "MOTIONER_GROUP_ID",
    "MOTIONER_GROUP_CANONICAL",
    "MotionerPatchResult",
    "try_extract_instance_name_from_entry",
    "has_motioner_group_in_instance_entry",
    "ensure_motioner_group_in_instance_entry",
    "patch_payload_root_add_motioner",
]

