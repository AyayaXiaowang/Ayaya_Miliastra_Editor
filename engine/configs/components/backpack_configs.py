"""
组件配置 - 背包与装备
基于知识库文档定义的背包、装备、战利品组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class BackpackComponentConfig:
    """背包组件配置（简化版，用于实体组件系统）
    
    注：这是组件级的简化配置，仅包含基本容量。
    如需完整的背包模板配置（包含掉落规则、外形等），请使用 specialized.resource_system_extended_configs.BackpackTemplateConfig
    """
    # 背包容量
    capacity: int = 20
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "背包容量": self.capacity
        }


@dataclass
class BackpackItemConfig:
    """背包初始物品配置"""
    item_id: str = ""
    item_count: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "物品ID": self.item_id,
            "物品数量": self.item_count
        }


@dataclass
class BackpackEntityConfig:
    """
    背包实体组件配置（完整版）
    来源：文本气泡.md（实际为背包.md，第1-16行）
    
    注：这是实体级的背包配置，包含模板引用和初始物品。
    """
    # 背包模板
    backpack_template: str = ""
    # 初始物品
    initial_items: List[BackpackItemConfig] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "背包模板": self.backpack_template,
            "初始物品": [item.to_dict() for item in self.initial_items]
        }


@dataclass
class EquipmentSlotConfig:
    """装备栏组件配置（待完善）"""
    # 装备槽位列表
    slots: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "装备槽位": self.slots
        }


@dataclass
class LootConfig:
    """战利品组件配置（待完善）"""
    # 战利品表
    loot_table: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "战利品表": self.loot_table
        }

