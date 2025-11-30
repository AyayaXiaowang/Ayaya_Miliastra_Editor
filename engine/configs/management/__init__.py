"""管理配置 - 计时器、变量、镜头、路径等
重构说明：移除通配导入，改为显式导入以避免命名冲突
调用方建议：from engine.configs.management import timer_variable_configs
"""

# ============================================================================
# 计时器与变量
# ============================================================================
from .timer_variable_configs import (
    TimerManagementConfig,
    LevelVariableConfig,
)

# ============================================================================
# 基础信息（实体通用配置）
# ============================================================================
from .basic_info_configs import (
    # 基础配置
    TransformConfig,
    NativeCollisionConfig,
    VisibilityConfig,
    InitializationConfig,
    CampConfig,
    # 枚举
    CampRelation,
    ViewDetectionMode,
    PresetStateIndex,
    # 标签与状态
    UnitTagDefinition,
    UnitTagConfig,
    PresetStateConfig,
    MountPointConfig,
    DecorationConfig,
    # 负载优化
    LoadOptimizationGlobalConfig,
    LoadOptimizationEntityConfig,
    # 节点图变量
    NodeGraphVariableConfig,
    # 验证函数
    validate_transform_for_entity,
    validate_preset_state_for_entity,
    validate_unit_tags_for_entity,
)

# ============================================================================
# 镜头与路径配置（按camera_and_path_configs拆分）
# ============================================================================
from .camera_and_path_configs import (
    # 镜头配置
    CameraMode as CameraAndPathCameraMode,
    CameraTransitionType,
    CameraConfig,
    # 路径配置
    PathType,
    PathLoopMode,
    PathPoint,
    GlobalPathConfig as CameraPathGlobalPathConfig,
    # 预设点配置
    PresetPointType as CameraPathPresetPointType,
    PresetPointConfig as CameraPathPresetPointConfig,
    # 节点定义
    CAMERA_NODES,
    PATH_NODES,
    PRESET_POINT_NODES,
    ALL_CAMERA_PATH_NODES,
)

# ============================================================================
# 局内存档
# ============================================================================
from .ingame_save_config import (
    SaveDataType,
    SaveScope,
    SaveVariableConfig,
    InGameSaveConfig,
)

# ============================================================================
# 音频与音乐
# ============================================================================
from .audio_music_configs import (
    BackgroundMusicConfig,
)

# ============================================================================
# 商店与经济
# ============================================================================
from .shop_economy_configs import (
    CurrencyConfig,
    CurrencyBackpackConfig,
    EquipmentDataConfig,
    ShopTemplateConfig,
)

# ============================================================================
# 局内存档管理
# ============================================================================
from .save_point_configs import (
    SavePointConfig,
)

# ============================================================================
# 实体布设组
# ============================================================================
from .deployment_configs import (
    EntityDeploymentGroupConfig,
)

# ============================================================================
# 标签与护盾
# ============================================================================
from .tag_shield_configs import (
    UnitTagConfig as TagShieldUnitTagConfig,  # 与basic_info重复，保留别名
    ShieldConfig,
    ScanTagConfig,
)

# ============================================================================
# 聊天配置
# ============================================================================
from .chat_configs import (
    ChatChannelConfig,
)

# ============================================================================
# 外围系统
# ============================================================================
from .peripheral_configs import (
    PeripheralSystemConfig,
)

# ============================================================================
# 光源
# ============================================================================
from .light_configs import (
    LightSourceConfig,
)

# ============================================================================
# 资源与多语言（从resource_language_configs拆分）
# ============================================================================
from .resource_language_configs import (
    MultiLanguageTextConfig,
)

# ============================================================================
# 关卡设置
# ============================================================================
from .level_settings_configs import (
    FactionConfig,
    SpawnPointConfig,
    RespawnPointConfig,
    PlayerGroupConfig,
    VictoryCondition,
    DefeatCondition,
    LevelSettingsConfig,
)

# ============================================================================
# 导出所有符号（供 from engine.configs.management import * 使用）
# 注意：不推荐使用通配导入，建议直接导入需要的类或使用模块前缀
# ============================================================================
__all__ = [
    # 计时器与变量
    'TimerManagementConfig',
    'LevelVariableConfig',
    # 基础信息
    'TransformConfig',
    'NativeCollisionConfig',
    'VisibilityConfig',
    'InitializationConfig',
    'CampConfig',
    'CampRelation',
    'ViewDetectionMode',
    'PresetStateIndex',
    'UnitTagDefinition',
    'UnitTagConfig',
    'PresetStateConfig',
    'MountPointConfig',
    'DecorationConfig',
    'LoadOptimizationGlobalConfig',
    'LoadOptimizationEntityConfig',
    'NodeGraphVariableConfig',
    'validate_transform_for_entity',
    'validate_preset_state_for_entity',
    'validate_unit_tags_for_entity',
    # 镜头与路径（使用别名）
    'CameraAndPathCameraMode',
    'CameraTransitionType',
    'CameraConfig',
    'PathType',
    'PathLoopMode',
    'PathPoint',
    'CameraPathGlobalPathConfig',
    'CameraPathPresetPointType',
    'CameraPathPresetPointConfig',
    'CAMERA_NODES',
    'PATH_NODES',
    'PRESET_POINT_NODES',
    'ALL_CAMERA_PATH_NODES',
    # 局内存档
    'SaveDataType',
    'SaveScope',
    'SaveVariableConfig',
    'InGameSaveConfig',
    # 音频与音乐
    'BackgroundMusicConfig',
    # 商店与经济
    'CurrencyConfig',
    'CurrencyBackpackConfig',
    'EquipmentDataConfig',
    'ShopTemplateConfig',
    # 局内存档管理
    'SavePointConfig',
    # 实体布设组
    'EntityDeploymentGroupConfig',
    # 标签与护盾
    'TagShieldUnitTagConfig',
    'ShieldConfig',
    'ScanTagConfig',
    # 聊天配置
    'ChatChannelConfig',
    # 外围系统
    'PeripheralSystemConfig',
    # 光源
    'LightSourceConfig',
    # 资源与多语言
    'MultiLanguageTextConfig',
    # 关卡设置
    'FactionConfig',
    'SpawnPointConfig',
    'RespawnPointConfig',
    'PlayerGroupConfig',
    'VictoryCondition',
    'DefeatCondition',
    'LevelSettingsConfig',
]

