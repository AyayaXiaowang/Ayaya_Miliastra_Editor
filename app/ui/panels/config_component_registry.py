"""配置组件注册表（右侧属性栏分组块）。

本模块为“配置组件”提供一个轻量级注册中心，用于：
- 统一标识技能/玩家/职业等面板中的 QGroupBox 分组块（如“生效目标”“基础”“复苏”等）；
- 为 UI 检查器等调试工具提供稳定的配置组件 ID，便于从控件快速定位到配置语义；
- 为后续文档/向导等功能提供可复用的元数据入口。

说明：
- 这里的“配置组件”是 UI 层的概念，对应右侧属性栏中的配置分组块，
  与实体上的“通用组件”（背包、定时器等）区分开来。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class UiConfigComponentDefinition:
    """配置组件定义。

    Attributes:
        id: 全局唯一 ID，例如 "combat.player.active_targets"。
        title: 分组标题文本，例如 "生效目标"、"基础"、"复苏"。
        panel_class_name: 所属面板的 Python 类名，例如 "CombatPlayerEditorPanel"。
        description: 简要说明该分组负责的配置内容。
        json_path: 对应配置在存档 JSON 中的大致路径说明，仅用于调试文案。
    """

    id: str
    title: str
    panel_class_name: str
    description: str
    json_path: str


_CONFIG_COMPONENTS: Dict[Tuple[str, str], UiConfigComponentDefinition] = {}


def _register(definition: UiConfigComponentDefinition) -> None:
    """在本模块内部注册一个配置组件定义。"""
    key = (definition.panel_class_name, definition.title)
    _CONFIG_COMPONENTS[key] = definition


# 战斗预设 · 玩家模板 · 玩家编辑页签
_register(
    UiConfigComponentDefinition(
        id="combat.player.active_targets",
        title="生效目标",
        panel_class_name="CombatPlayerEditorPanel",
        description="配置当前玩家模板在关卡中的目标玩家范围（单个玩家或全部玩家）。",
        json_path="metadata.player_editor.player.active_targets",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.player.basic",
        title="基础",
        panel_class_name="CombatPlayerEditorPanel",
        description="配置玩家等级、出生点与初始职业等基础属性。",
        json_path="metadata.player_editor.player.basic",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.player.resurrection",
        title="复苏",
        panel_class_name="CombatPlayerEditorPanel",
        description="配置玩家是否允许复苏、复苏次数与复苏点规则等复苏行为。",
        json_path="metadata.player_editor.player.resurrection",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.player.special_knockout",
        title="特殊被击倒损伤",
        panel_class_name="CombatPlayerEditorPanel",
        description="配置特殊被击倒场景下扣除最大生命值的比例。",
        json_path="metadata.player_editor.player.special_knockout",
    )
)

# 战斗预设 · 技能详情面板 · 技能编辑页签
_register(
    UiConfigComponentDefinition(
        id="combat.skill.basic_info",
        title="基础信息",
        panel_class_name="CombatSkillPanel",
        description="配置技能的基础元信息（配置 ID、名称、技能类型）。",
        json_path="metadata.skill_editor.basic_info",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.skill.basic_settings",
        title="基础设置",
        panel_class_name="CombatSkillPanel",
        description="配置技能是否启用坠崖保护、是否可在空中释放以及技能备注。",
        json_path="metadata.skill_editor.basic",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.skill.combo",
        title="连段配置",
        panel_class_name="CombatSkillPanel",
        description="配置技能是否开启蓄力分支以及蓄力公共前摇等连段相关参数。",
        json_path="metadata.skill_editor.combo",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.skill.numeric",
        title="数值配置",
        panel_class_name="CombatSkillPanel",
        description="配置冷却、次数限制、资源消耗与索敌范围等数值参数。",
        json_path="metadata.skill_editor.numeric",
    )
)

_register(
    UiConfigComponentDefinition(
        id="combat.skill.lifecycle",
        title="生命周期管理",
        panel_class_name="CombatSkillPanel",
        description="配置技能生命周期次数上限与达到上限后的销毁策略。",
        json_path="metadata.skill_editor.lifecycle",
    )
)


def find_config_component(
    panel_class_name: str,
    groupbox_title: str,
) -> Optional[UiConfigComponentDefinition]:
    """根据面板类名与 QGroupBox 标题查找配置组件定义。

    该函数供 UI 检查器等调试工具调用，用于在不引入 UI 依赖的情况下
    为指定分组块提供稳定的配置组件 ID 与说明。
    """
    key = (panel_class_name, groupbox_title)
    return _CONFIG_COMPONENTS.get(key)


__all__ = ["UiConfigComponentDefinition", "find_config_component"]


