"""专业化配置 - 高级配置、扩展配置等
重构说明：
- 移除通配导入，改为显式导入以避免命名冲突
- specialized 存档内容复杂且存在大量重复定义（LevelSettingsConfig、EffectConfig等）
- 建议调用方使用模块前缀访问：
  from engine.configs.specialized import ui_widget_configs
  from engine.configs.specialized import advanced_configs as spec_advanced
  
注意：本包内多个文件存在同名类（用于不同领域），已在此处统一用别名区分
"""

# ============================================================================
# 核心专业化配置（specialized_configs.py）
# ============================================================================
from .specialized_configs import (
    # 属性增长
    AttributeGrowthMode,
    CombatAttributesConfig as SpecializedCombatAttributesConfig,
    CreatureCombatAttributesConfig,
    # 仇恨系统
    AggroMode,
    AggroGlobalConfig,
    ObjectAggroConfig,
    ProfessionAggroConfig,
    CreatureAggroConfig,
    AggroCalculation,
    # 受击盒与设置
    HitboxConfig as SpecializedHitboxConfig,
    GeneralSettingsConfig as SpecializedGeneralSettingsConfig,
    CombatSettingsConfig as SpecializedCombatSettingsConfig,  # 与 combat 包重复
    AbilityUnitConfig as SpecializedAbilityUnitConfig,  # 与 combat 包重复
)

# ============================================================================
# UI控件配置（ui_widget_configs.py）
# 推荐使用：from engine.configs.specialized import ui_widget_configs
# ============================================================================
from .ui_widget_configs import (
    # 枚举
    WidgetType,
    WidgetDisplayMode,
    AnchorPoint,
    # 交互按钮
    InteractionButtonConfig as SpecializedInteractionButtonConfig,
    # 卡牌选择器
    CardSelectionMode,
    CardConfig,
    CardSelectorConfig,
    # 弹窗
    PopupType,
    PopupButtonConfig,
    PopupConfig as SpecializedPopupConfig,
    # 文本框
    TextBoxType,
    TextBoxConfig as SpecializedTextBoxConfig,
    # 计分板
    ScoreboardSortMode,
    ScoreboardColumn,
    ScoreboardConfig as SpecializedScoreboardConfig,
    # 计时器
    TimerMode as UIWidgetTimerMode,  # 与 components 重复
    TimerDisplayFormat,
    TimerConfig as UIWidgetTimerConfig,  # 与 management 重复
    # 进度条
    ProgressBarOrientation,
    ProgressBarFillMode,
    ProgressBarConfig as SpecializedProgressBarConfig,
    # 界面控件组（简化版，用于基础序列化）
    SimpleWidgetGroupConfig,
    SimpleUILayoutConfig,
    # 验证函数
    validate_widget_position,
    validate_scoreboard_config,
)

# ============================================================================
# 完整特化配置系统（专门模块）
# ============================================================================
# - hitbox_configs.py: 受击盒设置
# - creature_settings_configs.py: 造物常规设置
# - combat_effect_configs.py: 战斗设置与战斗特效
# - ability_units_configs.py: 能力单元
#
# 推荐使用方式（按需导入）：
#   from engine.configs.specialized import hitbox_configs
#   from engine.configs.specialized import creature_settings_configs
#   from engine.configs.specialized import combat_effect_configs
#   from engine.configs.specialized import ability_units_configs
#
# 不再提供 complete_specialized_configs 聚合入口；如需迁移旧代码，
# 请将导入路径改为上述对应模块。

# ============================================================================
# 扩展配置系统（已拆分为多个模块，不再提供 extended_configs 聚合入口）
# ============================================================================
# - deployment_configs.py: 实体布设组、数据复制粘贴
# - node_graph_configs.py: 节点图核心、调试、结构体
# - game_systems_configs.py: 技能资源、聊天、成就、排行榜、竞技段位
# - creature_info_configs.py: 单位状态效果、造物技能、行为模式
# - resource_system_extended_configs.py: 商店/背包/道具/装备/货币模板
#
# 推荐使用方式（按需导入）：
#   from engine.configs.specialized import node_graph_configs
#   from engine.configs.specialized import game_systems_configs
#   from engine.configs.specialized import creature_info_configs
#   from engine.configs.specialized import resource_system_extended_configs

# ============================================================================
# 注意事项：以下模块包含大量重复定义的类，不建议通配导入
# 推荐使用模块前缀访问：
#   from engine.configs.specialized import advanced_configs
#   shield_cfg = advanced_configs.ShieldConfig(...)
# ============================================================================
# - advanced_configs.py: ShieldConfig（与management重复）
# - additional_advanced_configs.py: LevelSettingsConfig（与management重复）、EffectConfig
# - overview_configs.py: 全局概览，不导出具体类

# 如果确实需要使用这些模块的类，请使用：
# from engine.configs.specialized.advanced_configs import ShieldConfig as AdvancedShieldConfig
# from engine.configs.specialized.additional_advanced_configs import LevelSettingsConfig as EditorLevelSettingsConfig

# ============================================================================
# 导出所有符号（仅核心符号）
# ============================================================================
__all__ = [
    # 核心专业化配置
    'AttributeGrowthMode',
    'SpecializedCombatAttributesConfig',
    'CreatureCombatAttributesConfig',
    'AggroMode',
    'AggroGlobalConfig',
    'ObjectAggroConfig',
    'ProfessionAggroConfig',
    'CreatureAggroConfig',
    'AggroCalculation',
    'SpecializedHitboxConfig',
    'SpecializedGeneralSettingsConfig',
    'SpecializedCombatSettingsConfig',
    'SpecializedAbilityUnitConfig',
    # UI控件配置
    'WidgetType',
    'WidgetDisplayMode',
    'AnchorPoint',
    'SpecializedInteractionButtonConfig',
    'CardSelectionMode',
    'CardConfig',
    'CardSelectorConfig',
    'PopupType',
    'PopupButtonConfig',
    'SpecializedPopupConfig',
    'TextBoxType',
    'SpecializedTextBoxConfig',
    'ScoreboardSortMode',
    'ScoreboardColumn',
    'SpecializedScoreboardConfig',
    'UIWidgetTimerMode',
    'TimerDisplayFormat',
    'UIWidgetTimerConfig',
    'ProgressBarOrientation',
    'ProgressBarFillMode',
    'SpecializedProgressBarConfig',
    'SimpleWidgetGroupConfig',
    'SimpleUILayoutConfig',
    'validate_widget_position',
    'validate_scoreboard_config',
]

