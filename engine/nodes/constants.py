from __future__ import annotations

from typing import Literal, Tuple

# 统一的节点类别/作用域常量（单一来源）
NODE_CATEGORY_VALUES: Tuple[str, ...] = (
    "事件节点",
    "执行节点",
    "查询节点",
    "运算节点",
    "复合节点",
    "流程控制节点",
    "其他节点",
)

ALLOWED_SCOPES: Tuple[str, ...] = ("server", "client")

# 类型别名（用于注解）
NodeCategory = Literal[
    "事件节点",
    "执行节点",
    "查询节点",
    "运算节点",
    "复合节点",
    "流程控制节点",
    "其他节点",
]

