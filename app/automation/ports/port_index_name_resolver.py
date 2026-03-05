# -*- coding: utf-8 -*-
from __future__ import annotations

"""
port_index_name_resolver: 将“识别到的端口侧别+序号”映射为端口名称的公共工具。

背景：
- 视觉端口识别会产出 (side, index)；
- 旧逻辑常通过 `engine.nodes.port_index_mapper.map_port_index_to_name(node_title, side, index)`
  去节点定义库中按“节点中文名”反查端口名；
- 当 client/server 存在**同名节点**时，该反查会因为“无法唯一定位 NodeDef”而返回 None，
  导致上层只能拿到 index，却拿不到稳定端口名，进而出现
  “测试端口识别有结果，但执行步骤认为端口不存在”的假失败。

本模块提供：在调用方已持有 `node_def`（唯一）时，直接按 node_def.inputs/outputs 顺序映射端口名，
避免依赖“节点中文名唯一”这一前提。
"""

from typing import Any, Optional

from engine.nodes.port_name_rules import map_index_to_range_instance


def map_port_index_to_name_via_node_def(
    node_def: Any,
    side: str,
    index: int,
) -> Optional[str]:
    """基于已解析的 node_def，将 (side, index) 映射为端口名。

    Args:
        node_def: `engine.nodes.node_definition_loader.NodeDef` 或兼容对象（需具备 inputs/outputs）。
        side: 'left' | 'right'
        index: 0-based 序号

    Returns:
        端口名称；无法映射则返回 None。
    """
    if node_def is None:
        return None
    if side not in ("left", "right"):
        return None
    if not isinstance(index, int) or index < 0:
        return None

    port_list = list(getattr(node_def, "inputs", []) or []) if side == "left" else list(getattr(node_def, "outputs", []) or [])
    if len(port_list) == 0:
        return None

    # 范围式端口名（如 "0~99"、"键0~49"）兼容：仅当该侧只有一个定义项时尝试展开
    if len(port_list) == 1:
        defined_name = str(port_list[0] or "")
        if defined_name:
            instance_name = map_index_to_range_instance(defined_name, int(index))
            if isinstance(instance_name, str) and instance_name:
                return instance_name

    if index >= len(port_list):
        return None

    mapped = port_list[index]
    if isinstance(mapped, str) and mapped:
        return mapped
    mapped_text = str(mapped or "")
    return mapped_text if mapped_text else None


__all__ = [
    "map_port_index_to_name_via_node_def",
]


