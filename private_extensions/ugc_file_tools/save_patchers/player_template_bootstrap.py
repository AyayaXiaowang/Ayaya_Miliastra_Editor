from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gil_codec import decode_message, read_gil_container
from .player_templates import (
    _get_root4_entries,
    _get_root5_entries,
    _extract_name_from_entry_meta_list,
    _extract_players_bytes_from_entry_meta_list,
    _decode_players_bytes,
    _players_to_human,
    _parse_human_players,
    list_player_templates,
)


@dataclass(frozen=True)
class BootstrapSeed:
    payload_root: Dict[str, Any]


def load_seed_from_gil(seed_gil: Path) -> BootstrapSeed:
    c = read_gil_container(Path(seed_gil))
    root = decode_message(c.payload)
    if not isinstance(root, dict):
        raise TypeError("seed payload_root must be dict")
    return BootstrapSeed(payload_root=root)


def _get_section_or_raise(payload_root: Dict[str, Any], key: str) -> Dict[str, Any]:
    section = payload_root.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"payload_root 缺少 dict 字段 {key!r}")
    return section


def bootstrap_player_template_sections_inplace(
    payload_root: Dict[str, Any],
    *,
    seed: BootstrapSeed,
) -> Dict[str, Any]:
    """
    为“空存档（缺少 root4['4']/root4['5']）”自举玩家模板段的 section 外壳。

    原理（可解释）：
    - 玩家模板相关数据存在于 payload_root 的两个 section：
      - `payload_root['4']['1']`: 模板主条目（被 root5 引用）
      - `payload_root['5']['1']`: 模板 wrapper/索引条目（含展示/引用信息）
    - 空存档可能完全没有这些 section；此时必须创建它们才能写入模板。
    - 由于 section 内可能存在除 `['1']` 之外的必要元数据，本函数从 seed 中复制 section 外壳，
      但会清空 `['1']` 使其变为“无模板列表”的干净状态。
    """
    seed_root = seed.payload_root
    seed_s4 = _get_section_or_raise(seed_root, "4")
    seed_s5 = _get_section_or_raise(seed_root, "5")

    created = []
    for k, seed_section in (("4", seed_s4), ("5", seed_s5)):
        section = payload_root.get(k)
        if isinstance(section, dict):
            # 已存在则不覆盖
            continue
        new_section = copy.deepcopy(seed_section)
        new_section["1"] = []
        payload_root[k] = new_section
        created.append(k)

    return {"created_sections": created, "note": "仅创建玩家模板所需 section 外壳，并清空 entries。"}


