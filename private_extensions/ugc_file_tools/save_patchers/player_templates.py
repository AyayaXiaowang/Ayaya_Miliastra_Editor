from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..gil_dump_codec.protobuf_like import (  # wire-level, lossless for untouched bytes
    decode_message_to_wire_chunks as _decode_wire_chunks,
    decode_varint as _decode_varint,
    encode_tag as _encode_tag,
    encode_varint as _encode_varint,
    encode_wire_chunks as _encode_wire_chunks,
)
from ..wire.patch import parse_tag_raw as _parse_tag_raw, split_length_delimited_value_raw as _split_ld_value_raw

from .gil_codec import (
    GilContainer,
    build_gil_bytes_from_container,
    decode_message,
    decode_packed_varints,
    encode_message,
    encode_packed_varints,
    read_gil_container,
)


@dataclass(frozen=True)
class PlayerTemplateRef:
    """玩家模板抽象（从 `.gil` payload 中提取出的可解释视图）。"""

    name: str
    # 0-based players: 0..7
    players: Tuple[int, ...]
    # 指向 payload 内的“模板 message dict”（数值键）
    msg: Dict[str, Any]


def _walk(obj: Any, *, path: Tuple[Any, ...]) -> Iterable[Tuple[Tuple[Any, ...], Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, path=path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, path=path + (i,))


def _collect_strings(obj: Any) -> List[str]:
    texts: List[str] = []
    for _, v in _walk(obj, path=()):
        if isinstance(v, str):
            t = str(v).strip()
            if t:
                texts.append(t)
    return texts


def _choose_template_name_from_strings(texts: List[str]) -> str:
    # 优先选择“像模板名”的字符串
    for t in texts:
        if "模板" in t:
            return t
    for t in texts:
        if t == "自定义变量":
            return t
    return texts[0] if texts else ""


def _normalize_player_index_list(values: List[int]) -> Tuple[int, ...]:
    cleaned: List[int] = []
    for v in values:
        if not isinstance(v, int):
            continue
        if 0 <= int(v) <= 7:
            cleaned.append(int(v))
    # 保持稳定：升序去重
    return tuple(sorted(set(cleaned)))


def _try_extract_players_from_template_msg(msg: Dict[str, Any]) -> Optional[Tuple[int, ...]]:
    """
    玩家模板生效玩家字段（真源样本）是 packed varints：
      field 4 (wire=2): bytes = [playerIndex0, playerIndex1, ...]   # 0-based
    """
    raw = msg.get("4")
    if isinstance(raw, (bytes, bytearray)):
        indices = decode_packed_varints(bytes(raw))
        players = _normalize_player_index_list(indices)
        # 空 bytes：可能表达“全部/未限制”。这里返回空 tuple 交由上层解释（不直接当作错误）。
        return tuple(players)
    return None


def _looks_like_player_template_msg(msg: Dict[str, Any]) -> bool:
    # 先看是否有 field_4 packed players（这是玩家模板最关键的“可解释字段”）
    players = _try_extract_players_from_template_msg(msg)
    if players is None:
        return False

    # 再在该 dict 内部（递归）寻找“像模板名”的文本
    texts = _collect_strings(msg)
    for t in texts:
        if "模板" in t or t == "自定义变量":
            return True
    return False


def _collect_player_templates(payload_root: Dict[str, Any]) -> List[PlayerTemplateRef]:
    """
    从 payload_root 中“基于结构+语义”抽取玩家模板条目。

    约束：
    - 不依赖某个固定路径；而是用字段形态识别（含 name 且含 field4 packed players）。
    - 玩家索引为 0..7（对应玩家1..8）。
    """
    found: List[PlayerTemplateRef] = []
    for _path, obj in _walk(payload_root, path=()):
        if not isinstance(obj, dict):
            continue
        if not _looks_like_player_template_msg(obj):
            continue
        texts = _collect_strings(obj)
        name = _choose_template_name_from_strings(texts)
        players = _try_extract_players_from_template_msg(obj)
        if players is None:
            continue
        found.append(PlayerTemplateRef(name=str(name), players=tuple(players), msg=obj))
    # 去重：同一个 dict 会被 walk 命中一次，但不同 dict 可能同名；这里不强行去重
    return found


def _players_to_human(players_0_based: Tuple[int, ...]) -> Tuple[int, ...]:
    return tuple(int(p) + 1 for p in players_0_based)


def _parse_human_players(players: Iterable[int]) -> Tuple[int, ...]:
    out: List[int] = []
    for p in players:
        if not isinstance(p, int):
            raise ValueError(f"player index must be int: {p!r}")
        if not (1 <= int(p) <= 8):
            raise ValueError(f"player must be in 1..8: {p!r}")
        out.append(int(p) - 1)
    return tuple(sorted(set(out)))


def _enforce_no_overlap_or_raise(templates: List[PlayerTemplateRef]) -> None:
    used: Dict[int, str] = {}
    for t in templates:
        for p in t.players:
            if p in used:
                raise ValueError(
                    f"玩家模板生效玩家发生重叠：player={p+1} 被 {used[p]!r} 与 {t.name!r} 同时占用"
                )
            used[p] = t.name


# -------------------- Structured extraction (root4/root5 sections) --------------------


@dataclass(frozen=True)
class PlayerTemplateEntry:
    """
    结构化玩家模板条目（来自 payload_root['4']['1'] 与 payload_root['5']['1'] 的成对数据）。

    说明：
    - root4_entry_id = root4_entry['1']
    - root5_entry['2']['1'] == root4_entry_id（root5 通过该字段引用 root4）
    - 玩家生效玩家列表在“普通模板条目”（不含 "(角色编辑)"）的 meta item 中：
      - root5_entry['5'][?] 里 item['1']==3 的 item['12']['4'] 为 packed players bytes（0-based）
      - root4_entry['6'][?] 里同样结构
    - 自定义变量定义在普通模板条目的变量组容器内：
      - root5_entry['7']（list）里 item['1']==1 && item['2']==1 的 item['11']['1'] 为变量定义列表
      - root4_entry['8']（list）里同样结构
    """

    name: str
    players_0_based: Optional[Tuple[int, ...]]  # None = “未写 players 字段”（真源语义：默认/全体或特殊模板）
    root5_index: int
    root4_index: int
    root5_wrapper_id: int
    root4_entry_id: int


def _get_root4_entries(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    section = payload_root.get("4")
    if not isinstance(section, dict):
        return []
    entries = section.get("1")
    if isinstance(entries, list):
        return [e for e in entries if isinstance(e, dict)]
    if isinstance(entries, dict):
        return [entries]
    return []


def _get_root5_entries(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    section = payload_root.get("5")
    if not isinstance(section, dict):
        return []
    entries = section.get("1")
    if isinstance(entries, list):
        return [e for e in entries if isinstance(e, dict)]
    if isinstance(entries, dict):
        return [entries]
    return []


def _find_root5_entry_index_by_name(payload_root: Dict[str, Any], *, name: str) -> int:
    target = str(name or "").strip()
    if target == "":
        raise ValueError("name 不能为空")
    entries = _get_root5_entries(payload_root)
    hit: Optional[int] = None
    for i, e in enumerate(entries):
        e_name = _extract_name_from_entry_meta_list(e.get("5"))
        if e_name != target:
            continue
        if hit is not None:
            raise ValueError(f"存在多个同名条目：{target!r}（root5 index {hit} 与 {i}）")
        hit = int(i)
    if hit is None:
        raise ValueError(f"未找到条目：{target!r}")
    return int(hit)


def _find_root4_entry_index_by_id(payload_root: Dict[str, Any], *, entry_id: int) -> int:
    entries = _get_root4_entries(payload_root)
    target = int(entry_id)
    hit: Optional[int] = None
    for i, e in enumerate(entries):
        rid = e.get("1")
        if isinstance(rid, int) and int(rid) == target:
            if hit is not None:
                raise ValueError(f"root4 存在多个相同 id={target} 的条目（index {hit} 与 {i}）")
            hit = int(i)
    if hit is None:
        raise ValueError(f"root4 未找到 id={target} 的条目")
    return int(hit)


def _extract_name_from_entry_meta_list(meta_list: Any) -> str:
    if not isinstance(meta_list, list):
        return ""
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        name_box = item.get("11")
        if not isinstance(name_box, dict):
            continue
        name = name_box.get("1")
        if isinstance(name, str) and name.strip():
            return str(name).strip()
    return ""


def _extract_players_bytes_from_entry_meta_list(meta_list: Any) -> Optional[bytes]:
    """
    返回 packed players bytes（不解析）；若 meta 中不存在该字段则返回 None。
    """
    if not isinstance(meta_list, list):
        return None
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 3:
            continue
        box = item.get("12")
        if not isinstance(box, dict):
            continue
        raw = box.get("4")
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return None
    return None


def _decode_players_bytes(players_bytes: bytes) -> Tuple[int, ...]:
    return _normalize_player_index_list(decode_packed_varints(bytes(players_bytes)))


def _is_player_template_like_root5_entry(entry: Dict[str, Any]) -> bool:
    """
    识别“玩家模板 wrapper 条目”（root5['1'] 的元素）。

    依据真源样本的可解释特征：
    - entry['5'] meta list 内存在 item['1']==3，且 item['12'] 为 dict
    - item['12'] 至少包含字段 '5' 与 '6'（固定配置），'4'(players) 可缺失表示“全部/默认”
    """
    meta = entry.get("5")
    if not isinstance(meta, list):
        return False
    for item in meta:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 3:
            continue
        box = item.get("12")
        if not isinstance(box, dict):
            continue
        if not isinstance(box.get("5"), int):
            return False
        if not isinstance(box.get("6"), int):
            return False
        return True
    return False


def _iter_root5_indices_by_ref_id(payload_root: Dict[str, Any], *, ref_id: int) -> List[int]:
    out: List[int] = []
    entries = _get_root5_entries(payload_root)
    target = int(ref_id)
    for i, e5 in enumerate(entries):
        ref_box = e5.get("2")
        rid = ref_box.get("1") if isinstance(ref_box, dict) else None
        if isinstance(rid, int) and int(rid) == target:
            out.append(int(i))
    return out


def list_player_templates(payload_root: Dict[str, Any]) -> List[PlayerTemplateEntry]:
    root4 = _get_root4_entries(payload_root)
    root5 = _get_root5_entries(payload_root)
    root4_by_id: Dict[int, Tuple[int, Dict[str, Any]]] = {}
    for idx, e4 in enumerate(root4):
        rid = e4.get("1")
        if isinstance(rid, int):
            root4_by_id[int(rid)] = (int(idx), e4)

    out: List[PlayerTemplateEntry] = []
    for idx, e5 in enumerate(root5):
        # 只识别“玩家模板 wrapper 条目”（避免把其它模板/资源条目误当成玩家模板）。
        if not _is_player_template_like_root5_entry(e5):
            continue
        ref_box = e5.get("2")
        ref_id = ref_box.get("1") if isinstance(ref_box, dict) else None
        if not isinstance(ref_id, int):
            continue
        root4_hit = root4_by_id.get(int(ref_id))
        if root4_hit is None:
            continue
        root4_index, e4 = root4_hit

        name = _extract_name_from_entry_meta_list(e5.get("5"))
        if name == "":
            continue
        # 只把“普通条目”当作玩家模板入口；角色编辑条目用于 UI/编辑器形态，不承载生效玩家/变量定义
        if name.endswith("(角色编辑)"):
            continue

        players_bytes = _extract_players_bytes_from_entry_meta_list(e5.get("5"))
        players: Optional[Tuple[int, ...]] = None
        if isinstance(players_bytes, (bytes, bytearray)):
            players = _decode_players_bytes(bytes(players_bytes))

        wrapper_id = e5.get("1")
        if not isinstance(wrapper_id, int):
            continue

        out.append(
            PlayerTemplateEntry(
                name=str(name),
                players_0_based=(tuple(players) if players is not None else None),
                root5_index=int(idx),
                root4_index=int(root4_index),
                root5_wrapper_id=int(wrapper_id),
                root4_entry_id=int(ref_id),
            )
        )
    # root5 可能存在多个 wrapper 同时引用同一个 root4_entry（同一个模板多处出现）。
    # 对外暴露时按 root4_entry_id 去重，避免“同一模板被重复计数/导致重叠校验误报”。
    dedup: Dict[int, PlayerTemplateEntry] = {}
    for t in out:
        existing = dedup.get(int(t.root4_entry_id))
        if existing is None:
            dedup[int(t.root4_entry_id)] = t
            continue
        # 选更靠前的 root5_index 作为代表（稳定）
        if int(t.root5_index) < int(existing.root5_index):
            dedup[int(t.root4_entry_id)] = t
    return list(dedup.values())


def set_template_players_inplace(
    payload_root: Dict[str, Any],
    *,
    template_name: str,
    players_1_based: Iterable[int],
) -> Dict[str, Any]:
    """
    修改指定玩家模板的生效玩家（写回到 field 4 packed varints）。
    """
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")
    new_players = _parse_human_players(players_1_based)

    root5_index = _find_root5_entry_index_by_name(payload_root, name=target)
    root5_entries = _get_root5_entries(payload_root)
    e5 = root5_entries[root5_index]
    ref_box = e5.get("2")
    ref_id = ref_box.get("1") if isinstance(ref_box, dict) else None
    if not isinstance(ref_id, int):
        raise ValueError(f"模板 {target!r} 缺少 root4 引用：entry['2']['1']")
    root4_index = _find_root4_entry_index_by_id(payload_root, entry_id=int(ref_id))
    root4_entries = _get_root4_entries(payload_root)
    e4 = root4_entries[root4_index]

    before_bytes = _extract_players_bytes_from_entry_meta_list(e5.get("5"))
    before_players = _decode_players_bytes(before_bytes) if isinstance(before_bytes, (bytes, bytearray)) else None

    # 写回策略：
    # - 指定玩家集合 => 写入 packed bytes
    # - 若指定为全体(1..8) => 删除该字段（对齐“空存档/默认全体”的缺省形态）
    is_all = tuple(new_players) == tuple(range(8))
    encoded = encode_packed_varints(list(new_players))

    def _set_players_bytes_on_meta_list(meta_list: Any, *, players_bytes: Optional[bytes]) -> None:
        if not isinstance(meta_list, list):
            raise ValueError("entry meta_list is not list")
        for item in meta_list:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 3:
                continue
            box = item.get("12")
            if not isinstance(box, dict):
                raise ValueError("players box missing: item['12'] is not dict")
            if players_bytes is None:
                box.pop("4", None)
            else:
                box["4"] = bytes(players_bytes)
            return
        raise ValueError("players meta item (item['1']==3) not found")

    # 同一 root4_entry_id 可能被多个 wrapper 条目引用（例如 “默认模版” 与 “玩家1的模板” 指向同一 root4）。
    # 真实语义上它们是同一模板的不同别名/入口，因此需要同步更新所有引用同一 root4 的 wrapper，避免出现不一致。
    ref_indices = _iter_root5_indices_by_ref_id(payload_root, ref_id=int(ref_id))
    changed_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = root5_entries[i]
        if not _is_player_template_like_root5_entry(wrapper):
            continue
        # role-edit 条目通常 self-ref 且不包含 players box；这里仅更新“有 players box 的条目”
        _set_players_bytes_on_meta_list(wrapper.get("5"), players_bytes=(None if is_all else encoded))
        changed_wrappers.append(int(i))
    _set_players_bytes_on_meta_list(e4.get("6"), players_bytes=(None if is_all else encoded))

    # 校验互斥：仅对“写了 players 字段”的模板做互斥（未写字段的条目可能是特殊模板，如“自定义变量”）。
    after = list_player_templates(payload_root)
    concrete_refs: List[PlayerTemplateRef] = []
    for it in after:
        if it.players_0_based is None:
            continue
        concrete_refs.append(PlayerTemplateRef(name=it.name, players=it.players_0_based, msg={}))
    _enforce_no_overlap_or_raise(concrete_refs)

    return {
        "template_name": target,
        "players_before": (list(_players_to_human(before_players)) if before_players is not None else None),
        "players_after": list(_players_to_human(tuple(new_players))),
        "stored_as": ("missing_field4(all_players)" if is_all else "packed_field4"),
        "root5_index": int(root5_index),
        "root4_entry_id": int(ref_id),
        "updated_root5_wrappers_total": int(len(changed_wrappers)),
        "updated_root5_wrappers": changed_wrappers,
    }


def add_custom_variable_to_template_inplace(
    payload_root: Dict[str, Any],
    *,
    template_name: str,
    variable_name: str,
    type_code: int,
    default_value: Any,
) -> Dict[str, Any]:
    """
    给玩家模板追加一条“自定义变量定义”。

    说明：
    - 这里先按“通用自定义变量条目形态”写入：{name,type_code,default}。
    - 真正的字段路径需要先从样本中定位：变量列表在模板 message 的哪个字段号下。
    - 当前实现先做结构定位（在模板 msg 内找出“变量列表容器”字段），定位不到就 fail-fast。
    """
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")
    var_name = str(variable_name or "").strip()
    if var_name == "":
        raise ValueError("variable_name 不能为空")
    tc = int(type_code)
    if tc <= 0:
        raise ValueError(f"invalid type_code: {type_code!r}")

    root5_index = _find_root5_entry_index_by_name(payload_root, name=target)
    root5_entries = _get_root5_entries(payload_root)
    e5 = root5_entries[root5_index]
    ref_box = e5.get("2")
    ref_id = ref_box.get("1") if isinstance(ref_box, dict) else None
    if not isinstance(ref_id, int):
        raise ValueError(f"模板 {target!r} 缺少 root4 引用：entry['2']['1']")
    root4_index = _find_root4_entry_index_by_id(payload_root, entry_id=int(ref_id))
    root4_entries = _get_root4_entries(payload_root)
    e4 = root4_entries[root4_index]

    def _ensure_variable_def_list(container_list: Any) -> List[Dict[str, Any]]:
        if not isinstance(container_list, list):
            raise ValueError("variables container is not list")
        for item in container_list:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 1 or item.get("2") != 1:
                continue
            box = item.get("11")
            if box is None or isinstance(box, (bytes, bytearray)):
                box = {}
                item["11"] = box
            if not isinstance(box, dict):
                raise ValueError(f"variables box is not dict: {type(box).__name__}")
            lst = box.get("1")
            if lst is None:
                box["1"] = []
                return box["1"]
            if isinstance(lst, dict):
                box["1"] = [lst]
                return box["1"]
            if isinstance(lst, list):
                return lst
        # 没有 group1 容器则创建
        new_item: Dict[str, Any] = {"1": 1, "2": 1, "11": {"1": []}}
        container_list.append(new_item)
        return new_item["11"]["1"]

    def _build_var_def_item(*, name: str, type_code: int, default_value: Any) -> Dict[str, Any]:
        empty = b""
        tc2 = int(type_code)
        # type-specific default field number（来自真源样本：字符串16、字符串列表21、整数13、整数列表18、配置ID30）
        default_field_by_type: Dict[int, str] = {
            1: "11",
            3: "13",
            6: "16",
            8: "18",
            11: "21",
            20: "30",
        }
        default_field = default_field_by_type.get(tc2)
        if default_field is None:
            raise ValueError(f"暂不支持该自定义变量类型写回：type_code={tc2}")

        # 默认值编码（尽量与真源一致：0/空通常用 empty bytes）
        default_payload: Any = empty
        if tc2 in (1, 3):
            v = int(default_value) if default_value is not None else 0
            default_payload = (b"" if v == 0 else {"1": int(v)})
        elif tc2 == 6:
            s = str(default_value) if default_value is not None else ""
            default_payload = (b"" if s == "" else {"1": s})
        elif tc2 == 20:
            v = int(default_value) if default_value is not None else 0
            default_payload = (b"" if v == 0 else {"1": {"1": 1, "2": int(v)}})
        else:
            # 列表：先只支持空默认（与真源样本一致）
            default_payload = b""

        return {
            "2": str(name),
            "3": int(tc2),
            "4": {
                "1": int(tc2),
                "2": {"1": int(tc2), "2": b""},
                default_field: default_payload,
            },
            "5": 1,
            "6": {"1": int(tc2), "2": b""},
        }

    # root5: variables in field '7'（需要同步到所有引用同一 root4 的 wrapper，保持一致）
    ref_indices = _iter_root5_indices_by_ref_id(payload_root, ref_id=int(ref_id))
    updated_wrappers: List[int] = []

    # 先在“当前 name 指向的 wrapper”上写入，然后把同样的变量 item 追加到其他 wrapper 的 field7 中
    vlist5 = _ensure_variable_def_list(e5.setdefault("7", []))
    if not isinstance(vlist5, list):
        raise RuntimeError("internal error: root5 variable list not list")
    # root4: variables in field '8'
    vlist4 = _ensure_variable_def_list(e4.setdefault("8", []))
    if not isinstance(vlist4, list):
        raise RuntimeError("internal error: root4 variable list not list")

    # 去重（按 name）
    for item in vlist5:
        if isinstance(item, dict) and str(item.get("2") or "").strip() == var_name:
            return {
                "template_name": target,
                "variable_name": var_name,
                "created": False,
                "reason": "already_exists",
                "root5_index": int(root5_index),
                "root4_entry_id": int(ref_id),
            }

    new_item = _build_var_def_item(name=var_name, type_code=int(tc), default_value=default_value)
    vlist5.append(dict(new_item))
    vlist4.append(dict(new_item))

    for i in ref_indices:
        wrapper = root5_entries[i]
        if wrapper is e5:
            updated_wrappers.append(int(i))
            continue
        # 仅同步“像模板 wrapper”的条目；其它引用（若存在）跳过
        if not isinstance(wrapper, dict):
            continue
        vlist_other = _ensure_variable_def_list(wrapper.setdefault("7", []))
        if isinstance(vlist_other, list):
            # 避免重复追加
            exists = False
            for it in vlist_other:
                if isinstance(it, dict) and str(it.get("2") or "").strip() == var_name:
                    exists = True
                    break
            if not exists:
                vlist_other.append(dict(new_item))
            updated_wrappers.append(int(i))

    return {
        "template_name": target,
        "variable_name": var_name,
        "type_code": int(tc),
        "default_value": default_value,
        "created": True,
        "root5_index": int(root5_index),
        "root4_entry_id": int(ref_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
    }


def _find_player_template_entry_by_name(payload_root: Dict[str, Any], *, template_name: str) -> PlayerTemplateEntry:
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")

    entries = list_player_templates(payload_root)
    hits = [t for t in entries if str(t.name) == target]
    if not hits:
        available = [t.name for t in entries]
        raise ValueError(f"未找到玩家模板：{target!r}（available={available!r}）")
    if len(hits) > 1:
        ids = [int(t.root4_entry_id) for t in hits]
        raise ValueError(f"存在多个同名玩家模板：{target!r}（root4_entry_ids={ids!r}）")
    return hits[0]


def _extract_group1_variable_def_items(group_list: Any) -> List[Dict[str, Any]]:
    """
    从 root5['7']/root4['8'] 的 group_list 中提取 group1(1/1) 的变量定义列表（dict item）。

    group1 容器形态（与 add_custom_variable_to_template_inplace 的写回一致）：
    - list item：item['1']==1 && item['2']==1
    - item['11']['1']：变量定义列表（list 或 dict）
    """
    if not isinstance(group_list, list):
        return []

    for item in group_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1 or item.get("2") != 1:
            continue
        box = item.get("11")
        if not isinstance(box, dict):
            return []
        lst = box.get("1")
        if lst is None:
            return []
        if isinstance(lst, dict):
            return [dict(lst)]
        if isinstance(lst, list):
            return [dict(x) for x in lst if isinstance(x, dict)]
        return []

    return []


def _extract_group1_variable_names(group_list: Any) -> List[str]:
    items = _extract_group1_variable_def_items(group_list)
    out: List[str] = []
    for it in items:
        name = it.get("2")
        if isinstance(name, str) and name.strip():
            out.append(str(name).strip())
    return out


def copy_template_custom_variable_defs_inplace(
    dst_payload_root: Dict[str, Any],
    *,
    dst_template_name: str,
    src_payload_root: Dict[str, Any],
    src_template_name: str,
) -> Dict[str, Any]:
    """
    将 src 模板上的“自定义变量定义（group1）”拷贝到 dst 模板（写回 root5['7'] 与 root4['8']）。

    说明：
    - 以模板名定位条目（基于 list_player_templates 的 root4 去重视图，避免 root5 同名 wrapper 导致歧义）。
    - 同步更新所有引用同一 root4_entry_id 的 root5 wrapper，避免出现不一致。
    """
    src_name = str(src_template_name or "").strip()
    dst_name = str(dst_template_name or "").strip()
    if src_name == "":
        raise ValueError("src_template_name 不能为空")
    if dst_name == "":
        raise ValueError("dst_template_name 不能为空")

    src_entry = _find_player_template_entry_by_name(src_payload_root, template_name=src_name)
    dst_entry = _find_player_template_entry_by_name(dst_payload_root, template_name=dst_name)

    src_root5_entries = _get_root5_entries(src_payload_root)
    src_root4_entries = _get_root4_entries(src_payload_root)
    dst_root5_entries = _get_root5_entries(dst_payload_root)
    dst_root4_entries = _get_root4_entries(dst_payload_root)

    src_e5 = src_root5_entries[int(src_entry.root5_index)]
    src_e4 = src_root4_entries[int(src_entry.root4_index)]

    # 深拷贝：避免引用同一 dict/list 导致后续写回互相污染
    src_group7 = copy.deepcopy(src_e5.get("7"))
    src_group8 = copy.deepcopy(src_e4.get("8"))

    src_var_names = _extract_group1_variable_names(src_group7)
    if not src_var_names:
        raise ValueError(f"源模板未找到任何 group1 变量定义：template={src_name!r}")

    dst_before_names = _extract_group1_variable_names(dst_root5_entries[int(dst_entry.root5_index)].get("7"))

    # root4: template body
    dst_e4 = dst_root4_entries[int(dst_entry.root4_index)]
    if src_group8 is None:
        dst_e4.pop("8", None)
    else:
        dst_e4["8"] = copy.deepcopy(src_group8)

    # root5: all wrappers referencing same root4_entry_id
    ref_indices = _iter_root5_indices_by_ref_id(dst_payload_root, ref_id=int(dst_entry.root4_entry_id))
    updated_wrappers: List[int] = []
    skipped_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = dst_root5_entries[int(i)]
        if not isinstance(wrapper, dict):
            skipped_wrappers.append(int(i))
            continue
        if not _is_player_template_like_root5_entry(wrapper):
            skipped_wrappers.append(int(i))
            continue
        name = _extract_name_from_entry_meta_list(wrapper.get("5"))
        if name.endswith("(角色编辑)"):
            skipped_wrappers.append(int(i))
            continue
        if str(name) != dst_name:
            skipped_wrappers.append(int(i))
            continue

        if src_group7 is None:
            wrapper.pop("7", None)
        else:
            wrapper["7"] = copy.deepcopy(src_group7)
        updated_wrappers.append(int(i))

    dst_after_names = _extract_group1_variable_names(dst_root5_entries[int(dst_entry.root5_index)].get("7"))

    return {
        "src_template_name": src_name,
        "dst_template_name": dst_name,
        "src_vars_total": int(len(src_var_names)),
        "src_vars_preview": src_var_names[:50],
        "dst_before_vars_total": int(len(dst_before_names)),
        "dst_before_vars_preview": dst_before_names[:50],
        "dst_after_vars_total": int(len(dst_after_names)),
        "dst_after_vars_preview": dst_after_names[:50],
        "dst_root4_entry_id": int(dst_entry.root4_entry_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
        "skipped_root5_wrappers_total": int(len(skipped_wrappers)),
        "skipped_root5_wrappers": skipped_wrappers,
    }


def _build_player_template_custom_variable_def_item(*, name: str, type_code: int, default_value: Any) -> Dict[str, Any]:
    """
    构造“玩家模板自定义变量定义”条目（可写入 root5['7'] / root4['8'] 的 group1 变量列表）。

    约定：默认值字段号 = type_code + 10（与真源样本一致）。
    """
    var_name = str(name or "").strip()
    if var_name == "":
        raise ValueError("variable name 不能为空")

    tc = int(type_code)
    if tc <= 0:
        raise ValueError(f"invalid type_code: {type_code!r}")

    empty = b""
    default_field = str(int(tc) + 10)

    # 默认值编码（尽量对齐真源：零/空/None 常用 empty bytes 表达）
    default_payload: Any = empty
    if tc in (1, 2, 3):
        v = int(default_value) if default_value is not None else 0
        default_payload = (empty if int(v) == 0 else {"1": int(v)})
    elif tc == 6:
        s = str(default_value) if default_value is not None else ""
        default_payload = (empty if s == "" else {"1": s})
    elif tc in (8, 11):
        # 列表：当前仅强支持空默认（与常见真源样本一致）
        if default_value is None:
            default_payload = empty
        elif isinstance(default_value, list) and len(default_value) == 0:
            default_payload = empty
        else:
            raise ValueError(f"列表类型默认值暂不支持非空写回：type_code={tc} default_value={default_value!r}")
    elif tc == 20:
        v = int(default_value) if default_value is not None else 0
        default_payload = (empty if int(v) == 0 else {"1": {"1": 1, "2": int(v)}})
    else:
        raise ValueError(f"暂不支持该自定义变量类型写回：type_code={tc}")

    return {
        "2": str(var_name),
        "3": int(tc),
        "4": {
            "1": int(tc),
            "2": {"1": int(tc), "2": b""},
            default_field: default_payload,
        },
        "5": 1,
        "6": {"1": int(tc), "2": b""},
    }


def _replace_group1_var_defs_in_group_list(group_list: Any, *, var_def_items: List[Dict[str, Any]]) -> List[Any]:
    """
    将 group_list 中的 group1(1/1) 变量列表替换为指定 items；保留其它 group 条目。
    """
    out: List[Any] = []
    if isinstance(group_list, list):
        for item in group_list:
            if isinstance(item, dict) and item.get("1") == 1 and item.get("2") == 1:
                continue
            out.append(copy.deepcopy(item))
    elif isinstance(group_list, dict):
        if not (group_list.get("1") == 1 and group_list.get("2") == 1):
            out.append(copy.deepcopy(group_list))
    elif group_list is None or isinstance(group_list, (bytes, bytearray)):
        out = []
    else:
        raise ValueError(f"group_list 结构异常（期望 list/dict/bytes/None）：{type(group_list).__name__}")

    out.append({"1": 1, "2": 1, "11": {"1": [dict(x) for x in list(var_def_items or [])]}})
    return out


def set_template_custom_variable_defs_inplace(
    payload_root: Dict[str, Any],
    *,
    template_name: str,
    variables: List[Tuple[str, int, Any]],
) -> Dict[str, Any]:
    """
    以“变量规格列表”覆盖指定玩家模板的自定义变量定义（group1）。

    - 写回：root5['7'] 与 root4['8']
    - 同步更新：所有引用同一 root4_entry_id 的 root5 wrapper（避免不一致）
    """
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")

    entry = _find_player_template_entry_by_name(payload_root, template_name=target)
    root5_entries = _get_root5_entries(payload_root)
    root4_entries = _get_root4_entries(payload_root)

    e5_rep = root5_entries[int(entry.root5_index)]
    e4 = root4_entries[int(entry.root4_index)]

    before_names = _extract_group1_variable_names(e5_rep.get("7"))

    # build var def items (keep input order; validate uniqueness)
    seen: set[str] = set()
    var_def_items: List[Dict[str, Any]] = []
    for name, type_code, default_value in list(variables or []):
        nm = str(name or "").strip()
        if nm == "":
            raise ValueError("variables 中存在空 variable_name")
        if nm in seen:
            raise ValueError(f"variables 存在重复 variable_name：{nm!r}")
        seen.add(nm)
        var_def_items.append(
            _build_player_template_custom_variable_def_item(name=nm, type_code=int(type_code), default_value=default_value)
        )

    if not var_def_items:
        raise ValueError("variables 不能为空（至少需要 1 个变量定义）")

    new_group7 = _replace_group1_var_defs_in_group_list(e5_rep.get("7"), var_def_items=var_def_items)
    new_group8 = _replace_group1_var_defs_in_group_list(e4.get("8"), var_def_items=var_def_items)
    e5_rep["7"] = new_group7
    e4["8"] = new_group8

    ref_indices = _iter_root5_indices_by_ref_id(payload_root, ref_id=int(entry.root4_entry_id))
    updated_wrappers: List[int] = []
    skipped_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = root5_entries[int(i)]
        if not isinstance(wrapper, dict):
            skipped_wrappers.append(int(i))
            continue
        if not _is_player_template_like_root5_entry(wrapper):
            skipped_wrappers.append(int(i))
            continue
        name = _extract_name_from_entry_meta_list(wrapper.get("5"))
        if name.endswith("(角色编辑)"):
            skipped_wrappers.append(int(i))
            continue
        if str(name) != target:
            skipped_wrappers.append(int(i))
            continue
        wrapper["7"] = copy.deepcopy(new_group7)
        updated_wrappers.append(int(i))

    after_names = _extract_group1_variable_names(e5_rep.get("7"))

    return {
        "template_name": target,
        "before_vars_total": int(len(before_names)),
        "before_vars_preview": before_names[:50],
        "after_vars_total": int(len(after_names)),
        "after_vars_preview": after_names[:50],
        "root4_entry_id": int(entry.root4_entry_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
        "skipped_root5_wrappers_total": int(len(skipped_wrappers)),
        "skipped_root5_wrappers": skipped_wrappers,
    }


def dump_player_templates_report(input_gil: Path) -> Dict[str, Any]:
    container = read_gil_container(Path(input_gil))
    payload_root = decode_message(container.payload)
    # 以 root5 的“展示条目”为准列出所有玩家模板（不做 root4 去重，避免漏掉“玩家1的模板/玩家2345的模板”这种别名条目）
    root5_entries = _get_root5_entries(payload_root)
    listed: List[Dict[str, Any]] = []
    # overlap 校验：以 root4_entry_id 去重后再检查
    by_root4: Dict[int, Tuple[str, Tuple[int, ...]]] = {}

    for i, e5 in enumerate(root5_entries):
        wrapper_id = e5.get("1")
        name = _extract_name_from_entry_meta_list(e5.get("5"))
        if name == "" or name.endswith("(角色编辑)"):
            continue
        if not _is_player_template_like_root5_entry(e5):
            continue
        ref_box = e5.get("2")
        ref_id = ref_box.get("1") if isinstance(ref_box, dict) else None
        if not isinstance(ref_id, int):
            continue
        players_bytes = _extract_players_bytes_from_entry_meta_list(e5.get("5"))
        players0: Optional[Tuple[int, ...]] = None
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


def write_back_payload(
    *,
    base_gil: Path,
    payload_root: Dict[str, Any],
    output_gil: Path,
) -> Path:
    base_container = read_gil_container(Path(base_gil))
    new_payload = encode_message(payload_root)
    out_bytes = build_gil_bytes_from_container(base=base_container, new_payload=new_payload)
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)
    return out_path


def load_payload_root(input_gil: Path) -> Tuple[GilContainer, Dict[str, Any]]:
    container = read_gil_container(Path(input_gil))
    payload_root = decode_message(container.payload)
    return container, payload_root


def find_bytes_fields_containing_pattern(
    payload_root: Dict[str, Any],
    *,
    pattern: bytes,
    limit: int = 50,
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
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    在已解码的 payload_root 中查找包含指定子串的字符串值，并返回其路径。
    """
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


def _read_single_varint_field_from_message_bytes(msg_bytes: bytes, *, field_number: int) -> int | None:
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(msg_bytes), start_offset=0, end_offset=len(msg_bytes))
    if int(consumed) != len(msg_bytes):
        raise ValueError("message bytes did not consume all bytes")
    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(field_number) or int(tag.wire_type) != 0:
            continue
        v, next_offset, ok = _decode_varint(bytes(value_raw), 0, len(value_raw))
        if not ok or int(next_offset) != len(value_raw):
            raise ValueError("invalid varint field encoding")
        return int(v)
    return None


def _read_single_length_delimited_payload_from_message_bytes(msg_bytes: bytes, *, field_number: int) -> bytes | None:
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(msg_bytes), start_offset=0, end_offset=len(msg_bytes))
    if int(consumed) != len(msg_bytes):
        raise ValueError("message bytes did not consume all bytes")
    found: bytes | None = None
    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(field_number):
            continue
        if int(tag.wire_type) != 2:
            raise ValueError(f"expected wire_type=2 for field {int(field_number)}, got {int(tag.wire_type)}")
        _len_raw, payload = _split_ld_value_raw(value_raw)
        if found is not None:
            raise ValueError(f"field {int(field_number)} occurs multiple times (unexpected)")
        found = bytes(payload)
    return found


def _extract_template_name_from_root5_entry_bytes(entry_bytes: bytes) -> str:
    """
    root5 wrapper entry 的名字来自 meta list（field 5）：
    - meta_item(field1==1) -> field11 message -> field1 utf8 string
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("root5 entry bytes did not consume all bytes")

    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 5 or int(tag.wire_type) != 2:
            continue
        _len_raw, meta_payload = _split_ld_value_raw(value_raw)
        if _read_single_varint_field_from_message_bytes(meta_payload, field_number=1) != 1:
            continue
        name_box = _read_single_length_delimited_payload_from_message_bytes(meta_payload, field_number=11)
        if name_box is None:
            continue
        raw_name = _read_single_length_delimited_payload_from_message_bytes(name_box, field_number=1)
        if raw_name is None:
            continue
        name = bytes(raw_name).decode("utf-8")
        if name.strip():
            return str(name).strip()
    return ""


def _extract_root5_ref_root4_entry_id(entry_bytes: bytes) -> int | None:
    ref_box = _read_single_length_delimited_payload_from_message_bytes(entry_bytes, field_number=2)
    if ref_box is None:
        return None
    return _read_single_varint_field_from_message_bytes(ref_box, field_number=1)


def _is_player_template_like_root5_entry_bytes(entry_bytes: bytes) -> bool:
    """
    依据真源样本的可解释特征（与 _is_player_template_like_root5_entry 对齐，但不解码为 dict）：
    - meta list（field 5）中存在 meta_item(field1==3) 且其 field12 message 内至少包含 field5/field6(varint)
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("root5 entry bytes did not consume all bytes")

    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 5 or int(tag.wire_type) != 2:
            continue
        _len_raw, meta_payload = _split_ld_value_raw(value_raw)
        if _read_single_varint_field_from_message_bytes(meta_payload, field_number=1) != 3:
            continue
        box12 = _read_single_length_delimited_payload_from_message_bytes(meta_payload, field_number=12)
        if box12 is None:
            continue
        if _read_single_varint_field_from_message_bytes(box12, field_number=5) is None:
            continue
        if _read_single_varint_field_from_message_bytes(box12, field_number=6) is None:
            continue
        return True
    return False


def _is_group1_container_item_bytes(group_item_bytes: bytes) -> bool:
    gid = _read_single_varint_field_from_message_bytes(group_item_bytes, field_number=1)
    gidx = _read_single_varint_field_from_message_bytes(group_item_bytes, field_number=2)
    return int(gid or 0) == 1 and int(gidx or 0) == 1


def _build_group1_container_item_bytes(*, variables: List[Tuple[str, int, Any]]) -> bytes:
    """
    构造 group1(1/1) 变量容器 item 的 message bytes：
    - item: {1:1, 2:1, 11:{1:[var_def_item...] } }

    注意：这里用本目录的 `gil_codec.encode_message` 构造该小段 message，
    因为它能直接编码 bytes（empty bytes）并且该结构不涉及 fixed32/fixed64。
    """
    var_defs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for name, type_code, default_value in list(variables or []):
        nm = str(name or "").strip()
        if nm == "":
            raise ValueError("variables 中存在空 variable_name")
        if nm in seen:
            raise ValueError(f"variables 存在重复 variable_name：{nm!r}")
        seen.add(nm)
        var_defs.append(_build_player_template_custom_variable_def_item(name=nm, type_code=int(type_code), default_value=default_value))
    if not var_defs:
        raise ValueError("variables 不能为空（至少需要 1 个变量定义）")
    item = {"1": 1, "2": 1, "11": {"1": [dict(x) for x in var_defs]}}
    return bytes(encode_message(dict(item)))


def _patch_group_list_field_in_entry_bytes(
    entry_bytes: bytes,
    *,
    group_field_number: int,
    new_group1_item_payload_bytes: bytes,
) -> bytes:
    """
    wire-level patch：在 entry message bytes 中替换/插入 group1 容器（repeated length-delimited field）。
    - 保留其它字段的 tag/value 原始字节不变
    - 保留其它 group item（非 group1）原始字节不变
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("entry bytes did not consume all bytes")

    out: List[Tuple[bytes, bytes]] = []
    group1_insert_at: int | None = None
    group1_tag_raw: bytes | None = None

    for tag_raw, value_raw in list(chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(group_field_number):
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue
        if int(tag.wire_type) != 2:
            raise ValueError(
                f"group field must be length-delimited: field={int(group_field_number)} got wire_type={int(tag.wire_type)}"
            )
        _len_raw, payload = _split_ld_value_raw(value_raw)
        if _is_group1_container_item_bytes(payload):
            if group1_insert_at is None:
                group1_insert_at = int(len(out))
                group1_tag_raw = bytes(tag_raw)
            # drop old group1 container
            continue
        # keep other groups untouched
        out.append((bytes(tag_raw), bytes(value_raw)))

    if group1_insert_at is None:
        # missing -> insert before first field_number greater than group_field_number (keep near-sorted)
        group1_insert_at = int(len(out))
        for i, (t_raw, _v_raw) in enumerate(list(out)):
            t = _parse_tag_raw(t_raw)
            if int(t.field_number) > int(group_field_number):
                group1_insert_at = int(i)
                break
        group1_tag_raw = bytes(_encode_tag(int(group_field_number), 2))

    if group1_tag_raw is None:
        raise RuntimeError("internal error: group1_tag_raw is None")

    new_value_raw = bytes(_encode_varint(int(len(new_group1_item_payload_bytes)))) + bytes(new_group1_item_payload_bytes)
    out.insert(int(group1_insert_at), (bytes(group1_tag_raw), bytes(new_value_raw)))
    return bytes(_encode_wire_chunks(list(out)))


def _patch_section_entries_field1_by_predicate(
    section_bytes: bytes,
    *,
    should_patch_entry: Any,
    patch_entry_bytes: Any,
) -> Tuple[bytes, int]:
    """
    对 section message bytes 中 field_1(repeated entry bytes) 做按 predicate 的定点替换。
    返回：(new_section_bytes, patched_count)
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(section_bytes), start_offset=0, end_offset=len(section_bytes))
    if int(consumed) != len(section_bytes):
        raise ValueError("section bytes did not consume all bytes")

    out: List[Tuple[bytes, bytes]] = []
    patched = 0
    for tag_raw, value_raw in list(chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 1 or int(tag.wire_type) != 2:
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue

        _len_raw, payload = _split_ld_value_raw(value_raw)
        if not bool(should_patch_entry(payload)):
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue

        new_payload = bytes(patch_entry_bytes(payload))
        new_value_raw = bytes(_encode_varint(len(new_payload))) + new_payload
        out.append((bytes(tag_raw), bytes(new_value_raw)))
        patched += 1

    return bytes(_encode_wire_chunks(list(out))), int(patched)


def patch_player_template_custom_variable_defs_in_gil(
    *,
    input_gil: Path,
    output_gil: Path,
    template_name: str,
    variables: List[Tuple[str, int, Any]],
) -> Dict[str, Any]:
    """
    安全写回：仅对玩家模板的变量定义字段做 wire-level 补丁，避免全量 decode/encode 造成 payload drift。

    修改范围（按已验证真源结构）：
    - payload_root field 5（root5 wrappers）：对匹配 template_name 的玩家模板 wrapper 条目，补齐/替换 field 7 的 group1 变量容器
    - payload_root field 4（root4 entries）：对 wrapper 引用到的 root4_entry_id，补齐/替换 field 8 的 group1 变量容器

    不修改其它 payload_root 字段 bytes。
    """
    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    container = read_gil_container(in_path)
    payload = bytes(container.payload)

    # 1) parse payload_root and locate section 4/5
    root_chunks, consumed = _decode_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if int(consumed) != len(payload):
        raise ValueError("payload_root did not consume all bytes")

    section4_payload: bytes | None = None
    section5_payload: bytes | None = None
    section4_idx: int | None = None
    section5_idx: int | None = None

    for i, (tag_raw, value_raw) in enumerate(list(root_chunks)):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.wire_type) != 2:
            continue
        if int(tag.field_number) == 4:
            if section4_payload is not None:
                raise ValueError("payload_root field 4 occurs multiple times (unexpected)")
            _len_raw, section4_payload = _split_ld_value_raw(value_raw)
            section4_idx = int(i)
        if int(tag.field_number) == 5:
            if section5_payload is not None:
                raise ValueError("payload_root field 5 occurs multiple times (unexpected)")
            _len_raw, section5_payload = _split_ld_value_raw(value_raw)
            section5_idx = int(i)

    if section4_payload is None or section4_idx is None:
        raise ValueError("payload_root missing field 4 (root4 section)")
    if section5_payload is None or section5_idx is None:
        raise ValueError("payload_root missing field 5 (root5 section)")

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    # 2) build group1 item payload bytes once
    group1_item_bytes = _build_group1_container_item_bytes(variables=variables)

    # 3) find target wrappers in section5 (by name + signature) and ensure single ref_id
    s5_chunks, consumed5 = _decode_wire_chunks(data_bytes=section5_payload, start_offset=0, end_offset=len(section5_payload))
    if int(consumed5) != len(section5_payload):
        raise ValueError("section5 did not consume all bytes")

    matched_wrapper_indices: List[int] = []
    ref_ids: List[int] = []
    for idx, (tag_raw, value_raw) in enumerate(list(s5_chunks)):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 1 or int(tag.wire_type) != 2:
            continue
        _len_raw, entry_payload = _split_ld_value_raw(value_raw)
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            continue
        name = _extract_template_name_from_root5_entry_bytes(entry_payload)
        if str(name) != target_name:
            continue
        if str(name).endswith("(角色编辑)"):
            continue
        rid = _extract_root5_ref_root4_entry_id(entry_payload)
        if not isinstance(rid, int):
            continue
        matched_wrapper_indices.append(int(idx))
        ref_ids.append(int(rid))

    if not matched_wrapper_indices:
        raise ValueError(f"未在 root5 section 找到玩家模板 wrapper：template_name={target_name!r}")

    ref_ids_unique = sorted(set(int(x) for x in ref_ids))
    if len(ref_ids_unique) != 1:
        raise ValueError(f"同名玩家模板 wrapper 引用多个 root4_entry_id：template={target_name!r} ref_ids={ref_ids_unique!r}")
    target_root4_entry_id = int(ref_ids_unique[0])

    # 4) patch section5 wrappers: field7 group list
    def _should_patch_root5_entry(entry_payload: bytes) -> bool:
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            return False
        if _extract_template_name_from_root5_entry_bytes(entry_payload) != target_name:
            return False
        if str(target_name).endswith("(角色编辑)"):
            return False
        rid2 = _extract_root5_ref_root4_entry_id(entry_payload)
        return isinstance(rid2, int) and int(rid2) == int(target_root4_entry_id)

    def _patch_root5_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=7,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section5, patched_wrappers = _patch_section_entries_field1_by_predicate(
        section5_payload,
        should_patch_entry=_should_patch_root5_entry,
        patch_entry_bytes=_patch_root5_entry,
    )
    if int(patched_wrappers) <= 0:
        raise RuntimeError("internal error: matched wrappers but patched 0 entries")

    # 5) patch section4 entry: field8 group list (by root4_entry_id)
    def _should_patch_root4_entry(entry_payload: bytes) -> bool:
        vid = _read_single_varint_field_from_message_bytes(entry_payload, field_number=1)
        return isinstance(vid, int) and int(vid) == int(target_root4_entry_id)

    def _patch_root4_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=8,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section4, patched_root4 = _patch_section_entries_field1_by_predicate(
        section4_payload,
        should_patch_entry=_should_patch_root4_entry,
        patch_entry_bytes=_patch_root4_entry,
    )
    if int(patched_root4) != 1:
        raise ValueError(f"root4 section 命中条目数量异常：expected=1 actual={int(patched_root4)} root4_entry_id={int(target_root4_entry_id)}")

    # 6) rebuild payload_root chunks (only replace field4/5 value_raw)
    if section4_idx is None or section5_idx is None:
        raise RuntimeError("internal error: missing section indices")

    new_root_chunks = list(root_chunks)
    # replace field4
    tag4_raw, _old4_value_raw = new_root_chunks[int(section4_idx)]
    new_root_chunks[int(section4_idx)] = (
        bytes(tag4_raw),
        bytes(_encode_varint(len(patched_section4))) + bytes(patched_section4),
    )
    # replace field5
    tag5_raw, _old5_value_raw = new_root_chunks[int(section5_idx)]
    new_root_chunks[int(section5_idx)] = (
        bytes(tag5_raw),
        bytes(_encode_varint(len(patched_section5))) + bytes(patched_section5),
    )
    new_payload = bytes(_encode_wire_chunks(list(new_root_chunks)))

    out_bytes = build_gil_bytes_from_container(base=container, new_payload=new_payload)
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    return {
        "input_gil": str(in_path),
        "output_gil": str(out_path),
        "template_name": target_name,
        "root4_entry_id": int(target_root4_entry_id),
        "patched_root5_wrappers": int(patched_wrappers),
        "variables_total": int(len(list(variables or []))),
    }


def extract_player_template_group1_container_item_bytes_from_gil(
    *,
    input_gil: Path,
    template_name: str,
) -> bytes:
    """
    从指定 `.gil` 中提取玩家模板（root5 wrapper）的 group1(1/1) 变量容器 item 的 message bytes（payload，不含外层 length varint）。

    用途：
    - `copy-vars`：将参考 `.gil` 的变量定义“原样拷贝”到目标 `.gil`，避免重新构造导致类型/默认值漂移。
    """
    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    container = read_gil_container(in_path)
    payload = bytes(container.payload)

    root_chunks, consumed = _decode_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if int(consumed) != len(payload):
        raise ValueError("payload_root did not consume all bytes")

    section5_payload: bytes | None = None
    for tag_raw, value_raw in list(root_chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 5 or int(tag.wire_type) != 2:
            continue
        if section5_payload is not None:
            raise ValueError("payload_root field 5 occurs multiple times (unexpected)")
        _len_raw, section5_payload = _split_ld_value_raw(value_raw)

    if section5_payload is None:
        raise ValueError("payload_root missing field 5 (root5 section)")

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    s5_chunks, consumed5 = _decode_wire_chunks(data_bytes=section5_payload, start_offset=0, end_offset=len(section5_payload))
    if int(consumed5) != len(section5_payload):
        raise ValueError("section5 did not consume all bytes")

    for tag_raw, value_raw in list(s5_chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 1 or int(tag.wire_type) != 2:
            continue
        _len_raw, entry_payload = _split_ld_value_raw(value_raw)
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            continue
        name = _extract_template_name_from_root5_entry_bytes(entry_payload)
        if str(name) != target_name:
            continue

        # 在该 wrapper entry 内找到 field7 的 group1 item
        e_chunks, consumed_e = _decode_wire_chunks(
            data_bytes=bytes(entry_payload),
            start_offset=0,
            end_offset=len(entry_payload),
        )
        if int(consumed_e) != len(entry_payload):
            raise ValueError("entry payload did not consume all bytes")

        for t_raw, v_raw in list(e_chunks):
            t = _parse_tag_raw(t_raw)
            if int(t.field_number) != 7 or int(t.wire_type) != 2:
                continue
            _len_raw2, group_item_payload = _split_ld_value_raw(v_raw)
            if _is_group1_container_item_bytes(group_item_payload):
                return bytes(group_item_payload)

        raise ValueError(f"模板存在但未找到 group1 变量容器：template={target_name!r}")

    raise ValueError(f"未找到玩家模板：template_name={target_name!r}")


def patch_player_template_custom_variable_group1_item_bytes_in_gil(
    *,
    input_gil: Path,
    output_gil: Path,
    template_name: str,
    group1_container_item_bytes: bytes,
) -> Dict[str, Any]:
    """
    安全写回：使用外部提供的 group1 容器 item bytes（原样），补丁到目标 `.gil` 的玩家模板变量定义字段。

    适用于：从参考 `.gil` 复制变量定义（支持复杂类型/默认值，无需重新构造）。
    """
    if not isinstance(group1_container_item_bytes, (bytes, bytearray)):
        raise TypeError("group1_container_item_bytes must be bytes")
    group1_item_bytes = bytes(group1_container_item_bytes)
    if group1_item_bytes == b"":
        raise ValueError("group1_container_item_bytes 不能为空")

    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    container = read_gil_container(in_path)
    payload = bytes(container.payload)

    # parse payload_root and locate section 4/5
    root_chunks, consumed = _decode_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if int(consumed) != len(payload):
        raise ValueError("payload_root did not consume all bytes")

    section4_payload: bytes | None = None
    section5_payload: bytes | None = None
    section4_idx: int | None = None
    section5_idx: int | None = None

    for i, (tag_raw, value_raw) in enumerate(list(root_chunks)):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.wire_type) != 2:
            continue
        if int(tag.field_number) == 4:
            if section4_payload is not None:
                raise ValueError("payload_root field 4 occurs multiple times (unexpected)")
            _len_raw, section4_payload = _split_ld_value_raw(value_raw)
            section4_idx = int(i)
        if int(tag.field_number) == 5:
            if section5_payload is not None:
                raise ValueError("payload_root field 5 occurs multiple times (unexpected)")
            _len_raw, section5_payload = _split_ld_value_raw(value_raw)
            section5_idx = int(i)

    if section4_payload is None or section4_idx is None:
        raise ValueError("payload_root missing field 4 (root4 section)")
    if section5_payload is None or section5_idx is None:
        raise ValueError("payload_root missing field 5 (root5 section)")

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    # find target wrappers in section5 (by name + signature) and ensure single ref_id
    s5_chunks, consumed5 = _decode_wire_chunks(data_bytes=section5_payload, start_offset=0, end_offset=len(section5_payload))
    if int(consumed5) != len(section5_payload):
        raise ValueError("section5 did not consume all bytes")

    ref_ids: List[int] = []
    for tag_raw, value_raw in list(s5_chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != 1 or int(tag.wire_type) != 2:
            continue
        _len_raw, entry_payload = _split_ld_value_raw(value_raw)
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            continue
        name = _extract_template_name_from_root5_entry_bytes(entry_payload)
        if str(name) != target_name:
            continue
        rid = _extract_root5_ref_root4_entry_id(entry_payload)
        if isinstance(rid, int):
            ref_ids.append(int(rid))

    if not ref_ids:
        raise ValueError(f"未在 root5 section 找到玩家模板 wrapper：template_name={target_name!r}")

    ref_ids_unique = sorted(set(int(x) for x in ref_ids))
    if len(ref_ids_unique) != 1:
        raise ValueError(f"同名玩家模板 wrapper 引用多个 root4_entry_id：template={target_name!r} ref_ids={ref_ids_unique!r}")
    target_root4_entry_id = int(ref_ids_unique[0])

    # patch section5 wrappers: field7 group list
    def _should_patch_root5_entry(entry_payload: bytes) -> bool:
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            return False
        if _extract_template_name_from_root5_entry_bytes(entry_payload) != target_name:
            return False
        rid2 = _extract_root5_ref_root4_entry_id(entry_payload)
        return isinstance(rid2, int) and int(rid2) == int(target_root4_entry_id)

    def _patch_root5_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=7,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section5, patched_wrappers = _patch_section_entries_field1_by_predicate(
        section5_payload,
        should_patch_entry=_should_patch_root5_entry,
        patch_entry_bytes=_patch_root5_entry,
    )
    if int(patched_wrappers) <= 0:
        raise RuntimeError("internal error: matched wrappers but patched 0 entries")

    # patch section4 entry: field8 group list (by root4_entry_id)
    def _should_patch_root4_entry(entry_payload: bytes) -> bool:
        vid = _read_single_varint_field_from_message_bytes(entry_payload, field_number=1)
        return isinstance(vid, int) and int(vid) == int(target_root4_entry_id)

    def _patch_root4_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=8,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section4, patched_root4 = _patch_section_entries_field1_by_predicate(
        section4_payload,
        should_patch_entry=_should_patch_root4_entry,
        patch_entry_bytes=_patch_root4_entry,
    )
    if int(patched_root4) != 1:
        raise ValueError(
            f"root4 section 命中条目数量异常：expected=1 actual={int(patched_root4)} root4_entry_id={int(target_root4_entry_id)}"
        )

    # rebuild payload_root chunks (only replace field4/5 value_raw)
    new_root_chunks = list(root_chunks)
    tag4_raw, _old4_value_raw = new_root_chunks[int(section4_idx)]
    new_root_chunks[int(section4_idx)] = (
        bytes(tag4_raw),
        bytes(_encode_varint(len(patched_section4))) + bytes(patched_section4),
    )
    tag5_raw, _old5_value_raw = new_root_chunks[int(section5_idx)]
    new_root_chunks[int(section5_idx)] = (
        bytes(tag5_raw),
        bytes(_encode_varint(len(patched_section5))) + bytes(patched_section5),
    )
    new_payload = bytes(_encode_wire_chunks(list(new_root_chunks)))

    out_bytes = build_gil_bytes_from_container(base=container, new_payload=new_payload)
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    return {
        "input_gil": str(in_path),
        "output_gil": str(out_path),
        "template_name": target_name,
        "root4_entry_id": int(target_root4_entry_id),
        "patched_root5_wrappers": int(patched_wrappers),
    }
