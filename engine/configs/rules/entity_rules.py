"""实体类型规则定义

基于内部实体与单位设计文档整理的实体类型规则
"""

ENTITY_TYPES = {
    "关卡": {
        "display_name": "关卡",
        "description": "纯逻辑实体，承载关卡逻辑",
        "reference": "关卡.md:1-38",
        
        # 变换信息
        "has_position": True,
        "has_rotation": False,  # 关卡.md:34 "关卡实体只有位置信息，没有旋转、缩放信息"
        "has_scale": False,
        
        # 物理特性
        "is_physical": False,  # 关卡.md:30-31 "关卡实体是一个纯逻辑实体"
        
        # 可用组件 (关卡.md:15-17)
        "allowed_components": [
            "自定义变量",
            "全局计时器"
        ],
        
        # 特殊事件 (关卡.md:25-28)
        "special_events": [
            "实体销毁时",  # 物件和敌人销毁时事件转发到关卡
            "实体移除/销毁时"
        ],
        
        # 生命周期 (关卡.md:36-37)
        "lifecycle": "随关卡初始化创建，随关卡销毁而销毁",
        
        # 其他特性
        "has_guid": True,
        "can_be_布设": True,
    },
    
    "角色": {
        "display_name": "角色",
        "description": "玩家实际控制的走跑爬飞单位，有物理实体",
        "reference": "角色.md:1-29",
        
        # 变换信息
        "has_position": True,
        "has_rotation": True,
        "has_scale": True,
        
        # 物理特性
        "is_physical": True,  # 角色.md:1 "有物理实体"
        
        # 可用组件 (角色.md:9-23)
        "allowed_components": [
            "碰撞触发器",
            "自定义变量",
            "全局计时器",
            "单位状态",
            "特效播放",
            "单位挂接点",
            "碰撞触发源",
            "背包",
            "战利品",
            "铭牌",
            "气泡",
            "装备栏",  # 角色.md:22-23 "仅角色可以添加的装备栏组件"
        ],
        
        # 特殊事件
        "special_events": [
            "角色倒下时",  # 角色.md:27 "角色实体上的节点图可以收到角色的实体销毁时事件"
            "角色复苏时",
            "实体销毁时",  # 角色特殊：可以收到自己的销毁事件
            "实体移除/销毁时",
        ],
        
        # 运行时特性 (角色.md:26)
        "has_guid": False,  # "角色在游戏过程中动态初始化，因此角色实体不具有对应的GUID"
        "can_be_布设": False,  # 动态创建
        "lifecycle": "根据模板配置动态初始化",
    },
    
    "物件-静态": {
        "display_name": "静态物件",
        "description": "纯表现向实体，不支持任何功能",
        "reference": "物件.md:8-10",
        
        # 变换信息
        "has_position": True,
        "has_rotation": True,
        "has_scale": True,
        
        # 物理特性
        "is_physical": False,
        
        # 物件.md:10 "不支持组件、节点图等任何功能"
        "allowed_components": [],
        "allowed_node_graphs": False,  # 静态物件不支持节点图
        
        "special_events": [],
        "has_guid": True,
        "can_be_布设": True,
    },
    
    "物件-动态": {
        "display_name": "动态物件",
        "description": "可配置预设状态的动态物件，遵循实体通用规则",
        "reference": "物件.md:12-14",
        
        # 变换信息
        "has_position": True,
        "has_rotation": True,
        "has_scale": True,
        
        # 物理特性
        "is_physical": True,
        
        # 可用组件 (需要从通用组件文档进一步确认)
        "allowed_components": [
            "碰撞触发器",
            "自定义变量",
            "定时器",
            "全局计时器",
            "单位状态",
            "特效播放",
            "自定义挂接点",
            "碰撞触发源",
            "背包",
            "战利品",
            "铭牌",
            "文本气泡",
        ],
        
        "special_events": [],
        "has_guid": True,
        "can_be_布设": True,
        "lifecycle": "遵循实体通用规则",
    },
    
    "本地投射物": {
        "display_name": "本地投射物",
        "description": "由本地计算和呈现投射物效果的实体",
        "reference": "本地投射物.md:1-62",
        
        # 变换信息
        "has_position": True,
        "has_rotation": True,
        "has_scale": True,
        
        # 物理特性
        "is_physical": True,
        
        # 本地投射物.md:45-55 特定组件
        "allowed_components": [
            "特效播放",  # 本地投射物.md:48-49
            "投射运动器",  # 本地投射物.md:51-52
            "命中检测",  # 本地投射物.md:54-55
        ],
        
        # 特殊配置 (本地投射物.md:18-44)
        "special_config": {
            "基础设置": {
                "模型配置": True,  # 本地投射物.md:21-23
                "xyz轴缩放": True,
            },
            "战斗参数": {
                "属性设置": ["继承自创建者", "独立设置"],  # 本地投射物.md:29
                "后续是否受创建者影响": "bool",  # 本地投射物.md:30
            },
            "生命周期设置": {
                "永久持续": "bool",  # 本地投射物.md:36
                "持续时长": "float",  # 本地投射物.md:37
                "XZ轴销毁距离": "float",  # 本地投射物.md:38
                "Y轴销毁距离": "float",  # 本地投射物.md:39
            },
            "生命周期结束行为": {
                "能力单元列表": []  # 本地投射物.md:41-43
            }
        },
        
        # 本地投射物.md:5 "需要在编辑时预先定义"
        "needs_predefinition": True,
        "has_guid": False,  # 动态创建
        "can_be_布设": False,
    },
    
    "玩家": {
        "display_name": "玩家",
        "description": "特殊的抽象实体，描述角色的从属概念",
        "reference": "玩家.md:1-40",
        
        # 玩家.md:34 "没有布设信息"
        "has_position": False,
        "has_rotation": False,
        "has_scale": False,
        
        # 玩家.md:31-32 "玩家实体是一个纯逻辑实体"
        "is_physical": False,
        
        # 玩家.md:21-24 可用组件
        "allowed_components": [
            "自定义变量",
            "全局计时器",
            "单位状态",
        ],
        
        "special_events": [
            "玩家传送完成时",
            "玩家所有角色倒下时",
            "玩家所有角色复苏时",
            "玩家异常倒下并复苏时",
        ],
        
        # 玩家.md:37-39 生命周期
        "lifecycle": "随关卡初始化创建，随关卡销毁而移除；用户退出时移除",
        "has_guid": False,
        "can_be_布设": False,
    },
    
    "造物": {
        "display_name": "造物",
        "description": "人型生物、元素生物等，可自主对敌对阵营做出反应",
        "reference": "造物.md:1-80",
        
        # 造物.md:28 "不支持空间X、Z轴的旋转，仅支持Y轴"
        "has_position": True,
        "has_rotation": "仅Y轴",  # 特殊：仅支持Y轴旋转
        "has_scale": True,
        
        # 物理特性
        "is_physical": True,
        
        # 造物.md:61-75 可用组件
        "allowed_components": [
            "选项卡",
            "碰撞触发器",
            "自定义变量",
            "全局计时器",
            "单位状态",
            "特效播放",
            "自定义挂接点",
            "碰撞触发源",
            "背包",
            "战利品",
            "铭牌",
            "文本气泡",
            "商店",
        ],
        
        # 造物.md:7 "依赖编辑时配置的行为模式"
        "requires_behavior_mode": True,
        
        # 造物.md:9 "默认携带和自身模型相等大小的受击盒"
        "has_default_hitbox": True,
        
        "special_events": [],
        "has_guid": True,
        "can_be_布设": True,
    },
    
    # 兼容性别名：物件（默认为动态物件）
    "物件": {
        "display_name": "物件（动态）",
        "description": "物件别名，默认为动态物件",
        "reference": "物件.md",
        "alias_of": "物件-动态",  # 标记为别名
        "has_position": True,
        "has_rotation": True,
        "has_scale": True,
        "is_physical": True,
        "allowed_components": [
            "碰撞触发器",
            "自定义变量",
            "定时器",
            "全局计时器",
            "单位状态",
            "特效播放",
            "自定义挂接点",
            "碰撞触发源",
            "背包",
            "战利品",
            "铭牌",
            "文本气泡",
        ],
        "special_events": [],
        "has_guid": True,
        "can_be_布设": True,
    },
    
    # UI控件（界面控件）
    "UI控件": {
        "display_name": "UI控件",
        "description": "界面控件，包括按钮、文本框、计时器等",
        "reference": "概念介绍/资产/界面控件/",
        "has_position": False,  # UI控件使用界面坐标系
        "has_rotation": False,
        "has_scale": False,
        "is_physical": False,
        "allowed_components": [],  # UI控件有专门的配置，不使用通用组件
        "special_events": [],
        "has_guid": True,
        "can_be_布设": False,  # 在界面编辑器中配置，不在场景中布设
        "is_ui_element": True,
    },
    
    # 技能（注意：技能不是实体，而是配置资源）
    "技能": {
        "display_name": "技能",
        "description": "技能配置，在战斗预设页签中定义",
        "reference": "技能.md:1-155",
        "is_config_resource": True,  # 标记为配置资源，不是实体
        "has_position": False,
        "has_rotation": False,
        "has_scale": False,
        "is_physical": False,
        "allowed_components": [],  # 技能不使用组件，有自己的配置体系
        "allowed_node_graphs": True,  # 技能有技能节点图
        "special_config": {
            "技能类型": ["瞬发技能", "长按技能", "普通技能", "连段技能", "瞄准技能"],
            "冷却时间": "float",
            "使用次数": "int",
            "消耗": "技能资源",
        },
        "special_events": [],
        "has_guid": False,
        "can_be_布设": False,
    },
}


