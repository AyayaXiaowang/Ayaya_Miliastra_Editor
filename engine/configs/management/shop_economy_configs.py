"""
商店与经济配置模块
包含商店模板、货币、背包和装备配置
"""

from dataclasses import dataclass, field
from typing import List, Dict


# ============================================================================
# 货币与背包配置
# ============================================================================

@dataclass
class CurrencyConfig:
    """货币配置（管理系统版，用于货币背包管理）
    
    注：这是管理系统的货币配置，以字符串ID为主键，包含初始值和描述。
    如需运行时战斗系统的货币配置，请使用 combat.resource_system_configs.CurrencyConfig
    如需编辑器级的货币模板，请使用 specialized.resource_system_extended_configs.CurrencyTemplateConfig
    """
    currency_id: str
    currency_name: str
    icon: str = ""
    initial_amount: int = 0
    max_amount: int = 999999
    description: str = ""


@dataclass
class CurrencyBackpackConfig:
    """货币与背包配置"""
    config_id: str = "default"
    currencies: List[CurrencyConfig] = field(default_factory=list)
    backpack_capacity: int = 30  # 背包格子数
    max_stack_size: int = 99  # 堆叠上限
    initial_items: List[str] = field(default_factory=list)  # 初始道具ID列表
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "config_id": self.config_id,
            "currencies": [
                {
                    "currency_id": c.currency_id,
                    "currency_name": c.currency_name,
                    "icon": c.icon,
                    "initial_amount": c.initial_amount,
                    "max_amount": c.max_amount,
                    "description": c.description
                }
                for c in self.currencies
            ],
            "backpack_capacity": self.backpack_capacity,
            "max_stack_size": self.max_stack_size,
            "initial_items": self.initial_items,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'CurrencyBackpackConfig':
        currencies = [
            CurrencyConfig(
                currency_id=c["currency_id"],
                currency_name=c["currency_name"],
                icon=c.get("icon", ""),
                initial_amount=c.get("initial_amount", 0),
                max_amount=c.get("max_amount", 999999),
                description=c.get("description", "")
            )
            for c in data.get("currencies", [])
        ]
        
        return CurrencyBackpackConfig(
            config_id=data.get("config_id", "default"),
            currencies=currencies,
            backpack_capacity=data.get("backpack_capacity", 30),
            max_stack_size=data.get("max_stack_size", 99),
            initial_items=data.get("initial_items", []),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 装备数据配置
# ============================================================================

@dataclass
class EquipmentDataConfig:
    """装备数据配置"""
    equipment_id: str
    equipment_name: str
    equipment_slot: str  # head/body/legs/feet/weapon/shield/accessory
    base_attributes: Dict[str, float] = field(default_factory=dict)  # 基础属性
    special_effects: List[str] = field(default_factory=list)  # 特殊效果
    rarity: str = "common"
    level_requirement: int = 1
    icon: str = ""
    model: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "equipment_id": self.equipment_id,
            "equipment_name": self.equipment_name,
            "equipment_slot": self.equipment_slot,
            "base_attributes": self.base_attributes,
            "special_effects": self.special_effects,
            "rarity": self.rarity,
            "level_requirement": self.level_requirement,
            "icon": self.icon,
            "model": self.model,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'EquipmentDataConfig':
        return EquipmentDataConfig(
            equipment_id=data["equipment_id"],
            equipment_name=data["equipment_name"],
            equipment_slot=data["equipment_slot"],
            base_attributes=data.get("base_attributes", {}),
            special_effects=data.get("special_effects", []),
            rarity=data.get("rarity", "common"),
            level_requirement=data.get("level_requirement", 1),
            icon=data.get("icon", ""),
            model=data.get("model", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 商店模板管理配置
# ============================================================================

@dataclass
class ShopTemplateConfig:
    """商店模板配置"""
    shop_id: str
    shop_name: str
    shop_type: str = "general"  # general/equipment/consumable/special
    available_items: List[str] = field(default_factory=list)  # 商品ID列表
    refresh_interval: float = 0.0  # 刷新间隔（秒），0表示不刷新
    currency_type: str = "gold"  # 使用的货币类型
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "shop_id": self.shop_id,
            "shop_name": self.shop_name,
            "shop_type": self.shop_type,
            "available_items": self.available_items,
            "refresh_interval": self.refresh_interval,
            "currency_type": self.currency_type,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ShopTemplateConfig':
        return ShopTemplateConfig(
            shop_id=data["shop_id"],
            shop_name=data["shop_name"],
            shop_type=data.get("shop_type", "general"),
            available_items=data.get("available_items", []),
            refresh_interval=data.get("refresh_interval", 0.0),
            currency_type=data.get("currency_type", "gold"),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 商店与经济配置测试 ===\n")
    
    # 测试货币配置
    print("1. 货币与背包配置:")
    backpack = CurrencyBackpackConfig(
        config_id="default_backpack",
        backpack_capacity=40,
        max_stack_size=99
    )
    backpack.currencies.append(
        CurrencyConfig(
            currency_id="gold",
            currency_name="金币",
            initial_amount=100,
            max_amount=9999999
        )
    )
    print(f"   背包容量: {backpack.backpack_capacity}")
    print(f"   货币种类: {len(backpack.currencies)}")
    print(f"   货币名: {backpack.currencies[0].currency_name}")
    
    # 测试装备配置
    print("\n2. 装备数据配置:")
    equipment = EquipmentDataConfig(
        equipment_id="sword_001",
        equipment_name="铁剑",
        equipment_slot="weapon",
        base_attributes={"attack": 10.0, "speed": 1.5},
        rarity="common",
        level_requirement=1
    )
    print(f"   装备名: {equipment.equipment_name}")
    print(f"   装备槽: {equipment.equipment_slot}")
    print(f"   基础属性: {equipment.base_attributes}")
    
    # 测试商店配置
    print("\n3. 商店模板配置:")
    shop = ShopTemplateConfig(
        shop_id="shop_001",
        shop_name="武器商店",
        shop_type="equipment",
        available_items=["sword_001", "sword_002"],
        refresh_interval=3600.0
    )
    print(f"   商店名: {shop.shop_name}")
    print(f"   商店类型: {shop.shop_type}")
    print(f"   商品数量: {len(shop.available_items)}")
    
    print("\n✅ 商店与经济配置测试完成")

