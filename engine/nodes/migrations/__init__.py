"""
节点库迁移（breaking 变更的显式兼容/自动迁移支撑）。

说明：
- 本包只存放“纯数据 + 纯函数”的迁移规则模型，不做 I/O；
- Graph Code 自动迁移工具属于内部工具链：通过读取 manifest/diff 与这里的规则做自动改写；
- 迁移规则的长期目标：把“节点改名/端口改名/枚举值改名”等 breaking 变更变成可控升级。
"""

from .node_migrations import (
    EnumValueRename,
    MigrationPlan,
    NodeCallRename,
    PortRename,
    get_default_migration_plan,
)

__all__ = [
    "EnumValueRename",
    "MigrationPlan",
    "NodeCallRename",
    "PortRename",
    "get_default_migration_plan",
]


