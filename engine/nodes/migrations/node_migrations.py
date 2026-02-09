from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal


@dataclass(frozen=True)
class NodeCallRename:
    """Graph Code：节点函数调用名改写规则（例如 旧节点(...) -> 新节点(...)）。

    注意：
    - 这里的“调用名”指 Graph Code 中 `ast.Name` 的函数名（必须是合法 Python 标识符）；
    - 不包含类别前缀（Graph Code 无法写 `执行节点/xxx(...)`）。
    """

    from_call_name: str
    to_call_name: str
    reason: str = ""


@dataclass(frozen=True)
class PortRename:
    """Graph Code：节点关键字参数名（端口名）改写规则（例如 旧端口=... -> 新端口=...）。"""

    node_call_name: str
    direction: Literal["input", "output"] = "input"
    from_port_name: str = ""
    to_port_name: str = ""
    reason: str = ""


@dataclass(frozen=True)
class EnumValueRename:
    """Graph Code：枚举端口的候选值迁移（例如 旧值 -> 新值）。

    约定：
    - 仅对 Graph Code 中“关键字参数值为字面量”的场景可自动改写；
    - 该规则用于表达“删枚举候选但提供可迁移映射”的兼容策略，配合 diff 与迁移工具使用。
    """

    node_call_name: str
    direction: Literal["input", "output"] = "input"
    port_name: str = ""
    from_value: str = ""
    to_value: str = ""
    reason: str = ""


@dataclass(frozen=True)
class MigrationPlan:
    """迁移计划：集中描述一组可执行的改写规则。"""

    node_call_renames: List[NodeCallRename] = field(default_factory=list)
    port_renames: List[PortRename] = field(default_factory=list)
    enum_value_renames: List[EnumValueRename] = field(default_factory=list)

    # 预留：枚举值迁移、复合节点方法名迁移等
    extra: Dict[str, object] = field(default_factory=dict)


def get_default_migration_plan() -> MigrationPlan:
    """
    返回仓库内置的迁移计划。

    约定：
    - 默认计划保持为空（由 manifest diff 自动推导“节点改名”即可覆盖大多数情况）；
    - 当出现“端口改名/枚举值替换”等无法从 diff 自动可靠推断的 breaking 变更时，
      应在此显式登记规则，并配套工具与测试覆盖。
    """
    return MigrationPlan()


__all__ = [
    "MigrationPlan",
    "EnumValueRename",
    "NodeCallRename",
    "PortRename",
    "get_default_migration_plan",
]


