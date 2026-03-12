from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..gil_codec import decode_packed_varints, encode_packed_varints

from .common import (
    ALL_PLAYERS_0_BASED,
    META_ITEM_ID_KEY,
    META_ITEM_ID_NAME,
    META_ITEM_ID_PLAYERS,
    META_NAME_BOX_KEY,
    META_NAME_TEXT_KEY,
    META_PLAYERS_BOX_FIELD5_KEY,
    META_PLAYERS_BOX_FIELD6_KEY,
    META_PLAYERS_BOX_KEY,
    META_PLAYERS_BYTES_KEY,
    ROOT4_META_LIST_KEY,
    ROOT4_SECTION_KEY,
    ROOT5_META_LIST_KEY,
    ROOT5_REF_BOX_KEY,
    ROOT5_SECTION_KEY,
    ROOT_ENTRY_ID_KEY,
    ROLE_EDIT_SUFFIX,
    SECTION_ENTRIES_KEY,
    PlayerTemplateRef,
    _enforce_no_overlap_or_raise,
    _normalize_player_index_list,
    _parse_human_players,
    _players_to_human,
)


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
    section = payload_root.get(ROOT4_SECTION_KEY)
    if not isinstance(section, dict):
        return []
    entries = section.get(SECTION_ENTRIES_KEY)
    if isinstance(entries, list):
        return [e for e in entries if isinstance(e, dict)]
    if isinstance(entries, dict):
        return [entries]
    return []


def _get_root5_entries(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    section = payload_root.get(ROOT5_SECTION_KEY)
    if not isinstance(section, dict):
        return []
    entries = section.get(SECTION_ENTRIES_KEY)
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
        e_name = _extract_name_from_entry_meta_list(e.get(ROOT5_META_LIST_KEY))
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
        rid = e.get(ROOT_ENTRY_ID_KEY)
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
        if item.get(META_ITEM_ID_KEY) != META_ITEM_ID_NAME:
            continue
        name_box = item.get(META_NAME_BOX_KEY)
        if not isinstance(name_box, dict):
            continue
        name = name_box.get(META_NAME_TEXT_KEY)
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
        if item.get(META_ITEM_ID_KEY) != META_ITEM_ID_PLAYERS:
            continue
        box = item.get(META_PLAYERS_BOX_KEY)
        if not isinstance(box, dict):
            continue
        raw = box.get(META_PLAYERS_BYTES_KEY)
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
    meta = entry.get(ROOT5_META_LIST_KEY)
    if not isinstance(meta, list):
        return False
    for item in meta:
        if not isinstance(item, dict):
            continue
        if item.get(META_ITEM_ID_KEY) != META_ITEM_ID_PLAYERS:
            continue
        box = item.get(META_PLAYERS_BOX_KEY)
        if not isinstance(box, dict):
            continue
        if not isinstance(box.get(META_PLAYERS_BOX_FIELD5_KEY), int):
            return False
        if not isinstance(box.get(META_PLAYERS_BOX_FIELD6_KEY), int):
            return False
        return True
    return False


def _iter_root5_indices_by_ref_id(payload_root: Dict[str, Any], *, ref_id: int) -> List[int]:
    out: List[int] = []
    entries = _get_root5_entries(payload_root)
    target = int(ref_id)
    for i, e5 in enumerate(entries):
        ref_box = e5.get(ROOT5_REF_BOX_KEY)
        rid = ref_box.get(ROOT_ENTRY_ID_KEY) if isinstance(ref_box, dict) else None
        if isinstance(rid, int) and int(rid) == target:
            out.append(int(i))
    return out


def list_player_templates(payload_root: Dict[str, Any]) -> List[PlayerTemplateEntry]:
    root4 = _get_root4_entries(payload_root)
    root5 = _get_root5_entries(payload_root)
    root4_by_id: Dict[int, Tuple[int, Dict[str, Any]]] = {}
    for idx, e4 in enumerate(root4):
        rid = e4.get(ROOT_ENTRY_ID_KEY)
        if isinstance(rid, int):
            root4_by_id[int(rid)] = (int(idx), e4)

    out: List[PlayerTemplateEntry] = []
    for idx, e5 in enumerate(root5):
        # 只识别“玩家模板 wrapper 条目”（避免把其它模板/资源条目误当成玩家模板）。
        if not _is_player_template_like_root5_entry(e5):
            continue
        ref_box = e5.get(ROOT5_REF_BOX_KEY)
        ref_id = ref_box.get(ROOT_ENTRY_ID_KEY) if isinstance(ref_box, dict) else None
        if not isinstance(ref_id, int):
            continue
        root4_hit = root4_by_id.get(int(ref_id))
        if root4_hit is None:
            continue
        root4_index, e4 = root4_hit

        name = _extract_name_from_entry_meta_list(e5.get(ROOT5_META_LIST_KEY))
        if name == "":
            continue
        # 只把“普通条目”当作玩家模板入口；角色编辑条目用于 UI/编辑器形态，不承载生效玩家/变量定义
        if name.endswith(ROLE_EDIT_SUFFIX):
            continue

        players_bytes = _extract_players_bytes_from_entry_meta_list(e5.get(ROOT5_META_LIST_KEY))
        players: Optional[Tuple[int, ...]] = None
        if isinstance(players_bytes, (bytes, bytearray)):
            players = _decode_players_bytes(bytes(players_bytes))

        wrapper_id = e5.get(ROOT_ENTRY_ID_KEY)
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
    ref_box = e5.get(ROOT5_REF_BOX_KEY)
    ref_id = ref_box.get(ROOT_ENTRY_ID_KEY) if isinstance(ref_box, dict) else None
    if not isinstance(ref_id, int):
        raise ValueError(f"模板 {target!r} 缺少 root4 引用：entry['2']['1']")
    root4_index = _find_root4_entry_index_by_id(payload_root, entry_id=int(ref_id))
    root4_entries = _get_root4_entries(payload_root)
    e4 = root4_entries[root4_index]

    before_bytes = _extract_players_bytes_from_entry_meta_list(e5.get(ROOT5_META_LIST_KEY))
    before_players = _decode_players_bytes(before_bytes) if isinstance(before_bytes, (bytes, bytearray)) else None

    # 写回策略：
    # - 指定玩家集合 => 写入 packed bytes
    # - 若指定为全体(1..8) => 删除该字段（对齐“空存档/默认全体”的缺省形态）
    is_all = tuple(new_players) == ALL_PLAYERS_0_BASED
    encoded = encode_packed_varints(list(new_players))

    def _set_players_bytes_on_meta_list(meta_list: Any, *, players_bytes: Optional[bytes]) -> None:
        if not isinstance(meta_list, list):
            raise ValueError("entry meta_list is not list")
        for item in meta_list:
            if not isinstance(item, dict):
                continue
            if item.get(META_ITEM_ID_KEY) != META_ITEM_ID_PLAYERS:
                continue
            box = item.get(META_PLAYERS_BOX_KEY)
            if not isinstance(box, dict):
                raise ValueError("players box missing: item['12'] is not dict")
            if players_bytes is None:
                box.pop(META_PLAYERS_BYTES_KEY, None)
            else:
                box[META_PLAYERS_BYTES_KEY] = bytes(players_bytes)
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
        _set_players_bytes_on_meta_list(wrapper.get(ROOT5_META_LIST_KEY), players_bytes=(None if is_all else encoded))
        changed_wrappers.append(int(i))
    _set_players_bytes_on_meta_list(e4.get(ROOT4_META_LIST_KEY), players_bytes=(None if is_all else encoded))

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

