"""节点挂载规则（校验层兼容入口）

权威规则定义位于配置层：`engine.configs.rules.node_mount_rules`。
本模块仅用于兼容旧导入路径，避免在 validate 层重复维护同一份规则数据。
"""

from engine.configs.rules.node_mount_rules import (
    NODE_ENTITY_RESTRICTIONS,
    NODE_TYPES,
    can_node_mount_on_entity,
)

__all__ = [
    "NODE_ENTITY_RESTRICTIONS",
    "NODE_TYPES",
    "can_node_mount_on_entity",
]


