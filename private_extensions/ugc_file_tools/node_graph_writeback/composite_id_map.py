from __future__ import annotations

import zlib

_COMPOSITE_ID_PREFIX: int = 0x40000000
_COMPOSITE_ID_LOW_MASK: int = 0x7FFF


def map_composite_id_to_node_type_id_int(composite_id: str) -> int:
    """
    将 composite_id 稳定映射为复合节点实例的 node_type_id_int（0x4000xxxx）。

    约束（GIL 口径）：
    - 高 16 位固定为 0x4000（避免高位漂移导致编辑器把复合节点误判为“信号节点”等特殊节点）
    - 低 16 位必须落在 `0x0001..0x7FFF`：
      部分链路会将 low16 作为 int16 解释，若 low16>=0x8000 会被视为负数，
      导致 NodeInterface/CompositeGraph 查表失败并出现“节点退化/渲染错类型”等现象。
    """
    text = str(composite_id or "").strip()
    if text == "":
        raise ValueError("composite_id 不能为空（无法映射复合节点 type_id）")
    crc32 = zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF
    low15 = int(crc32 & _COMPOSITE_ID_LOW_MASK)
    if low15 == 0:
        low15 = 1
    return int(_COMPOSITE_ID_PREFIX | low15)


def map_composite_id_to_composite_graph_id_int(composite_id: str) -> int:
    """
    将 composite_id 稳定映射为复合子图（CompositeGraph）的 graph_id/runtime_id（0x4000xxxx）。

    说明：
    - 使用不同 hash 种子避免与 node_type_id 撞车；
    - 若仍低概率撞车，则低 16 位 +1（保持稳定、无副作用）。
    """
    text = str(composite_id or "").strip()
    if text == "":
        raise ValueError("composite_id 不能为空（无法映射复合子图 graph_id）")
    crc32 = zlib.crc32((text + "#graph").encode("utf-8")) & 0xFFFFFFFF
    low15 = int(crc32 & _COMPOSITE_ID_LOW_MASK)
    if low15 == 0:
        low15 = 1
    graph_id = int(_COMPOSITE_ID_PREFIX | low15)
    node_id = int(map_composite_id_to_node_type_id_int(text))
    if int(graph_id) == int(node_id):
        bumped = int((low15 + 1) & _COMPOSITE_ID_LOW_MASK)
        if bumped == 0:
            bumped = 1
        graph_id = int(_COMPOSITE_ID_PREFIX | bumped)
    return int(graph_id)


__all__ = [
    "map_composite_id_to_node_type_id_int",
    "map_composite_id_to_composite_graph_id_int",
]

