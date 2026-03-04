from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_node_data_index_doc() -> Dict[str, Any]:
    """加载 ugc_file_tools/node_data/index.json（第三方快照）。"""
    index_path = Path(__file__).resolve().parents[1] / "node_data" / "index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"node_data/index.json not found: {str(index_path)!r}")
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("node_data/index.json is not a dict document")
    return doc


def _build_entry_by_id_map(entries: Any) -> Dict[int, Dict[str, Any]]:
    if not isinstance(entries, list):
        return {}
    result: Dict[int, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("ID")
        if not isinstance(entry_id, int):
            continue
        result[int(entry_id)] = dict(entry)
    return result


def _extract_enum_id_from_type_expr(type_expr: str) -> Optional[int]:
    text = str(type_expr or "").strip()
    m = re.match(r"^E<(-?\d+)>$", text)
    if not m:
        return None
    return int(m.group(1))


# 当 node_data 快照缺少某些节点的枚举输入（Inputs 未标注 E<...>）时，
# 需要基于 Graph_Generater 的 NodeDef 端口名/候选项做“最小可维护”的 enum_id 推断，
# 才能把中文选项写回为 EnumList item 的数值 ID（否则写回 0 会被编辑器导出时清空）。
_KNOWN_ENUM_ID_BY_PORT_NAME: Dict[str, int] = {
    # 运动/坐标系
    "跟随坐标系": 12,  # Coordinate_System_Type
    "跟随类型": 11,  # Follow_Location_Type
    # 技能槽位
    "角色技能槽位": 30,  # Skill_Slot
    "技能槽位": 30,  # Skill_Slot
    # UI
    "显示状态": 24,  # UI_Control_Group_Status
    # 排序
    "排序方式": 6,  # Sorting_Rules
    "筛选规则": 29,  # Target_Sorting_Rules（默认/随机/从近到远）
    # 结算
    "结算状态": 33,  # Settlement_Status
    # 背包掉落
    "掉落类型": 36,  # Item_Loot_Type
    # 实体类型
    "实体类型": 14,  # Entity_Type
    # 取整
    "取整方式": 7,  # Rounding_Logic
    # 攻击盒/受击
    "受击等级": 28,  # Hit_Performance_Level
    "受击击退朝向": 31,  # Knockback_Direction_Type
}


# node_data 未覆盖/缺失时的“直写 enum item id”兜底（来自人工样本存档）。
# key: (node_name, port_name, option_text) -> enum_item_id
#
# 说明：
# - 这类枚举的 item_id 不在 node_data/index.json 的 EnumList 中（第三方快照不全），只能靠样本对齐。
# - 仅维护极少数高频/关键节点；其余仍走 node_data(E<enum_id>) 或 enum_id 推断路径。
_KNOWN_ENUM_ITEM_ID_BY_NODE_AND_PORT_AND_OPTION: Dict[Tuple[str, str, str], int] = {
    # 设置扫描标签的规则 / 规则类型（样本：新建补错.gil）
    ("设置扫描标签的规则", "规则类型", "视野优先"): 5100,
    ("设置扫描标签的规则", "规则类型", "距离优先"): 5101,
    # 损失生命 / 伤害跳字类型（样本：新建补错.gil；仅观测到 5401/5402，按候选项顺序推断第三项为 5403）
    ("损失生命", "伤害跳字类型", "无跳字"): 5401,
    ("损失生命", "伤害跳字类型", "普通跳字"): 5402,
    ("损失生命", "伤害跳字类型", "暴击跳字"): 5403,
}


_KNOWN_ENUM_TYPE_IDS_CACHE: Optional[set[int]] = None


def get_known_enum_type_ids() -> set[int]:
    """返回“已知枚举类型 ID 集合”（用于判定 VarType 是否应按 EnumBaseValue 编码）。

    说明：
    - 主要来源是 `node_data/index.json` 的 EnumList（第三方快照）；
    - 同时纳入少量按端口名维护的 enum_id 映射（用于 node_data 缺失时的最小兜底）。
    """
    global _KNOWN_ENUM_TYPE_IDS_CACHE
    cached = _KNOWN_ENUM_TYPE_IDS_CACHE
    if cached is not None:
        return set(cached)

    doc = _load_node_data_index_doc()
    entries = doc.get("Enums")
    ids: set[int] = set()
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("ID")
            if isinstance(entry_id, int):
                ids.add(int(entry_id))

    ids.update(int(v) for v in _KNOWN_ENUM_ID_BY_PORT_NAME.values())

    _KNOWN_ENUM_TYPE_IDS_CACHE = set(ids)
    return set(ids)


def _infer_enum_id_from_node_def_port(
    *,
    port_name: str,
    options_text: List[str],
    enum_entry_by_id: Dict[int, Dict[str, Any]],
) -> Optional[int]:
    """在 node_data 无法提供 enum_id 的情况下，尝试推断 enum_id。

    规则：
    - 先按端口名做显式映射（维护成本最低、确定性最高）
    - 再按候选项文本做少量“强特征”推断（用于端口名变化/复用场景）
    - 若推断结果不在 enum_entry_by_id 中，则视为无效
    """
    port_key = str(port_name or "").strip()
    if port_key in _KNOWN_ENUM_ID_BY_PORT_NAME:
        enum_id = int(_KNOWN_ENUM_ID_BY_PORT_NAME[port_key])
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    opts = [str(x).strip() for x in options_text if str(x).strip()]
    if not opts:
        return None

    # 候选项强特征：前缀/包含关键子串
    if any(o.startswith("实体类型_") for o in opts):
        enum_id = 14
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    if any(o.startswith("取整逻辑_") for o in opts):
        enum_id = 7
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    if any(o.startswith("排序规则_") for o in opts):
        enum_id = 6
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    if any(o.startswith("界面控件组状态_") for o in opts):
        enum_id = 24
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    # 技能槽位（候选项包含“普通攻击/技能1-E/自定义技能槽位X”）
    if ("普通攻击" in opts) and any(("技能1" in o or "自定义技能槽位" in o) for o in opts):
        enum_id = 30
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    # 跟随坐标系（相对/世界）
    if ("相对坐标系" in opts) and ("世界坐标系" in opts):
        enum_id = 12
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    # 跟随类型（完全/位置/旋转）
    if ("完全跟随" in opts) and ("跟随位置" in opts) and ("跟随旋转" in opts):
        enum_id = 11
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    # 背包掉落类型（全员/每人）
    if ("全员一份" in opts) and ("每人一份" in opts):
        enum_id = 36
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    # 结算状态（未定/胜利/失败）
    if ("未定" in opts) and any(("胜利" in o or "失败" in o) for o in opts):
        enum_id = 33
        return enum_id if isinstance(enum_entry_by_id.get(enum_id), dict) else None

    return None


def _resolve_enum_item_id_for_input_constant(
    *,
    node_type_id_int: int,
    slot_index: int,
    port_name: str,
    raw_value: Any,
    node_def: Any,
    node_entry_by_id: Dict[int, Dict[str, Any]],
    enum_entry_by_id: Dict[int, Dict[str, Any]],
) -> Optional[int]:
    """将枚举端口的中文字符串常量映射为枚举 item 的数值 ID（用于 VarType=14 的 bEnum.val）。"""
    # 1) 已是数字：直接使用
    if isinstance(raw_value, int):
        return int(raw_value)
    value_text = str(raw_value).strip()
    if value_text.isdigit():
        return int(value_text)

    # 2) 通过 NodeDef 的 input_enum_options 确定“选项顺序”
    enum_options_map = getattr(node_def, "input_enum_options", None)
    if not isinstance(enum_options_map, dict):
        # 典型场景：泛型枚举节点（例如“枚举是否相等”）的端口候选项依赖“已选择的枚举类型”，
        # GraphModel JSON 若也未给出具体枚举类型，则无法稳定写回具体 item_id；保持为空并由上层记录 skipped。
        return None
    options = enum_options_map.get(str(port_name))
    if not isinstance(options, list) or not options:
        return None
    options_text = [str(x) for x in options]
    if str(value_text) not in options_text:
        return None
    option_index = int(options_text.index(str(value_text)))

    # 3) 兜底：若该枚举不在 node_data(EnumList) 快照中，优先用“人工样本”直写 item_id
    node_name = str(getattr(node_def, "name", "") or "").strip()
    direct_key = (node_name, str(port_name).strip(), str(value_text).strip())
    direct_item_id = _KNOWN_ENUM_ITEM_ID_BY_NODE_AND_PORT_AND_OPTION.get(direct_key)
    if isinstance(direct_item_id, int):
        return int(direct_item_id)

    # 4) 优先尝试使用 node_data/index.json 的 Inputs 类型表达式确定 enum_id，并映射到 enum item 的数值 ID。
    #    若 node_data 缺失/不匹配（常见：某些节点的 enum 输入在 node_data 中未标注为 E<...>），则尝试基于 NodeDef 推断 enum_id；
    #    仍无法推断时，返回 None（保持 bEnum.val 为空，避免写回 0 被编辑器导出时清空）。
    node_entry = node_entry_by_id.get(int(node_type_id_int))
    enum_id: Optional[int] = None
    if isinstance(node_entry, dict):
        inputs = node_entry.get("Inputs")
        if isinstance(inputs, list) and 0 <= int(slot_index) < len(inputs):
            enum_id = _extract_enum_id_from_type_expr(str(inputs[int(slot_index)]))

    if not isinstance(enum_id, int):
        enum_id = _infer_enum_id_from_node_def_port(
            port_name=str(port_name),
            options_text=list(options_text),
            enum_entry_by_id=enum_entry_by_id,
        )

    if not isinstance(enum_id, int):
        return None

    enum_entry = enum_entry_by_id.get(int(enum_id))
    if not isinstance(enum_entry, dict):
        return None
    items = enum_entry.get("Items")
    if not isinstance(items, list) or not items:
        return None
    if option_index < 0 or option_index >= len(items):
        return None
    item = items[option_index]
    if not isinstance(item, dict) or not isinstance(item.get("ID"), int):
        return None
    return int(item["ID"])


# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.
# Keep underscored implementations for internal structure, but expose stable
# public symbols for other subdomains (e.g. gia_export).


def load_node_data_index_doc() -> Dict[str, Any]:
    return _load_node_data_index_doc()


def build_entry_by_id_map(entries: Any) -> Dict[int, Dict[str, Any]]:
    return _build_entry_by_id_map(entries)


def resolve_enum_item_id_for_input_constant(
    *,
    node_type_id_int: int,
    slot_index: int,
    port_name: str,
    raw_value: Any,
    node_def: Any,
    node_entry_by_id: Dict[int, Dict[str, Any]],
    enum_entry_by_id: Dict[int, Dict[str, Any]],
) -> Optional[int]:
    return _resolve_enum_item_id_for_input_constant(
        node_type_id_int=node_type_id_int,
        slot_index=slot_index,
        port_name=port_name,
        raw_value=raw_value,
        node_def=node_def,
        node_entry_by_id=node_entry_by_id,
        enum_entry_by_id=enum_entry_by_id,
    )

