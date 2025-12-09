from enum import Enum


class ResourceType(Enum):
    TEMPLATE = "元件库"
    INSTANCE = "实例"
    GRAPH = "节点图"

    # 战斗预设
    PLAYER_TEMPLATE = "战斗预设/玩家模板"
    PLAYER_CLASS = "战斗预设/职业"
    UNIT_STATUS = "战斗预设/单位状态"
    SKILL = "战斗预设/技能"
    PROJECTILE = "战斗预设/投射物"
    ITEM = "战斗预设/道具"

    # 管理配置
    TIMER = "管理配置/计时器"
    LEVEL_VARIABLE = "管理配置/关卡变量"
    PRESET_POINT = "管理配置/预设点"
    SKILL_RESOURCE = "管理配置/技能资源"
    CURRENCY_BACKPACK = "管理配置/货币背包"
    EQUIPMENT_DATA = "管理配置/装备数据"
    SHOP_TEMPLATE = "管理配置/商店模板"
    UI_LAYOUT = "管理配置/UI布局"
    UI_WIDGET_TEMPLATE = "管理配置/UI控件模板"
    MULTI_LANGUAGE = "管理配置/多语言"
    MAIN_CAMERA = "管理配置/主镜头"
    LIGHT_SOURCE = "管理配置/光源"
    BACKGROUND_MUSIC = "管理配置/背景音乐"
    PATH = "管理配置/路径"
    ENTITY_DEPLOYMENT_GROUP = "管理配置/实体布设组"
    UNIT_TAG = "管理配置/单位标签"
    SCAN_TAG = "管理配置/扫描标签"
    SHIELD = "管理配置/护盾"
    PERIPHERAL_SYSTEM = "管理配置/外围系统"
    SAVE_POINT = "管理配置/局内存档管理"
    CHAT_CHANNEL = "管理配置/聊天频道"
    LEVEL_SETTINGS = "管理配置/关卡设置"
    STRUCT_DEFINITION = "管理配置/结构体定义"
    SIGNAL = "管理配置/信号"

