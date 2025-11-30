"""实体类型定义和模板

本模块提供 UI 层需要的实体类型展示信息，实体规则以 `engine.configs.rules.entity_rules`
为单一事实来源。
"""

from typing import List, Dict
from engine.configs.rules.entity_rules import ENTITY_TYPES as ENTITY_RULES
from engine.configs.rules.component_rules import get_all_component_names

# UI 展示信息（图标、默认节点图等）
# 规则信息（allowed_components 等）从 entity_rules 获取，避免重复维护
ENTITY_UI_INFO = {
    "玩家": {
        "icon": "👤",
        "default_graphs": [],
    },
    "角色": {
        "icon": "🎭",
        "default_graphs": [],
    },
    "物件": {
        "icon": "🎮",
        "default_graphs": [],
    },
    "造物": {
        "icon": "🤖",
        "default_graphs": [],
    },
    "技能": {
        "icon": "⚔️",
        "default_graphs": ["技能逻辑"],
    },
    "UI控件": {
        "icon": "🖼️",
        "default_graphs": ["控件逻辑"],
    },
    "关卡": {
        "icon": "🗺️",
        "default_graphs": [],
    },
    "本地投射物": {
        "icon": "💥",
        "default_graphs": [],
    },
    # 元件库相关的扩展概念（用于分类展示）
    "元件组": {
        "icon": "🧩",
        "default_graphs": [],
    },
    "掉落物": {
        "icon": "💎",
        "default_graphs": [],
    },
}


def get_entity_type_info(entity_type: str) -> Dict:
    """获取实体类型的完整信息（UI + 规则）
    
    Args:
        entity_type: 实体类型名称
        
    Returns:
        包含 UI 信息和规则信息的字典
    """
    info = {
        "icon": ENTITY_UI_INFO.get(entity_type, {}).get("icon", "📦"),
        "default_graphs": ENTITY_UI_INFO.get(entity_type, {}).get("default_graphs", []),
    }
    
    # 从 entity_rules 获取规则信息
    if entity_type in ENTITY_RULES:
        rules = ENTITY_RULES[entity_type]
        info["description"] = rules.get("description", "")
        info["default_components"] = rules.get("allowed_components", [])
    else:
        info["description"] = ""
        info["default_components"] = []
    
    return info


# 变量类型定义（统一用于实体/模板自定义变量与节点图变量编辑器）
# 说明：
# - 文本均为“规范中文类型名”，与节点端口/结构体/节点图变量等数据类型体系保持一致；
# - 若后续需要支持新的基础类型或列表类型，应在此处补充，并同步 UI 与校验规则。
VARIABLE_TYPES = [
    "字符串",
    "字符串列表",
    "整数",
    "整数列表",
    "浮点数",
    "浮点数列表",
    "布尔值",
    "布尔值列表",
    "三维向量",
    "三维向量列表",
    "实体",
    "实体列表",
    "GUID",
    "GUID列表",
    "配置ID",
    "配置ID列表",
    "元件ID",
    "元件ID列表",
    "阵营",
    "阵营列表",
    "结构体",
    "结构体列表",
    "字典",
]

# 组件类型定义（由组件注册中心提供统一来源）
COMPONENT_TYPES = get_all_component_names()


def get_all_entity_types() -> List[str]:
    """获取所有实体类型（用于元件库新建，不包含关卡、UI控件和战斗预设专属类型）"""
    # 元件库新建时不应该包含：
    # 1. 关卡和UI控件（特殊用途）
    # 2. 战斗预设专属类型（角色、玩家、技能、本地投射物）
    excluded_types = {"关卡", "UI控件", "角色", "玩家", "技能", "本地投射物"}
    return [entity_type for entity_type in ENTITY_RULES.keys() 
            if entity_type not in excluded_types and not entity_type.startswith("物件-")]


def get_template_library_entity_types() -> List[str]:
    """获取元件库可用的实体类型（不包含战斗预设专属类型和特殊类型）"""
    # 元件库只显示：物件、造物
    # 不包含：
    # - 关卡：在实体摆放页面单独管理
    # - UI控件：在管理界面的界面控件组里管理
    # - 战斗预设专属类型：在战斗预设里管理
    template_library_types = {"物件", "造物"}
    return [
        entity_type
        for entity_type in ENTITY_RULES.keys()
        if entity_type in template_library_types
    ]


def get_template_library_category_types() -> List[str]:
    """
    获取元件库页面使用的分类类型。
    
    - 基础实体类型：物件、造物
    - 扩展概念：元件组、掉落物（仅用于分类展示，不作为实体类型参与校验）
    """
    base_types = list(get_template_library_entity_types())
    extra_categories = ["元件组", "掉落物"]
    return base_types + extra_categories


def get_combat_preset_entity_types() -> List[str]:
    """获取战斗预设专属的实体类型"""
    combat_types = {"角色", "玩家", "技能", "本地投射物"}
    return [entity_type for entity_type in ENTITY_RULES.keys() if entity_type in combat_types]


def get_all_entity_types_including_special() -> List[str]:
    """获取所有实体类型（包含关卡和UI控件，用于内部使用）
    
    注意：返回简化的实体类型列表，排除内部细分类型（如"物件-静态"、"物件-动态"），
    保留用户可见的类型名称。
    """
    # 排除内部细分类型（带"-"的类型名）
    return [entity_type for entity_type in ENTITY_RULES.keys() 
            if "-" not in entity_type]


def get_all_variable_types() -> List[str]:
    """获取所有变量类型"""
    return VARIABLE_TYPES


def get_all_component_types() -> List[str]:
    """获取所有组件类型"""
    return list(COMPONENT_TYPES)


