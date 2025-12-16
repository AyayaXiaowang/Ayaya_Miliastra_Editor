"""集中管理管理面板的页面与资源配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from engine.configs.resource_types import ResourceType


@dataclass(frozen=True)
class ManagementResourceBinding:
    """描述某个管理配置条目在索引中的 key 与对应的资源类型。

    aggregation_mode:
        - "id_list"                : 按资源 ID 逐条列出（默认行为）。
        - "signal_entries"         : 针对信号配置，将聚合 JSON 中的每个信号作为一条记录展开。
        - "single_config_non_empty": 单配置类字段（如关卡设置、货币与背包、局内存档），
                                     仅在配置体非空时计数，并在聚合视图中按“已配置配置体数”汇总。
        - "peripheral_items"       : 外围系统配置，按成就/排行榜/段位条目的总数计数。
    """

    key: str
    resource_type: ResourceType
    aggregation_mode: str = "id_list"


@dataclass(frozen=True)
class ManagementSectionSpec:
    """描述管理面板左侧导航与资源绑定信息。

    当前仅声明每个管理类型在 UI 中的标题、分组与资源绑定等元数据，
    具体 Widget 与编辑逻辑由 `ManagementLibraryWidget` 与主窗口右侧面板负责装配。
    """

    key: str
    title: str
    requires_package: bool = True
    connect_data_updated: bool = True
    data_domain: Optional[str] = None
    eager_load: bool = False
    resources: Tuple[ManagementResourceBinding, ...] = ()
    group: str = "general"
    group_title: Optional[str] = None

MANAGEMENT_SECTIONS: Tuple[ManagementSectionSpec, ...] = (
    ManagementSectionSpec(
        key="signals",
        title="📡 信号管理",
        group="core_systems",
        group_title="系统服务",
        resources=(
            ManagementResourceBinding(
                "signals",
                ResourceType.SIGNAL,
                aggregation_mode="signal_entries",
            ),
        ),
    ),
    ManagementSectionSpec(
        key="struct_definitions",
        title="🧬 基础结构体定义",
        group="core_systems",
        resources=(ManagementResourceBinding("struct_definitions", ResourceType.STRUCT_DEFINITION),),
    ),
    ManagementSectionSpec(
        key="ingame_struct_definitions",
        title="💾 局内存档结构体定义",
        group="core_systems",
        resources=(ManagementResourceBinding("struct_definitions", ResourceType.STRUCT_DEFINITION),),
    ),
    ManagementSectionSpec(
        key="save_points",
        title="💾 局内存档管理",
        group="level",
        resources=(
            ManagementResourceBinding(
                "save_points",
                ResourceType.SAVE_POINT,
                aggregation_mode="single_config_non_empty",
            ),
        ),
    ),
    ManagementSectionSpec(
        key="ui_control_groups",
        title="🖼️ 界面控件组",
        connect_data_updated=False,
        eager_load=True,
        group="ui",
        group_title="界面与模板",
        resources=(
            ManagementResourceBinding("ui_layouts", ResourceType.UI_LAYOUT),
            ManagementResourceBinding("ui_widget_templates", ResourceType.UI_WIDGET_TEMPLATE),
        ),
    ),
    ManagementSectionSpec(
        key="level_settings",
        title="⚙️ 关卡设置",
        group="level",
        group_title="关卡配置",
        resources=(
            ManagementResourceBinding(
                "level_settings",
                ResourceType.LEVEL_SETTINGS,
                aggregation_mode="single_config_non_empty",
            ),
        ),
    ),
    ManagementSectionSpec(
        key="main_cameras",
        title="📷 主镜头管理",
        group="level",
        resources=(ManagementResourceBinding("main_cameras", ResourceType.MAIN_CAMERA),),
    ),
    ManagementSectionSpec(
        key="peripheral_systems",
        title="🔧 外围系统管理",
        group="core_systems",
        resources=(
            ManagementResourceBinding(
                "peripheral_systems",
                ResourceType.PERIPHERAL_SYSTEM,
                aggregation_mode="peripheral_items",
            ),
        ),
    ),
    ManagementSectionSpec(
        key="currency_backpack",
        title="💰 货币与背包",
        group="resources",
        group_title="资源资产",
        resources=(
            ManagementResourceBinding(
                "currency_backpack",
                ResourceType.CURRENCY_BACKPACK,
                aggregation_mode="single_config_non_empty",
            ),
        ),
    ),
    ManagementSectionSpec(
        key="timer",
        title="⏰ 计时器管理",
        group="core_systems",
        resources=(ManagementResourceBinding("timers", ResourceType.TIMER),),
    ),
    ManagementSectionSpec(
        key="variable",
        title="📊 关卡变量管理",
        group="level",
        resources=(ManagementResourceBinding("level_variables", ResourceType.LEVEL_VARIABLE),),
    ),
    ManagementSectionSpec(
        key="preset_point",
        title="📍 预设点管理",
        group="level",
        resources=(ManagementResourceBinding("preset_points", ResourceType.PRESET_POINT),),
    ),
    ManagementSectionSpec(
        key="skill_resource",
        title="✨ 技能资源管理",
        group="resources",
        resources=(ManagementResourceBinding("skill_resources", ResourceType.SKILL_RESOURCE),),
    ),
    ManagementSectionSpec(
        key="background_music",
        title="🎵 背景音乐管理",
        group="resources",
        resources=(ManagementResourceBinding("background_music", ResourceType.BACKGROUND_MUSIC),),
    ),
    ManagementSectionSpec(
        key="equipment_entries",
        title="⚔️ 装备数据管理-词条",
        group="resources",
        resources=(ManagementResourceBinding("equipment_data", ResourceType.EQUIPMENT_DATA),),
    ),
    ManagementSectionSpec(
        key="equipment_tags",
        title="⚔️ 装备数据管理-标签",
        group="resources",
        resources=(ManagementResourceBinding("equipment_data", ResourceType.EQUIPMENT_DATA),),
    ),
    ManagementSectionSpec(
        key="equipment_types",
        title="⚔️ 装备数据管理-类型",
        group="resources",
        resources=(ManagementResourceBinding("equipment_data", ResourceType.EQUIPMENT_DATA),),
    ),
    ManagementSectionSpec(
        key="shop_templates",
        title="🏪 商店模板管理",
        group="resources",
        resources=(ManagementResourceBinding("shop_templates", ResourceType.SHOP_TEMPLATE),),
    ),
    ManagementSectionSpec(
        key="entity_deployment_groups",
        title="📦 实体布设组管理",
        group="level",
        resources=(
            ManagementResourceBinding("entity_deployment_groups", ResourceType.ENTITY_DEPLOYMENT_GROUP),
        ),
    ),
    ManagementSectionSpec(
        key="unit_tags",
        title="🏷️ 单位标签管理",
        group="core_systems",
        resources=(ManagementResourceBinding("unit_tags", ResourceType.UNIT_TAG),),
    ),
    ManagementSectionSpec(
        key="shields",
        title="🛡️ 护盾管理",
        group="level",
        resources=(ManagementResourceBinding("shields", ResourceType.SHIELD),),
    ),
    ManagementSectionSpec(
        key="scan_tags",
        title="🔍 扫描标签管理",
        group="core_systems",
        resources=(ManagementResourceBinding("scan_tags", ResourceType.SCAN_TAG),),
    ),
    ManagementSectionSpec(
        key="paths",
        title="🛤️ 路径管理",
        group="level",
        resources=(ManagementResourceBinding("paths", ResourceType.PATH),),
    ),
    ManagementSectionSpec(
        key="multi_language",
        title="🌐 多语言文本管理",
        group="core_systems",
        resources=(ManagementResourceBinding("multi_language", ResourceType.MULTI_LANGUAGE),),
    ),
    ManagementSectionSpec(
        key="light_sources",
        title="💡 光源管理",
        group="level",
        resources=(ManagementResourceBinding("light_sources", ResourceType.LIGHT_SOURCE),),
    ),
    ManagementSectionSpec(
        key="chat_channels",
        title="💬 文字聊天管理",
        group="core_systems",
        resources=(ManagementResourceBinding("chat_channels", ResourceType.CHAT_CHANNEL),),
    ),
)


MANAGEMENT_RESOURCE_ORDER: Tuple[str, ...] = tuple(
    binding.key
    for section in MANAGEMENT_SECTIONS
    for binding in section.resources
)

MANAGEMENT_RESOURCE_BINDINGS = {
    binding.key: binding.resource_type
    for section in MANAGEMENT_SECTIONS
    for binding in section.resources
}

# 资源 key -> 左侧管理页标题映射，用于在其他视图中复用人类可读的分类名称
MANAGEMENT_RESOURCE_TITLES: Dict[str, str] = {
    binding.key: section.title
    for section in MANAGEMENT_SECTIONS
    for binding in section.resources
}

# 资源 key -> 聚合视图中的计数/展示模式映射。
# 用于在存档库等视图中统一处理“单配置类字段的汇总规则”与信号等特殊展开行为。
MANAGEMENT_RESOURCE_AGGREGATION_MODES: Dict[str, str] = {
    binding.key: binding.aggregation_mode
    for section in MANAGEMENT_SECTIONS
    for binding in section.resources
}

__all__ = [
    "ManagementResourceBinding",
    "ManagementSectionSpec",
    "MANAGEMENT_SECTIONS",
    "MANAGEMENT_RESOURCE_BINDINGS",
    "MANAGEMENT_RESOURCE_ORDER",
    "MANAGEMENT_RESOURCE_TITLES",
    "MANAGEMENT_RESOURCE_AGGREGATION_MODES",
]

