"""存档脏块模型（从 PackageController 中抽离）。

设计目标：
- 为“按脏块增量落盘”提供稳定的数据结构；
- 避免 PackageController 与保存 service 之间形成循环依赖；
- 保持字段语义与旧实现一致（不在此处引入额外状态机）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PackageDirtyState:
    """记录当前存档待落盘的脏块信息。"""

    graph_dirty: bool = False
    template_ids: set[str] = field(default_factory=set)
    instance_ids: set[str] = field(default_factory=set)
    level_entity_dirty: bool = False
    combat_dirty: bool = False
    management_keys: set[str] = field(default_factory=set)
    signals_dirty: bool = False
    index_dirty: bool = False
    full_management_sync: bool = False

    def is_empty(self) -> bool:
        return not (
            self.graph_dirty
            or self.template_ids
            or self.instance_ids
            or self.level_entity_dirty
            or self.combat_dirty
            or self.management_keys
            or self.signals_dirty
            or self.index_dirty
            or self.full_management_sync
        )

    def should_flush_property_panel(self) -> bool:
        return bool(
            self.graph_dirty
            or self.template_ids
            or self.instance_ids
            or self.level_entity_dirty
        )

    def snapshot(self) -> "PackageDirtyState":
        """生成当前脏状态的浅拷贝，便于保存时使用。"""
        return PackageDirtyState(
            graph_dirty=self.graph_dirty,
            template_ids=set(self.template_ids),
            instance_ids=set(self.instance_ids),
            level_entity_dirty=self.level_entity_dirty,
            combat_dirty=self.combat_dirty,
            management_keys=set(self.management_keys),
            signals_dirty=self.signals_dirty,
            index_dirty=self.index_dirty,
            full_management_sync=self.full_management_sync,
        )

    def clear(self) -> None:
        self.graph_dirty = False
        self.template_ids.clear()
        self.instance_ids.clear()
        self.level_entity_dirty = False
        self.combat_dirty = False
        self.management_keys.clear()
        self.signals_dirty = False
        self.index_dirty = False
        self.full_management_sync = False