def normalize_entity_type(entity_type: str) -> str:
    """规范化实体类型名称
    
    将别名转换为标准名称，例如 "物件" -> "物件-动态"
    """
    # "物件"是"物件-动态"的别名
    if entity_type == "物件":
        return "物件-动态"
    return entity_type


def get_entity_allowed_components(entity_type: str) -> list:
    """获取实体类型允许的组件列表"""
    # 规范化实体类型
    normalized_type = normalize_entity_type(entity_type)
    
    if normalized_type in ENTITY_TYPES:
        return ENTITY_TYPES[normalized_type].get("allowed_components", [])
    return []


def can_entity_have_node_graphs(entity_type: str) -> bool:
    """检查实体类型是否支持节点图"""
    if entity_type in ENTITY_TYPES:
        # 静态物件明确不支持节点图
        return ENTITY_TYPES[entity_type].get("allowed_node_graphs", True) != False
    return True


def validate_entity_transform(
    entity_type: str,
    *,
    has_rotation: bool = False,
    has_scale: bool = False,
    has_position: bool = False,
) -> list:
    """验证实体的变换信息是否合法
    
    Returns:
        list: 错误信息列表，为空表示无错误
    """
    errors = []
    if entity_type not in ENTITY_TYPES:
        return [f"未知的实体类型: {entity_type}"]
    
    rules = ENTITY_TYPES[entity_type]
    
    if has_rotation and not rules.get("has_rotation"):
        errors.append(
            f"实体类型'{entity_type}'不支持旋转信息\n"
            f"参考: {rules.get('reference')}"
        )
    
    if has_scale and not rules.get("has_scale"):
        errors.append(
            f"实体类型'{entity_type}'不支持缩放信息\n"
            f"参考: {rules.get('reference')}"
        )
    if has_position and not rules.get("has_position"):
        errors.append(
            f"实体类型'{entity_type}'不应该包含位置信息\n"
            f"参考: {rules.get('reference')}"
        )
    
    return errors

