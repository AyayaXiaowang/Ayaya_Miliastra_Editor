from __future__ import annotations

import zlib

from .asset_bundle_builder_constants import _COMPOSITE_NODE_TYPE_ID_PREFIX


def _map_composite_id_to_node_type_id_int(composite_id: str) -> int:
    """
    将 Graph_Generater 的 composite_id（字符串）映射为 NodeEditorPack/AssetBundle 口径的 node_id(int)。

    设计原则：
    - 稳定：同一 composite_id 在不同导出批次得到相同 node_id；
    - 隔离：复合节点 ID 固定落在 `0x60000000` 段，避免与内置节点 type_id 冲突；
    - 无副作用：不写回项目存档，不依赖外部 registry。
    """
    text = str(composite_id or "").strip()
    if text == "":
        raise ValueError("composite_id 不能为空（无法映射复合节点 node_id）")
    crc32 = zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF
    # 真源对齐：复合节点 node_id 必须落在 `0x6000xxxx`（高 16 位固定为 0x6000）。
    # 旧实现使用低 28 位会产生 `0x60A6xxxx` 这类高位变化的 ID，部分编辑器版本会导致
    # “复合节点实例端口可见但无法输入/参数 UI 不生成”的异常。
    low16 = int(crc32 & 0xFFFF)
    if low16 == 0:
        low16 = 1
    return int(_COMPOSITE_NODE_TYPE_ID_PREFIX | low16)


def _map_composite_id_to_composite_graph_id_int(composite_id: str) -> int:
    """
    将 composite_id 稳定映射为“复合图（CompositeGraph）”的 graph_id(int)。

    说明：
    - `.gia` 中复合节点通常由两部分组成：
      - NodeInterface（node_def，GraphUnitId.class=23，id=0x6000xxxx）
      - CompositeGraph（graph，GraphUnitId.class=5，id=0x6000xxxx，NodeGraph.identity.kind=21002）
    - 这里为 CompositeGraph 使用与 node_def 不同的 hash 种子，避免同 ID 撞车。
    """
    text = str(composite_id or "").strip()
    if text == "":
        raise ValueError("composite_id 不能为空（无法映射 composite graph id）")
    crc32 = zlib.crc32((text + "#graph").encode("utf-8")) & 0xFFFFFFFF
    low16 = int(crc32 & 0xFFFF)
    if low16 == 0:
        low16 = 1
    graph_id = int(_COMPOSITE_NODE_TYPE_ID_PREFIX | low16)
    node_def_id = int(_map_composite_id_to_node_type_id_int(text))
    if int(graph_id) == int(node_def_id):
        # 低概率撞车：再偏移一位（保持稳定、无副作用）
        bumped = int((low16 + 1) & 0xFFFF)
        if bumped == 0:
            bumped = 1
        graph_id = int(_COMPOSITE_NODE_TYPE_ID_PREFIX | bumped)
    return int(graph_id)


def _map_composite_virtual_pin_to_persistent_uid(*, composite_id: str, pin_name: str, kind_int: int) -> int:
    """
    为复合节点的 PinInterface / PinInstance 生成稳定的 persistent_pin_uid（PinInterface.field_8 / PinInstance.field_7）。
    """
    base = f"{str(composite_id).strip()}::{int(kind_int)}::{str(pin_name).strip()}"
    crc32 = zlib.crc32(base.encode("utf-8")) & 0xFFFFFFFF
    v = int(crc32 & 0x7FFFFFFF)
    return int(v if v != 0 else 1)

