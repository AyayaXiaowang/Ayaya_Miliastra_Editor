"""
资源系统配置
基于知识库：资源系统相关文档
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


# ============================================================================
# 道具系统 (道具.md)
# ============================================================================

class ItemType(str, Enum):
    """道具类型"""
    EQUIPMENT = "装备"
    MATERIAL = "材料"
    CONSUMABLE = "消耗品"
    VALUABLE = "贵重物品"


class ItemRarity(str, Enum):
    """道具稀有度"""
    GRAY = "灰色"
    GREEN = "绿色"
    BLUE = "蓝色"
    PURPLE = "紫色"
    ORANGE = "橙色"


class DropBehavior(str, Enum):
    """销毁时掉落形态"""
    DROP = "掉落"  # 转化为掉落物实体
    DESTROY = "销毁"  # 道具销毁
    KEEP = "保留"  # 保留在背包（仅角色有意义）


class DropType(str, Enum):
    """掉落类型"""
    SHARED = "全员一份"  # 所有玩家共享
    PER_PLAYER = "每人一份"  # 每个玩家独立掉落


@dataclass
class ItemBasicSettings:
    """道具基础设置"""
    item_name: str
    item_icon: str
    config_id: int
    rarity: ItemRarity = ItemRarity.GRAY
    stack_limit: int = 99
    associated_node_graph: Optional[int] = None  # 关联道具节点图
    inventory_tab: str = "全部"  # 背包内归属页签
    description: str = ""
    has_currency_value: bool = False
    currency_value: int = 0
    
    doc_reference: str = "道具.md:14-22"


@dataclass
class ItemDropSettings:
    """道具掉落设置"""
    destroy_drop_behavior: DropBehavior = DropBehavior.DROP
    drop_type: DropType = DropType.SHARED
    drop_entity_id: Optional[int] = None  # 对应掉落物外形
    
    doc_reference: str = "道具.md:24-33"


@dataclass
class ItemInteractionSettings:
    """道具交互设置"""
    allow_destroy: bool = True
    allow_trade: bool = True
    allow_use: bool = False
    batch_use: bool = False
    auto_use_on_acquire: bool = False
    cooldown: float = 0.0  # 冷却时间(s)
    group_cooldown: float = 0.0  # 关系组冷却时间(s)
    cooldown_group_items: List[int] = field(default_factory=list)  # 冷却连带关系组
    
    doc_reference: str = "道具.md:35-44"


@dataclass
class ItemConfig:
    """道具配置（运行时版，用于战斗资源系统）
    
    注：这是运行时的道具配置，将道具属性拆分为 basic/drop/interaction 子结构。
    如需编辑器级的完整道具模板，请使用 specialized.resource_system_extended_configs.ItemTemplateConfig
    """
    item_type: ItemType
    basic_settings: ItemBasicSettings
    drop_settings: ItemDropSettings
    interaction_settings: ItemInteractionSettings
    
    doc_reference: str = "道具.md"


# ============================================================================
# 装备系统 (装备.md)
# ============================================================================

class EquipmentEffectTiming(str, Enum):
    """词条生效时机"""
    ON_ACQUIRE = "获取时生效"  # 进入背包时生效
    ON_EQUIP = "装备时生效"  # 装入装备栏位时生效


class EquipmentAttributeType(str, Enum):
    """装备属性类型"""
    # 具体属性由基础战斗属性定义
    HEALTH = "生命值"
    ATTACK = "攻击力"
    DEFENSE = "防御力"


class AttributeBoostType(str, Enum):
    """加成类型"""
    RANDOM = "随机值"
    FIXED = "固定值"


class EntryDescriptionType(str, Enum):
    """词条描述类型"""
    PRESET = "固定描述"
    CUSTOM = "自定义描述"


class EntryType(str, Enum):
    """词条类型"""
    ATTRIBUTE_BOOST = "基础属性加成"
    GRANT_NODE_GRAPH = "赋予节点图"
    GRANT_UNIT_STATE = "赋予单位状态"


@dataclass
class EquipmentType:
    """装备类型定义"""
    type_name: str
    config_id: int
    
    doc_reference: str = "装备.md:21-30"


@dataclass
class EquipmentTag:
    """装备标签定义"""
    tag_name: str
    config_id: int
    
    doc_reference: str = "装备.md:32-37"


@dataclass
class EquipmentEntry:
    """装备词条定义"""
    entry_name: str
    config_id: int
    effect_timing: EquipmentEffectTiming
    entry_type: EntryType
    
    # 基础属性加成相关
    attribute_type: Optional[EquipmentAttributeType] = None
    boost_type: Optional[AttributeBoostType] = None
    random_range: Optional[tuple] = None  # (min, max)
    fixed_value: Optional[float] = None
    description_type: Optional[EntryDescriptionType] = None
    custom_description: str = ""
    
    # 赋予节点图相关
    associated_node_graph: Optional[int] = None
    
    # 赋予单位状态相关
    associated_unit_state: Optional[int] = None
    
    doc_reference: str = "装备.md:39-63"


@dataclass
class EquipmentSlot:
    """装备栏位设置"""
    slot_name: str
    allowed_types: List[int] = field(default_factory=list)  # 可装备类型
    icon: str = ""
    
    doc_reference: str = "装备.md:77-80"


@dataclass
class EquipmentSlotTemplate:
    """装备栏模板"""
    template_name: str
    config_id: int
    slots: List[EquipmentSlot] = field(default_factory=list)
    
    doc_reference: str = "装备.md:71-81"


@dataclass
class EquipmentSlotComponent:
    """装备栏组件（仅角色可用）"""
    slot_template_id: int
    
    doc_reference: str = "装备.md:83-87"
    entity_type_restriction: str = "仅角色可用"


# ============================================================================
# 货币系统（基于知识库补充）
# ============================================================================

@dataclass
class CurrencyConfig:
    """货币配置（运行时版，用于战斗资源系统）
    
    注：这是运行时的货币配置，以整数ID为主键。
    如需管理系统的货币配置（含初始值），请使用 management.shop_economy_configs.CurrencyConfig
    如需编辑器级的货币模板，请使用 specialized.resource_system_extended_configs.CurrencyTemplateConfig
    """
    currency_name: str
    currency_id: int
    icon: str
    max_amount: int = 999999
    
    doc_reference: str = "货币.md"


# ============================================================================
# 商店系统（基于知识库补充）
# ============================================================================

@dataclass
class ShopItemConfig:
    """商店商品配置"""
    item_id: int
    price: int
    currency_type: int
    stock: int = -1  # -1表示无限
    
    doc_reference: str = "商店.md"


@dataclass
class ShopConfig:
    """商店配置（运行时版，用于战斗资源系统）
    
    注：这是运行时的商店配置，简化为商品列表。
    如需编辑器级的商店模板（含UI、页签），请使用 specialized.resource_system_extended_configs.ShopTemplateConfig
    """
    shop_name: str
    shop_id: int
    items: List[ShopItemConfig] = field(default_factory=list)
    
    doc_reference: str = "商店.md"


# ============================================================================
# 掉落物系统（基于知识库补充）
# ============================================================================

@dataclass
class LootTableEntry:
    """掉落表条目"""
    item_id: int
    drop_rate: float  # 0.0-1.0
    quantity_range: tuple = (1, 1)  # (min, max)
    
    doc_reference: str = "掉落物.md"


@dataclass
class LootTableConfig:
    """掉落表配置"""
    loot_table_id: int
    entries: List[LootTableEntry] = field(default_factory=list)
    
    doc_reference: str = "掉落物.md"


# ============================================================================
# 验证函数
# ============================================================================

def validate_equipment_slot_component(entity_type: str) -> List[str]:
    """验证装备栏组件可用性"""
    errors = []
    
    # 装备栏组件仅角色可用 (装备.md:84)
    if entity_type != "角色":
        errors.append(
            "[装备栏错误] 装备栏组件仅有角色可以添加\n"
            f"当前实体类型：{entity_type}\n"
            "参考：装备.md:84"
        )
    
    return errors


def validate_equipment_type_match(
    equipment_types: List[int], 
    slot_types: List[int]
) -> List[str]:
    """验证装备类型匹配"""
    errors = []
    
    # 交集不为空时才能装备 (装备.md:25)
    if not set(equipment_types) & set(slot_types):
        errors.append(
            "[装备类型错误] 装备类型与装备栏位类型不匹配\n"
            f"装备类型：{equipment_types}\n"
            f"栏位类型：{slot_types}\n"
            "参考：装备.md:25 '交集不为空时即可成功装备'"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 资源系统配置测试 ===\n")
    
    # 测试道具配置
    print("1. 道具配置：")
    item = ItemConfig(
        item_type=ItemType.CONSUMABLE,
        basic_settings=ItemBasicSettings(
            item_name="生命药水",
            item_icon="health_potion.png",
            config_id=1001,
            rarity=ItemRarity.BLUE,
            stack_limit=50
        ),
        drop_settings=ItemDropSettings(
            destroy_drop_behavior=DropBehavior.DROP,
            drop_type=DropType.PER_PLAYER
        ),
        interaction_settings=ItemInteractionSettings(
            allow_use=True,
            batch_use=True,
            cooldown=5.0
        )
    )
    print(f"   道具名称：{item.basic_settings.item_name}")
    print(f"   稀有度：{item.basic_settings.rarity.value}")
    print(f"   可使用：{item.interaction_settings.allow_use}")
    
    # 测试装备词条
    print("\n2. 装备词条：")
    entry = EquipmentEntry(
        entry_name="力量加成",
        config_id=2001,
        effect_timing=EquipmentEffectTiming.ON_EQUIP,
        entry_type=EntryType.ATTRIBUTE_BOOST,
        attribute_type=EquipmentAttributeType.ATTACK,
        boost_type=AttributeBoostType.RANDOM,
        random_range=(10.0, 20.0)
    )
    print(f"   词条名称：{entry.entry_name}")
    print(f"   生效时机：{entry.effect_timing.value}")
    print(f"   加成类型：{entry.boost_type.value if entry.boost_type else 'N/A'}")
    
    # 测试装备栏模板
    print("\n3. 装备栏模板：")
    slot_template = EquipmentSlotTemplate(
        template_name="战士装备栏",
        config_id=3001,
        slots=[
            EquipmentSlot(slot_name="武器", allowed_types=[1, 2]),
            EquipmentSlot(slot_name="护甲", allowed_types=[3]),
            EquipmentSlot(slot_name="饰品", allowed_types=[4, 5])
        ]
    )
    print(f"   模板名称：{slot_template.template_name}")
    print(f"   栏位数量：{len(slot_template.slots)}")
    
    print("\n✅ 资源系统配置测试完成")