def _collect_all_entry_ids(payload_root: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    for e in _get_root4_entries(payload_root):
        v = e.get("1")
        if isinstance(v, int):
            ids.append(int(v))
    for e in _get_root5_entries(payload_root):
        v = e.get("1")
        if isinstance(v, int):
            ids.append(int(v))
    return ids


def _allocate_new_id(payload_root: Dict[str, Any], *, seed: BootstrapSeed) -> int:
    raise RuntimeError("use _allocate_new_id_with_reserved(...) instead")


def _allocate_new_id_with_reserved(
    payload_root: Dict[str, Any],
    *,
    seed: BootstrapSeed,
    reserved_ids: set[int],
) -> int:
    existing = set(_collect_all_entry_ids(payload_root)) | set(int(x) for x in reserved_ids)
    seed_existing = set(_collect_all_entry_ids(seed.payload_root))
    base = 1
    if seed_existing:
        base = max(seed_existing) + 1
    if existing:
        base = max(base, max(existing) + 1)
    while base in existing:
        base += 1
    reserved_ids.add(int(base))
    return int(base)


def _find_root5_entry_index_by_name(payload_root: Dict[str, Any], *, name: str) -> int:
    n = str(name or "").strip()
    if n == "":
        raise ValueError("name 不能为空")
    entries = _get_root5_entries(payload_root)
    hit: Optional[int] = None
    for i, e in enumerate(entries):
        e_name = _extract_name_from_entry_meta_list(e.get("5"))
        if e_name == n:
            if hit is not None:
                raise ValueError(f"存在多个同名条目：{n!r}（root5 index {hit} 与 {i}）")
            hit = int(i)
    if hit is None:
        raise ValueError(f"未找到条目：{n!r}")
    return int(hit)


def _clone_entry_pair_from_seed(
    *,
    seed: BootstrapSeed,
    base_name: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    从 seed 里按名字克隆一对（普通条目 + 角色编辑条目）的 root4/root5 entry。
    返回：(root4_normal, root5_normal, root4_role, root5_role)
    """
    seed_root = seed.payload_root
    seed_root5 = _get_root5_entries(seed_root)
    seed_root4 = _get_root4_entries(seed_root)

    normal_idx = _find_root5_entry_index_by_name(seed_root, name=str(base_name))
    role_idx = _find_root5_entry_index_by_name(seed_root, name=f"{str(base_name)}(角色编辑)")

    e5_normal = copy.deepcopy(seed_root5[normal_idx])
    e5_role = copy.deepcopy(seed_root5[role_idx])

    ref_normal = e5_normal.get("2")
    ref_role = e5_role.get("2")
    ref_normal_id = ref_normal.get("1") if isinstance(ref_normal, dict) else None
    ref_role_id = ref_role.get("1") if isinstance(ref_role, dict) else None
    if not isinstance(ref_normal_id, int):
        raise ValueError("seed normal entry missing ref id")
    if not isinstance(ref_role_id, int):
        raise ValueError("seed role entry missing ref id")

    root4_by_id: Dict[int, Dict[str, Any]] = {}
    for e4 in seed_root4:
        rid = e4.get("1")
        if isinstance(rid, int):
            root4_by_id[int(rid)] = e4
    e4_normal = copy.deepcopy(root4_by_id[int(ref_normal_id)])
    e4_role = copy.deepcopy(root4_by_id[int(ref_role_id)])

    return e4_normal, e5_normal, e4_role, e5_role


def create_player_template_inplace(
    payload_root: Dict[str, Any],
    *,
    seed: BootstrapSeed,
    # 基础模板从 seed 克隆（建议使用：自定义玩家模版）
    base_template_name: str,
    new_template_name: str,
    players_1_based: Optional[List[int]],
    copy_custom_variable_defs_from_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    新建玩家模板（含角色编辑条目）。

    可解释规则：
    - 需要同时新增 4 个 entry：
      - root4 普通条目（模板本体）
      - root5 普通 wrapper（展示名 + 引用 root4）
      - root4 角色编辑条目（编辑器 UI 的“角色编辑”版本）
      - root5 角色编辑 wrapper（名称带 “(角色编辑)” 且 self-ref）
    - 生效玩家：
      - 写在普通条目的 meta item(id=3) -> box['12']['4']（packed players，0..7）
      - 若希望“全部玩家”，则删除 field_4（与样本：自定义变量/自定义玩家模版一致）
    - 自定义变量定义：
      - 写在普通条目的 group1 容器中（root5['7'] / root4['8']）
    """
    bootstrap_player_template_sections_inplace(payload_root, seed=seed)

    # 从 seed 克隆 base
    e4_normal, e5_normal, e4_role, e5_role = _clone_entry_pair_from_seed(seed=seed, base_name=str(base_template_name))

    new_name = str(new_template_name or "").strip()
    if new_name == "":
        raise ValueError("new_template_name 不能为空")

    # allocate ids
    reserved: set[int] = set()
    new_root4_id = _allocate_new_id_with_reserved(payload_root, seed=seed, reserved_ids=reserved)
    new_root5_id = _allocate_new_id_with_reserved(payload_root, seed=seed, reserved_ids=reserved)
    new_role_id = _allocate_new_id_with_reserved(payload_root, seed=seed, reserved_ids=reserved)

    # patch ids/refs
    e4_normal["1"] = int(new_root4_id)
    e5_normal["1"] = int(new_root5_id)
    e5_normal["2"] = {"1": int(new_root4_id)}

    e4_role["1"] = int(new_role_id)
    e5_role["1"] = int(new_role_id)
    e5_role["2"] = {"1": int(new_role_id)}

    # patch names in root5 meta list and root4 meta list
    def _set_name_in_root5_meta(entry: Dict[str, Any], name: str) -> None:
        meta = entry.get("5")
        if not isinstance(meta, list):
            raise ValueError("entry['5'] is not list")
        for item in meta:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 1:
                continue
            box = item.get("11")
            if not isinstance(box, dict):
                raise ValueError("name box missing")
            box["1"] = str(name)
            return
        raise ValueError("name meta item not found")

    def _set_name_in_root4_meta(entry: Dict[str, Any], name: str) -> None:
        meta = entry.get("6")
        if not isinstance(meta, list):
            raise ValueError("root4 entry['6'] is not list")
        for item in meta:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 1:
                continue
            box = item.get("11")
            if not isinstance(box, dict):
                raise ValueError("root4 name box missing")
            box["1"] = str(name)
            return
        raise ValueError("root4 name meta item not found")

    _set_name_in_root5_meta(e5_normal, new_name)
    _set_name_in_root4_meta(e4_normal, new_name)
    _set_name_in_root5_meta(e5_role, f"{new_name}(角色编辑)")
    _set_name_in_root4_meta(e4_role, f"{new_name}(角色编辑)")

    # patch players (normal only)
    players0 = tuple(range(8)) if players_1_based is None else _parse_human_players(players_1_based)
    want_all = players0 == tuple(range(8))

    def _set_players_bytes_in_root5(entry: Dict[str, Any], players0: Tuple[int, ...]) -> None:
        meta = entry.get("5")
        if not isinstance(meta, list):
            raise ValueError("entry['5'] is not list")
        for item in meta:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 3:
                continue
            box = item.get("12")
            if not isinstance(box, dict):
                raise ValueError("players box missing")
            if want_all:
                box.pop("4", None)
            else:
                box["4"] = bytes(_encode_players(players0))
            return
        raise ValueError("players meta item not found")

    def _set_players_bytes_in_root4(entry: Dict[str, Any], players0: Tuple[int, ...]) -> None:
        meta = entry.get("6")
        if not isinstance(meta, list):
            raise ValueError("root4 entry['6'] is not list")
        for item in meta:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 3:
                continue
            box = item.get("12")
            if not isinstance(box, dict):
                raise ValueError("root4 players box missing")
            if want_all:
                box.pop("4", None)
            else:
                box["4"] = bytes(_encode_players(players0))
            return
        raise ValueError("root4 players meta item not found")

    def _encode_players(players0: Tuple[int, ...]) -> bytes:
        # packed varints（0..7 在样本中等价于单字节序列；这里仍按 varint 规则编码）
        out = bytearray()
        for v in players0:
            out.append(int(v))
        return bytes(out)

    _set_players_bytes_in_root5(e5_normal, players0)
    _set_players_bytes_in_root4(e4_normal, players0)

    # optional: copy custom variable defs from another template (e.g. 自定义变量)
    if copy_custom_variable_defs_from_name:
        src_name = str(copy_custom_variable_defs_from_name).strip()
        if src_name == "":
            raise ValueError("copy_custom_variable_defs_from_name 不能为空")
        existing = list_player_templates(payload_root)
        src = [t for t in existing if t.name == src_name]
        if not src:
            # base 可能是空存档：此时 payload_root 里还没有任何模板，允许从 seed 里拷贝
            seed_existing = list_player_templates(seed.payload_root)
            src_seed = [t for t in seed_existing if t.name == src_name]
            if not src_seed:
                raise ValueError(f"未找到用于拷贝变量定义的模板：{src_name!r}（base/seed 都没有）")
            if len(src_seed) > 1:
                raise ValueError(f"seed 中存在多个同名模板用于拷贝变量定义：{src_name!r}")

            src_t = src_seed[0]
            seed_root5 = _get_root5_entries(seed.payload_root)
            seed_root4 = _get_root4_entries(seed.payload_root)
            src_e5 = seed_root5[src_t.root5_index]
            src_e4 = seed_root4[src_t.root4_index]
            e5_normal["7"] = copy.deepcopy(src_e5.get("7"))
            e4_normal["8"] = copy.deepcopy(src_e4.get("8"))
        else:
            if len(src) > 1:
                raise ValueError(f"存在多个同名模板用于拷贝变量定义：{src_name!r}")
            # 复制 root5['7'] / root4['8'] 的 group1 变量容器（保持结构一致）
            src_t = src[0]
            root5_entries = _get_root5_entries(payload_root)
            root4_entries = _get_root4_entries(payload_root)
            src_e5 = root5_entries[src_t.root5_index]
            src_e4 = root4_entries[src_t.root4_index]
            e5_normal["7"] = copy.deepcopy(src_e5.get("7"))
            e4_normal["8"] = copy.deepcopy(src_e4.get("8"))

    # append entries into base sections
    sec4 = _get_section_or_raise(payload_root, "4")
    sec5 = _get_section_or_raise(payload_root, "5")
    sec4.setdefault("1", []).extend([e4_normal, e4_role])
    sec5.setdefault("1", []).extend([e5_normal, e5_role])

    # report
    return {
        "created": True,
        "new_template_name": new_name,
        "players_1_based": list(_players_to_human(players0)),
        "players_storage": ("missing_field4(all)" if want_all else "packed_field4"),
        "ids": {
            "root4_normal_id": int(new_root4_id),
            "root5_normal_id": int(new_root5_id),
            "role_id": int(new_role_id),
        },
        "base_template_name": str(base_template_name),
    }

