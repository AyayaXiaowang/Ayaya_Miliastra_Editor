from __future__ import annotations

from typing import Dict


_COMPOSITE_NODE_TYPE_ID_PREFIX = 0x60000000
_GIA_NODE_POS_SCALE: float = 2.0


# ---------------------------------------------------------------------------
# Constants (copied from NodeEditorPack `utils/node_data/data.json` SystemConstants)
# ---------------------------------------------------------------------------

_GRAPH_CATEGORY_CONSTS: Dict[str, Dict[str, int]] = {
    "ENTITY_NODE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 5,
        "AssetsKind": 0,
        "AssetsWhich": 9,
        "GraphOrigin": 10000,
        "GraphCategory": 20000,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
    "STATUS_NODE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 5,
        "AssetsKind": 0,
        "AssetsWhich": 22,
        "GraphOrigin": 10000,
        "GraphCategory": 20003,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
    "CLASS_NODE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 5,
        "AssetsKind": 0,
        "AssetsWhich": 23,
        "GraphOrigin": 10000,
        "GraphCategory": 20004,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
    "ITEM_NODE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 5,
        "AssetsKind": 0,
        "AssetsWhich": 46,
        "GraphOrigin": 10000,
        "GraphCategory": 20005,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
    "BOOLEAN_FILTER_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 1,
        "AssetsKind": 3,
        "AssetsWhich": 10,
        "GraphOrigin": 10000,
        "GraphCategory": 20001,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20001,
        "NodeKind": 22000,
    },
    "INTEGER_FILTER_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 1,
        "AssetsKind": 3,
        "AssetsWhich": 47,
        "GraphOrigin": 10000,
        "GraphCategory": 20006,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20001,
        "NodeKind": 22000,
    },
    "SKILL_NODE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 1,
        "AssetsKind": 3,
        "AssetsWhich": 11,
        "GraphOrigin": 10000,
        "GraphCategory": 20002,
        "GraphKind": 21001,
        "NodeOrigin": 10001,
        "NodeCategory": 20002,
        "NodeKind": 22000,
    },
    "COMPOSITE_NODE_DECL": {
        "AssetsOrigin": 0,
        "AssetsCategory": 23,
        "AssetsKind": 0,
        "AssetsWhich": 12,
        "GraphOrigin": 10000,
        "GraphCategory": 20000,
        "GraphKind": 21002,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
    # 复合图（CompositeGraph）本体：真源样本中其 GraphUnit.which 多数沿用实体节点图(9)，但 NodeGraph.identity.kind=21002。
    "COMPOSITE_GRAPH": {
        "AssetsOrigin": 0,
        "AssetsCategory": 5,
        "AssetsKind": 0,
        "AssetsWhich": 9,
        "GraphOrigin": 10000,
        "GraphCategory": 20000,
        "GraphKind": 21002,
        "NodeOrigin": 10001,
        "NodeCategory": 20000,
        "NodeKind": 22000,
    },
}


_LIST_LIKE_VAR_TYPES: set[int] = {7, 8, 9, 10, 11, 13, 15, 22, 23, 24, 26}

