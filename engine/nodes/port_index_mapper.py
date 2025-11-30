# -*- coding: utf-8 -*-
"""
端口序号→端口名称映射工具（权威：engine/nodes）

依据节点定义库（engine/nodes/node_definition_loader.py）将侧别+序号映射为正式端口名：
- 左侧 → inputs 顺序
- 右侧 → outputs 顺序

说明：
- 识别侧的序号不包含 Settings/Warning 等装饰项；
- 若同名节点存在于多个类别，返回 None（避免误判）；
- 不做 try/except，出错直接抛出。
"""

from typing import Optional, Dict, List
import re
from pathlib import Path

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.nodes.port_name_rules import map_index_to_range_instance


_node_library_cache: Optional[Dict[str, NodeDef]] = None
_last_mapping_records: List[Dict[str, object]] = []


def _get_workspace_path() -> Path:
    current_file = Path(__file__).resolve()
    # 当前文件位于 Graph_Generater/engine/nodes/，上溯两级到 Graph_Generater/
    return current_file.parents[2]


def _ensure_node_library() -> Dict[str, NodeDef]:
    global _node_library_cache
    if _node_library_cache is None:
        workspace_path = _get_workspace_path()
        registry = get_node_registry(workspace_path, include_composite=True)
        _node_library_cache = registry.get_library()
    return _node_library_cache


def _find_unique_node_def_by_name(node_name_cn: str) -> Optional[NodeDef]:
    """按中文名精确查找唯一的节点定义；找不到则进行同字数最近似回退。"""
    library = _ensure_node_library()
    candidates = [nd for nd in library.values() if nd.name == node_name_cn]
    if len(candidates) == 1:
        return candidates[0]

    # —— 同字数最近似回退 ——
    target_len = len(node_name_cn or "")
    if target_len == 0:
        return None

    name_to_defs: Dict[str, List[NodeDef]] = {}
    for nd in library.values():
        nm = nd.name
        if len(nm) != target_len:
            continue
        name_to_defs.setdefault(nm, []).append(nd)
    if len(name_to_defs) == 0:
        return None

    def _hamming(a: str, b: str) -> int:
        if len(a) != len(b):
            return 10**9
        diff = 0
        for i in range(len(a)):
            if a[i] != b[i]:
                diff += 1
        return diff

    best_name: Optional[str] = None
    best_dist: Optional[int] = None
    tie = False
    for nm in name_to_defs.keys():
        d = _hamming(node_name_cn, nm)
        if best_dist is None or d < int(best_dist):
            best_dist = int(d)
            best_name = nm
            tie = False
        elif best_dist is not None and int(d) == int(best_dist):
            tie = True

    if best_name is None or tie:
        return None
    defs_for_best = name_to_defs.get(best_name, [])
    if len(defs_for_best) != 1:
        return None
    return defs_for_best[0]


def map_port_index_to_name(node_name_cn: str, side: str, index: int) -> Optional[str]:
    """
    将"侧别+序号"映射为节点定义中的端口名称。

    Args:
        node_name_cn: 节点中文名（需与节点定义库匹配）。
        side: 'left' | 'right'
        index: 端口序号（从0开始）。

    Returns:
        对应的端口名称；若无法唯一定位或越界则返回 None。
    """
    if node_name_cn is None or node_name_cn == "":
        return None
    if side not in ("left", "right"):
        return None
    if index is None or index < 0:
        return None

    node_def = _find_unique_node_def_by_name(node_name_cn)
    if node_def is None:
        return None

    if side == "left":
        port_list = list(node_def.inputs)
    else:
        port_list = list(node_def.outputs)

    # 优先处理"范围式端口名"（如 "0~99"、"键0~49"、"值0~49"）：
    # 若该侧仅存在一个范围定义，则将序号 index 映射为具体实例名
    if len(port_list) == 1:
        defined_name = str(port_list[0])
        inst = map_index_to_range_instance(defined_name, int(index))
        if inst is not None:
            mapped = inst
        else:
            # 非范围定义且序号在范围内，按顺序映射
            if index < len(port_list):
                mapped = port_list[index]
            else:
                return None
    else:
        # 多个定义项：常规序号在定义列表范围内，直接按顺序映射
        if index < len(port_list):
            mapped = port_list[index]
        else:
            return None

    # 记录映射决策（用于上层日志输出）
    used_fallback = (node_def.name != node_name_cn)
    ham = None
    if used_fallback and len(node_def.name) == len(node_name_cn or ""):
        # 计算差异
        ham = 0
        for i in range(len(node_def.name)):
            if node_def.name[i] != (node_name_cn or "")[i]:
                ham += 1
    _last_mapping_records.append({
        "input_node_name": str(node_name_cn or ""),
        "resolved_node_name": str(node_def.name),
        "used_fallback": bool(used_fallback),
        "hamming": None if ham is None else int(ham),
        "side": str(side),
        "index": int(index),
        "port_name": str(mapped),
    })
    return mapped


def get_and_clear_last_mappings() -> List[Dict[str, object]]:
    """返回并清空最近的端口映射记录（含最近似回退信息）。"""
    global _last_mapping_records
    logs = list(_last_mapping_records)
    _last_mapping_records = []
    return logs
