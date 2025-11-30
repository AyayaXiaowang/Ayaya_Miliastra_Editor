"""战斗系统配置 - 战斗预设、技能、资源系统等
重构说明：移除通配导入，改为显式导入以避免命名冲突
"""

# ============================================================================
# 战斗预设模型
# ============================================================================
from .combat_presets_model import (
    PlayerClassConfig,
    UnitStatusConfig as CombatPresetUnitStatusConfig,  # 与components重复
    SkillConfig as CombatPresetSkillConfig,  # 与entities重复
    ProjectileConfig,
    ItemConfig as CombatPresetItemConfig,  # 与resource_system重复
)

# ============================================================================
# 战斗能力配置
# ============================================================================
from .combat_ability_configs import (
    # 枚举
    EffectAssetType as CombatEffectAssetType,  # 与components重复
    AbilityUnitType,
    AbilityInvokeType,
    # 特效配置
    EffectConfig as CombatEffectConfig,  # 与specialized重复，使用别名
    # 战斗设置
    CombatSettingsConfig,
    # 能力单元配置
    AttackBoxAbilityConfig,
    DirectAttackAbilityConfig,
    PlayEffectAbilityConfig,
    CreateProjectileAbilityConfig,
    AddUnitStateAbilityConfig,
    RemoveUnitStateAbilityConfig,
    RestoreHealthAbilityConfig,
    AbilityUnitDefinition,
    AbilityInvokeConfig,
    # 验证函数
    validate_ability_invoke_compatibility,
    validate_ability_config_complete,
)

# ============================================================================
# 资源系统配置
# ============================================================================
from .resource_system_configs import (
    # 道具相关枚举
    ItemType,
    ItemRarity,
    DropBehavior,
    DropType,
    # 道具配置
    ItemBasicSettings,
    ItemDropSettings,
    ItemInteractionSettings,
    ItemConfig as ResourceSystemItemConfig,  # 与combat_presets重复，使用别名
    # 装备相关枚举
    EquipmentEffectTiming,
    EquipmentAttributeType,
    AttributeBoostType,
    EntryDescriptionType,
    EntryType,
    # 装备配置
    EquipmentType,
    EquipmentTag,
    EquipmentEntry,
    EquipmentSlot,
    EquipmentSlotTemplate,
    EquipmentSlotComponent,
    # 货币配置
    CurrencyConfig as ResourceSystemCurrencyConfig,  # 与management重复
    # 商店配置
    ShopItemConfig as ResourceSystemShopItemConfig,  # 与management重复
    ShopConfig as ResourceSystemShopConfig,  # 与management重复
    # 掉落配置
    LootTableEntry,
    LootTableConfig,
    # 验证函数
    validate_equipment_slot_component,
    validate_equipment_type_match,
)

# ============================================================================
# 导出所有符号
# ============================================================================
__all__ = [
    # 战斗预设
    'PlayerClassConfig',
    'CombatPresetUnitStatusConfig',
    'CombatPresetSkillConfig',
    'ProjectileConfig',
    'CombatPresetItemConfig',
    # 战斗能力
    'CombatEffectAssetType',
    'AbilityUnitType',
    'AbilityInvokeType',
    'CombatEffectConfig',
    'CombatSettingsConfig',
    'AttackBoxAbilityConfig',
    'DirectAttackAbilityConfig',
    'PlayEffectAbilityConfig',
    'CreateProjectileAbilityConfig',
    'AddUnitStateAbilityConfig',
    'RemoveUnitStateAbilityConfig',
    'RestoreHealthAbilityConfig',
    'AbilityUnitDefinition',
    'AbilityInvokeConfig',
    'validate_ability_invoke_compatibility',
    'validate_ability_config_complete',
    # 资源系统
    'ItemType',
    'ItemRarity',
    'DropBehavior',
    'DropType',
    'ItemBasicSettings',
    'ItemDropSettings',
    'ItemInteractionSettings',
    'ResourceSystemItemConfig',
    'EquipmentEffectTiming',
    'EquipmentAttributeType',
    'AttributeBoostType',
    'EntryDescriptionType',
    'EntryType',
    'EquipmentType',
    'EquipmentTag',
    'EquipmentEntry',
    'EquipmentSlot',
    'EquipmentSlotTemplate',
    'EquipmentSlotComponent',
    'ResourceSystemCurrencyConfig',
    'ResourceSystemShopItemConfig',
    'ResourceSystemShopConfig',
    'LootTableEntry',
    'LootTableConfig',
    'validate_equipment_slot_component',
    'validate_equipment_type_match',
]

