"""实体相关配置 - 复苏、职业、技能等
重构说明：移除通配导入，改为显式导入以避免命名冲突
"""

# ============================================================================
# 实体基础配置
# ============================================================================
from .entity_configs import (
    # 枚举
    RevivePointSelectionRule as EntityRevivePointSelectionRule,  # 与revival_config重复
    SkillType as EntitySkillType,  # 与skill_config重复
    ResourceType as EntityResourceType,  # 与management重复
    # 复苏配置
    ReviveConfig as EntityReviveConfig,  # 与revival_config重复
    # 投射物配置
    LocalProjectileBaseSettings,
    LocalProjectileCombatParams,
    LocalProjectileLifecycle,
    LocalProjectileConfig,
    # 玩家与技能
    PlayerConfig,
    SkillConfig as EntitySkillConfig,  # 与skill_config重复
    # 战斗属性
    BaseCombatAttributes,
    # 实体配置
    CreatureConfig,
    CharacterConfig,
    ObjectConfig,
)

# ============================================================================
# 实体规则（完整）
# ============================================================================
from .entity_rules_complete import (
    EntityType,
    EntityRules,
)

# ============================================================================
# 复苏配置（详细）
# ============================================================================
from .revival_config import (
    # 枚举
    RevivalPointSelectionRule,
    DownReason,
    # 配置
    RevivalPoint,
    RevivalConfig as DetailedRevivalConfig,  # 使用别名区分entity_configs
)

# ============================================================================
# 职业配置
# ============================================================================
from .profession_config import (
    ProfessionType,
    ProfessionLevelConfig,
    ProfessionConfig,
)

# ============================================================================
# 技能配置（详细）
# ============================================================================
from .skill_config import (
    # 枚举
    SkillType as DetailedSkillType,  # 使用别名区分entity_configs
    TargetRangeType,
    AimEnterMode,
    SkillSlot,
    # 目标范围
    TargetRange,
    # 技能设置
    SkillBasicSettings,
    SkillNumericConfig,
    SkillLifecycleConfig,
    ComboSkillConfig,
    AimSkillConfig,
    # 动画与事件
    AnimationSlot,
    EventTrackItem,
    BranchConfig,
    ComboResponseEvent,
    AimStateConfig,
    SkillAnimationConfig,
    # 技能配置
    SkillConfig as DetailedSkillConfig,  # 使用别名区分entity_configs
)

# ============================================================================
# 导出所有符号
# ============================================================================
__all__ = [
    # 实体基础配置
    'EntityRevivePointSelectionRule',
    'EntitySkillType',
    'EntityResourceType',
    'EntityReviveConfig',
    'LocalProjectileBaseSettings',
    'LocalProjectileCombatParams',
    'LocalProjectileLifecycle',
    'LocalProjectileConfig',
    'PlayerConfig',
    'EntitySkillConfig',
    'BaseCombatAttributes',
    'CreatureConfig',
    'CharacterConfig',
    'ObjectConfig',
    # 实体规则
    'EntityType',
    'EntityRules',
    # 复苏配置（详细）
    'RevivalPointSelectionRule',
    'DownReason',
    'RevivalPoint',
    'DetailedRevivalConfig',
    # 职业配置
    'ProfessionType',
    'ProfessionLevelConfig',
    'ProfessionConfig',
    # 技能配置（详细）
    'DetailedSkillType',
    'TargetRangeType',
    'AimEnterMode',
    'SkillSlot',
    'TargetRange',
    'SkillBasicSettings',
    'SkillNumericConfig',
    'SkillLifecycleConfig',
    'ComboSkillConfig',
    'AimSkillConfig',
    'AnimationSlot',
    'EventTrackItem',
    'BranchConfig',
    'ComboResponseEvent',
    'AimStateConfig',
    'SkillAnimationConfig',
    'DetailedSkillConfig',
]

