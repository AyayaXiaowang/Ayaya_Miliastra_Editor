"""
资源系统扩展配置（商店、背包、道具、装备、货币模板）。
从 `extended_configs.py` 聚合文件中拆分而来，现作为编辑器级权威定义模块。
注意：这些是编辑器级的模板配置，运行时配置请参考 combat.resource_system_configs
"""
from dataclasses import dataclass, field
from typing import List, Tuple
from enum import Enum


# ============================================================================
# 资源系统 (商店、掉落物、背包、装备、货币、道具)
# ============================================================================

class ShopType(Enum):
    """商店类型"""
    CUSTOM_GOODS = "自定义商品商店"
    SELF_BACKPACK = "自身背包商店"


@dataclass
class ShopItemConfig:
    """商店商品配置"""
    item_config_id: str = ""  # 道具配置ID
    item_sequence: str = ""  # 商品序号（自定义商品时使用）
    tab_category: str = ""  # 所属页签
    sort_priority: int = 0  # 排序优先级
    is_sellable: bool = True  # 是否可售
    sell_price: int = 0  # 售价
    is_limited: bool = False  # 是否限量
    stock_quantity: int = 0  # 库存数量


@dataclass
class ShopTemplateConfig:
    """
    商店模板配置（编辑器版，用于资源管理）
    参考：商店.md
    
    商店是一种提供虚拟物品交易的模块。
    注：这是编辑器级的商店模板配置，包含UI、页签等编辑器属性。
    如需运行时商店配置，请使用 combat.resource_system_configs.ShopConfig
    """
    shop_name: str = ""
    config_id: str = ""
    shop_type: ShopType = ShopType.CUSTOM_GOODS
    
    # 显示设置
    open_backpack_with_shop: bool = False  # 开启商店时同时打开背包
    tab_type: str = "无页签"  # 商品页签类型：无页签、默认页签、自定义页签
    custom_tabs: List[str] = field(default_factory=list)  # 自定义页签列表
    
    # 出售设置
    sell_items: List[ShopItemConfig] = field(default_factory=list)
    sell_range: str = "全部道具"  # 出售范围：全部道具、部分道具
    
    # 收购设置
    purchase_range: str = "不收购"  # 收购范围：不收购、全部道具、部分道具
    purchase_items: List[ShopItemConfig] = field(default_factory=list)
    
    doc_reference: str = "商店.md"


@dataclass
class BackpackTemplateConfig:
    """
    背包模板配置（编辑器版，用于资源管理）
    参考：背包.md
    
    背包是整个资源系统的容器。
    注：这是编辑器级的背包模板配置，包含掉落规则、外形等完整属性。
    如需组件级的简化配置，请使用 components.backpack_configs.BackpackComponentConfig
    """
    backpack_name: str = ""
    slot_count: int = 20  # 背包格数量
    destroy_drop_form: str = "应用道具掉落规则"  # 销毁时掉落形态
    loot_drop_form: str = "全员一份"  # 战利品掉落形式
    corresponding_drop_appearance: str = ""  # 对应掉落物外形
    
    doc_reference: str = "背包.md"


class ItemRarity(Enum):
    """道具稀有度"""
    GRAY = "灰色"
    GREEN = "绿色"
    BLUE = "蓝色"
    PURPLE = "紫色"
    ORANGE = "橙色"


