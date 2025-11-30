"""包级视图/索引的协议类型。

用于在类型层描述“包状对象”的最小接口约束，避免再次依赖早期的
`PackageModel` 聚合结构，同时让验证器、Todo 系统等可以在
`PackageView` / `GlobalResourceView` / `UnclassifiedResourceView`
等视图之间复用相同的签名。
"""

from __future__ import annotations

from typing import Dict, Optional, Protocol

from engine.graph.models.package_model import (
    TemplateConfig,
    InstanceConfig,
    CombatPresets,
    ManagementData,
    SignalConfig,
)


class PackageLike(Protocol):
    """包级视图/索引统一接口（结构化约束，而非具体实现）。

    约定：
    - 提供基础元数据与 Todo 状态字段（package_id/name/description/todo_states 等）；
    - 以字典形式暴露模板与实例集合（templates/instances）；
    - 以聚合对象暴露战斗预设与管理配置（combat_presets/management）；
    - 以 {signal_id: SignalConfig} 字典暴露信号定义（signals）；
    - 暴露关卡实体 level_entity（可能为实例或模板，具体由实现决定）；
    - 通过 get_template/get_instance 提供按 ID 检索入口。

    实现示例：
    - engine.resources.PackageView
    - engine.resources.GlobalResourceView
    - engine.resources.UnclassifiedResourceView
    """

    package_id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    todo_states: Dict[str, bool]

    templates: Dict[str, TemplateConfig]
    instances: Dict[str, InstanceConfig]
    combat_presets: CombatPresets
    management: ManagementData
    signals: Dict[str, SignalConfig]

    # 关卡实体：具体类型由实现决定，可以是模板也可以是实例
    level_entity: object | None

    def get_template(self, template_id: str) -> Optional[TemplateConfig]:
        ...

    def get_instance(self, instance_id: str) -> Optional[InstanceConfig]:
        ...


