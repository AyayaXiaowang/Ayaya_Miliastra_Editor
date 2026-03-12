from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..gil_codec import decode_packed_varints

# -------------------- Constants --------------------

PLAYER_COUNT = 8
PLAYER_INDEX_MIN_0_BASED = 0
PLAYER_INDEX_MAX_0_BASED = PLAYER_COUNT - 1
PLAYER_INDEX_MIN_1_BASED = 1
PLAYER_INDEX_MAX_1_BASED = PLAYER_COUNT
ALL_PLAYERS_0_BASED: Tuple[int, ...] = tuple(range(PLAYER_COUNT))

ROLE_EDIT_SUFFIX = "(角色编辑)"

# decoded message keys (string field numbers)
ROOT4_SECTION_KEY = "4"
ROOT5_SECTION_KEY = "5"
SECTION_ENTRIES_KEY = "1"

ROOT_ENTRY_ID_KEY = "1"
ROOT5_REF_BOX_KEY = "2"
ROOT5_META_LIST_KEY = "5"
ROOT4_META_LIST_KEY = "6"
ROOT5_VARIABLE_GROUP_LIST_KEY = "7"
ROOT4_VARIABLE_GROUP_LIST_KEY = "8"

META_ITEM_ID_KEY = "1"
META_NAME_BOX_KEY = "11"
META_NAME_TEXT_KEY = "1"
META_PLAYERS_BOX_KEY = "12"
META_PLAYERS_BYTES_KEY = "4"
META_PLAYERS_BOX_FIELD5_KEY = "5"
META_PLAYERS_BOX_FIELD6_KEY = "6"

META_ITEM_ID_NAME = 1
META_ITEM_ID_PLAYERS = 3

GROUP_ITEM_ID_KEY = "1"
GROUP_ITEM_INDEX_KEY = "2"
GROUP_ITEM_BOX_KEY = "11"
GROUP_ITEM_VAR_LIST_KEY = "1"
GROUP1_ID = 1
GROUP1_INDEX = 1

VARIABLES_PREVIEW_LIMIT = 50
FIND_BYTES_DEFAULT_LIMIT = 50
FIND_TEXT_DEFAULT_LIMIT = 100


# -------------------- Common models --------------------


@dataclass(frozen=True)
class PlayerTemplateRef:
    """玩家模板抽象（从 `.gil` payload 中提取出的可解释视图）。"""

    name: str
    # 0-based players: 0..7
    players: Tuple[int, ...]
    # 指向 payload 内的“模板 message dict”（数值键）
    msg: Dict[str, Any]


# -------------------- Tree helpers (decoded dict) --------------------


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


# -------------------- Players helpers --------------------


def _normalize_player_index_list(values: List[int]) -> Tuple[int, ...]:
    cleaned: List[int] = []
    for v in values:
        if not isinstance(v, int):
            continue
        vi = int(v)
        if PLAYER_INDEX_MIN_0_BASED <= vi <= PLAYER_INDEX_MAX_0_BASED:
            cleaned.append(vi)
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
        pi = int(p)
        if not (PLAYER_INDEX_MIN_1_BASED <= pi <= PLAYER_INDEX_MAX_1_BASED):
            raise ValueError(f"player must be in {PLAYER_INDEX_MIN_1_BASED}..{PLAYER_INDEX_MAX_1_BASED}: {p!r}")
        out.append(pi - 1)
    return tuple(sorted(set(out)))


def _enforce_no_overlap_or_raise(templates: List[PlayerTemplateRef]) -> None:
    used: Dict[int, str] = {}
    for t in templates:
        for p in t.players:
            if p in used:
                raise ValueError(f"玩家模板生效玩家发生重叠：player={p+1} 被 {used[p]!r} 与 {t.name!r} 同时占用")
            used[p] = t.name

