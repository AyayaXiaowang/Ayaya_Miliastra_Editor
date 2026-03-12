from __future__ import annotations

from typing import Mapping

from engine.type_registry import TYPE_FLOAT, TYPE_INTEGER

# 算术节点 title → Python 运算符
_ARITHMETIC_OPERATOR_BY_TITLE: Mapping[str, str] = {
    "加法运算": "+",
    "减法运算": "-",
    "乘法运算": "*",
    "除法运算": "/",
}

_NUMERIC_TYPES: set[str] = {TYPE_INTEGER, TYPE_FLOAT}

MAX_DATA_SOURCE_RESOLVE_DEPTH: int = 50
MAX_GRAPH_END_NODE_IDS_IN_ERROR: int = 5
MIN_BRANCHES_FOR_JOIN: int = 2
MIN_BRANCH_USAGE_FOR_LIFT: int = 2
INF_BFS_DISTANCE: int = 10**9

