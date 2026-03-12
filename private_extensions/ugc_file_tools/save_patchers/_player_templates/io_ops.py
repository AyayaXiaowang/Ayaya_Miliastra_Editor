from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..gil_codec import (
    GilContainer,
    build_gil_bytes_from_container,
    decode_message,
    encode_message,
    read_gil_container,
)
from .common import (
    FIND_BYTES_DEFAULT_LIMIT,
    FIND_TEXT_DEFAULT_LIMIT,
    PlayerTemplateRef,
    ROLE_EDIT_SUFFIX,
    ROOT5_META_LIST_KEY,
    ROOT5_REF_BOX_KEY,
    ROOT_ENTRY_ID_KEY,
    _enforce_no_overlap_or_raise,
    _players_to_human,
    _walk,
)
from .structured_entries import (
    _decode_players_bytes,
    _extract_name_from_entry_meta_list,
    _extract_players_bytes_from_entry_meta_list,
    _get_root5_entries,
    _is_player_template_like_root5_entry,
)


def dump_player_templates_report(input_gil: Path) -> Dict[str, Any]:
    """输出玩家模板报告（JSON dict）。"""
    container = read_gil_container(Path(input_gil))
    payload_root = decode_message(container.payload)
    # 以 root5 的“展示条目”为准列出所有玩家模板（不做 root4 去重，避免漏掉“玩家1的模板/玩家2345的模板”这种别名条目）
    root5_entries = _get_root5_entries(payload_root)
    listed: List[Dict[str, Any]] = []
    # overlap 校验：以 root4_entry_id 去重后再检查
    by_root4: Dict[int, Tuple[str, Tuple[int, ...]]] = {}

    for i, e5 in enumerate(root5_entries):
        wrapper_id = e5.get(ROOT_ENTRY_ID_KEY)
        name = _extract_name_from_entry_meta_list(e5.get(ROOT5_META_LIST_KEY))
        if name == "" or name.endswith(ROLE_EDIT_SUFFIX):
            continue
        if not _is_player_template_like_root5_entry(e5):
            continue
        ref_box = e5.get(ROOT5_REF_BOX_KEY)
        ref_id = ref_box.get(ROOT_ENTRY_ID_KEY) if isinstance(ref_box, dict) else None
        if not isinstance(ref_id, int):
            continue
        players_bytes = _extract_players_bytes_from_entry_meta_list(e5.get(ROOT5_META_LIST_KEY))
        players0: Tuple[int, ...] | None = None
        if isinstance(players_bytes, (bytes, bytearray)):
            players0 = _decode_players_bytes(bytes(players_bytes))

        listed.append(
            {
                "name": str(name),
                "players_0_based": (list(players0) if players0 is not None else None),
                "players_1_based": (list(_players_to_human(players0)) if players0 is not None else None),
                "players_semantics": (
                    "packed_field4 (0-based indices)" if players0 is not None else "missing_field4(all/special)"
                ),
                "root5_index": int(i),
                "root5_wrapper_id": (int(wrapper_id) if isinstance(wrapper_id, int) else None),
                "root4_entry_id": int(ref_id),
            }
        )

        if players0 is not None:
            existing = by_root4.get(int(ref_id))
            if existing is None:
                by_root4[int(ref_id)] = (str(name), tuple(players0))
            else:
                # 同一个 root4 被多个名字引用：只要玩家集合一致即可
                if tuple(existing[1]) != tuple(players0):
                    raise ValueError(f"同一 root4_entry_id={int(ref_id)} 出现不同玩家集合：{existing[0]!r} vs {name!r}")

    # overlap check across distinct root4 ids
    concrete_refs: List[PlayerTemplateRef] = []
    for _, (nm, players0) in sorted(by_root4.items(), key=lambda kv: kv[0]):
        concrete_refs.append(PlayerTemplateRef(name=nm, players=players0, msg={}))
    _enforce_no_overlap_or_raise(concrete_refs)

    return {
        "input_gil": str(Path(input_gil).resolve()),
        "templates_total": int(len(listed)),
        "templates": listed,
    }


def write_back_payload(*, base_gil: Path, payload_root: Dict[str, Any], output_gil: Path) -> Path:
    """将 payload_root encode 后写回到 base_gil 并输出新 `.gil`。"""
    base_container = read_gil_container(Path(base_gil))
    new_payload = encode_message(payload_root)
    out_bytes = build_gil_bytes_from_container(base=base_container, new_payload=new_payload)
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)
    return out_path


def load_payload_root(input_gil: Path) -> Tuple[GilContainer, Dict[str, Any]]:
    """读取 `.gil` 并解码其 payload_root（数值键 dict）。"""
    container = read_gil_container(Path(input_gil))
    payload_root = decode_message(container.payload)
    return container, payload_root


def find_bytes_fields_containing_pattern(
    payload_root: Dict[str, Any],
    *,
    pattern: bytes,
    limit: int = FIND_BYTES_DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """
    在已解码的 payload_root 中查找“某个 bytes 值内部包含特定二进制子串”的字段路径。

    用途：
    - 当某些数据（例如 packed players 列表）被封装在较大的二进制 blob 中且没有被进一步解码时，
      可以用该方法定位 blob 所在字段，再针对性做二次解码/写回。
    """
    if not isinstance(pattern, (bytes, bytearray)) or not bytes(pattern):
        raise ValueError("pattern must be non-empty bytes")
    hits: List[Dict[str, Any]] = []
    for path, v in _walk(payload_root, path=()):
        if not isinstance(v, (bytes, bytearray)):
            continue
        b = bytes(v)
        if bytes(pattern) not in b:
            continue
        hits.append(
            {
                "path": list(path),
                "bytes_len": int(len(b)),
                "occurrences": int(b.count(bytes(pattern))),
            }
        )
        if len(hits) >= int(limit):
            break
    return hits


def find_text_paths(
    payload_root: Dict[str, Any],
    *,
    substring: str,
    limit: int = FIND_TEXT_DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """在已解码的 payload_root 中查找包含指定子串的字符串值，并返回其路径。"""
    sub = str(substring or "")
    if sub == "":
        raise ValueError("substring 不能为空")
    hits: List[Dict[str, Any]] = []
    for path, v in _walk(payload_root, path=()):
        if not isinstance(v, str):
            continue
        if sub not in v:
            continue
        hits.append({"path": list(path), "value": str(v)})
        if len(hits) >= int(limit):
            break
    return hits

