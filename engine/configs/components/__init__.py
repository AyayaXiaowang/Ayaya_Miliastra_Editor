"""组件相关配置 - 组件定义和UI控件组"""

# 变量相关
from .variable_configs import (
    VariableDataType,
    CustomVariableConfig,
    CustomVariableComponentConfig
)

# 计时器相关
from .timer_configs import (
    TimerType,
    SourceEntityType,
    TimerSegment,
    TimerDefinition,
    GlobalTimerDefinition,
    GlobalTimerComponentConfig
)

# 碰撞相关
from .collision_configs import (
    TriggerShape,
    CollisionTargetType,
    TriggerArea,
    CollisionTriggerDefinition,
    CollisionTriggerConfig,
    CollisionTriggerSourceConfig,
    ExtraCollisionDefinition,
    ExtraCollisionComponentConfig
)

# 状态相关
from .status_configs import (
    UnitStatusConfig
)

# 小地图相关
from .minimap_configs import (
    MinimapMarkType,
    MinimapColorLogic,
    MinimapMarkDefinition,
    MinimapComponentConfig
)

# 背包与装备相关
from .backpack_configs import (
    BackpackComponentConfig,
    BackpackItemConfig,
    BackpackEntityConfig,
    EquipmentSlotConfig,
    LootConfig
)

# 扫描标签相关
from .scan_tag_configs import (
    ScanState,
    ScanTagDefinition,
    ScanTagComponentConfig
)

# 运动器相关
from .motor_configs import (
    ProjectileMotorConfig,
    FollowType,
    TrackingMode,
    CoordinateSystemType,
    FollowMotorComponentConfig,
    BasicMotorType,
    PathLoopType,
    BasicMotorState,
    PathPoint,
    BasicMotorDefinition,
    BasicMotorComponentConfig,
    PerturbatorType,
    PerturbatorDirection,
    PerturbatorDefinition,
    CharacterPerturbatorComponentConfig
)

# 商店相关
from .shop_configs import (
    ShopSourceType,
    ShopTabType,
    PurchaseRange,
    ShopDefinition,
    ShopComponentConfig
)

# 特效相关
from .effect_configs import (
    EffectAssetType,
    EffectPlayDefinition,
    EffectPlayConfig
)

# 命中检测相关
from .hit_detection_configs import (
    HitTriggerType,
    CCDType,
    CampFilter,
    HitLayerType,
    HitDetectionArea,
    HitDetectionConfig
)

# UI组件相关
from .ui_configs import (
    NameplateConfig,
    BubbleConfig
)

# 挂接点相关
from .attach_point_configs import (
    UnitAttachPointConfig,
    CustomAttachPoint,
    CustomAttachPointComponentConfig
)

# 选项卡相关
from .tab_configs import (
    TabDefinition,
    TabComponentConfig
)

# UI控件组（显式导入以避免命名冲突）
from .ui_control_group_model import (
    # 常量
    BUILTIN_WIDGET_TYPES,
    TEMPLATE_WIDGET_TYPES,
    DEVICE_PRESETS,
    # 类
    UIWidgetConfig,
    UIControlGroupTemplate,
    UILayout,
    DevicePreset,
    # 函数
    create_default_layout,
    create_builtin_widget_templates,
    create_template_widget_preset,
)

# 定义 __all__ 以明确导出内容
__all__ = [
    # 变量相关
    'VariableDataType',
    'CustomVariableConfig',
    'CustomVariableComponentConfig',
    
    # 计时器相关
    'TimerType',
    'SourceEntityType',
    'TimerSegment',
    'TimerDefinition',
    'GlobalTimerDefinition',
    'GlobalTimerComponentConfig',
    
    # 碰撞相关
    'TriggerShape',
    'CollisionTargetType',
    'TriggerArea',
    'CollisionTriggerDefinition',
    'CollisionTriggerConfig',
    'CollisionTriggerSourceConfig',
    'ExtraCollisionDefinition',
    'ExtraCollisionComponentConfig',
    
    # 状态相关
    'UnitStatusConfig',
    
    # 小地图相关
    'MinimapMarkType',
    'MinimapColorLogic',
    'MinimapMarkDefinition',
    'MinimapComponentConfig',
    
    # 背包与装备相关
    'BackpackComponentConfig',
    'BackpackItemConfig',
    'BackpackEntityConfig',
    'EquipmentSlotConfig',
    'LootConfig',
    
    # 扫描标签相关
    'ScanState',
    'ScanTagDefinition',
    'ScanTagComponentConfig',
    
    # 运动器相关
    'ProjectileMotorConfig',
    'FollowType',
    'TrackingMode',
    'CoordinateSystemType',
    'FollowMotorComponentConfig',
    'BasicMotorType',
    'PathLoopType',
    'BasicMotorState',
    'PathPoint',
    'BasicMotorDefinition',
    'BasicMotorComponentConfig',
    'PerturbatorType',
    'PerturbatorDirection',
    'PerturbatorDefinition',
    'CharacterPerturbatorComponentConfig',
    
    # 商店相关
    'ShopSourceType',
    'ShopTabType',
    'PurchaseRange',
    'ShopDefinition',
    'ShopComponentConfig',
    
    # 特效相关
    'EffectAssetType',
    'EffectPlayDefinition',
    'EffectPlayConfig',
    
    # 命中检测相关
    'HitTriggerType',
    'CCDType',
    'CampFilter',
    'HitLayerType',
    'HitDetectionArea',
    'HitDetectionConfig',
    
    # UI组件相关
    'NameplateConfig',
    'BubbleConfig',
    
    # 挂接点相关
    'UnitAttachPointConfig',
    'CustomAttachPoint',
    'CustomAttachPointComponentConfig',
    
    # 选项卡相关
    'TabDefinition',
    'TabComponentConfig',
    
    # UI控件组
    'BUILTIN_WIDGET_TYPES',
    'TEMPLATE_WIDGET_TYPES',
    'DEVICE_PRESETS',
    'UIWidgetConfig',
    'UIControlGroupTemplate',
    'UILayout',
    'DevicePreset',
    'create_default_layout',
    'create_builtin_widget_templates',
    'create_template_widget_preset',
]