@dataclass
class ItemTemplateConfig:
    """
    道具模板配置（编辑器版，用于资源管理）
    参考：道具.md
    
    道具是玩家可以在局内获取、使用或装备的虚拟物品。
    注：这是编辑器级的道具模板配置，包含UI、交互、掉落等完整属性。
    如需运行时道具配置，请使用 combat.resource_system_configs.ItemConfig
    """
    item_name: str = ""
    item_icon: str = ""
    config_id: str = ""
    
    # 基础设置
    rarity: ItemRarity = ItemRarity.GRAY
    stack_limit: int = 999  # 堆叠上限
    related_node_graph: str = ""  # 关联道具节点图
    backpack_tab: str = "材料"  # 背包内归属页签
    description: str = ""  # 简介
    has_currency_value: bool = False  # 是否有货币价值
    currency_value: int = 0  # 货币价值
    
    # 掉落设置
    destroy_drop_form: str = "掉落"  # 销毁时掉落形态
    drop_type: str = "全员一份"  # 掉落类型
    drop_appearance: str = ""  # 对应掉落物外形
    
    # 交互设置
    allow_destroy: bool = True  # 允许销毁
    allow_trade: bool = True  # 允许交易
    allow_use: bool = False  # 允许使用
    batch_use_allowed: bool = False  # 是否可批量使用
    auto_use_on_acquire: bool = False  # 进包后自动使用
    cooldown_time: float = 0.0  # 冷却时间(s)
    group_cooldown_time: float = 0.0  # 关系组冷却时间(s)
    cooldown_relation_group: List[str] = field(default_factory=list)  # 冷却连带关系组
    
    doc_reference: str = "道具.md"


@dataclass
class EquipmentEntryConfig:
    """装备词条配置"""
    entry_name: str = ""
    config_id: str = ""
    effect_timing: str = "装备时生效"  # 生效时机：获取时生效、装备时生效
    entry_type: str = "基础属性加成"  # 词条类型：基础属性加成、赋予节点图、赋予单位状态
    
    # 基础属性加成配置
    attribute_type: str = ""  # 选择属性
    bonus_type: str = "固定值"  # 加成类型：随机值、固定值
    random_range: Tuple[float, float] = (0.0, 0.0)  # 随机值范围
    fixed_bonus: float = 0.0  # 加成固定值
    description_type: str = "固定描述"  # 描述类型
    custom_description: str = ""  # 自定义描述
    
    # 赋予节点图
    related_node_graph: str = ""
    
    # 赋予单位状态
    related_unit_state: str = ""


@dataclass
class EquipmentSlotConfig:
    """装备栏位配置"""
    slot_name: str = ""
    allowed_equipment_types: List[str] = field(default_factory=list)  # 可装备类型
    icon: str = ""  # 图标


@dataclass
class EquipmentTemplateConfig:
    """
    装备模板配置（编辑器版，用于资源管理）
    参考：装备.md
    
    装备是一种道具的子类型，可以被装备到装备栏位上。
    注：这是编辑器级的装备模板配置，包含类型、标签、词条等完整属性。
    """
    equipment_name: str = ""
    equipment_icon: str = ""
    config_id: str = ""
    
    # 基础设置（装备不支持堆叠）
    rarity: ItemRarity = ItemRarity.GRAY
    
    # 交互设置
    equipment_types: List[str] = field(default_factory=list)  # 装备类型
    show_type_in_detail: bool = True  # 详情中显示类型
    show_tag_in_detail: bool = True  # 详情中显示标签
    tags: List[str] = field(default_factory=list)  # 选择标签
    initial_entries: List[str] = field(default_factory=list)  # 选择初始词条
    
    doc_reference: str = "装备.md"


@dataclass
class CurrencyTemplateConfig:
    """
    货币模板配置（编辑器版，用于资源管理）
    参考：货币.md
    
    货币是玩法中的一般等价物。
    注：这是编辑器级的货币模板配置，包含掉落规则、外形、优先级等完整属性。
    如需运行时货币配置，请使用 management.shop_economy_configs.CurrencyConfig
    """
    currency_name: str = ""
    config_id: str = ""
    
    # 基础属性
    icon: str = ""  # 图标
    destroy_drop_form: str = "掉落"  # 销毁时掉落形态
    loot_drop_form: str = "全员一份"  # 战利品掉落形式
    drop_appearance: str = ""  # 对应掉落物外形
    display_priority: int = 0  # 显示优先级
    
    doc_reference: str = "货币.md"

