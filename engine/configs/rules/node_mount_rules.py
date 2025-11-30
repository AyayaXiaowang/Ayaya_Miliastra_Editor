"""节点挂载规则定义

基于内部节点挂载规则文档整理的挂载限制说明
"""

# 节点挂载实体限制规则
# 基于事件节点.md逐个提取每个事件的挂载限制
NODE_ENTITY_RESTRICTIONS = {
    # ========== 实体相关事件 (事件节点.md:48-103) ==========
    
    "实体创建时": {
        "allowed_entities": ["所有实体"],  # 事件节点.md:67 "所有类型的实体均可以触发该事件"
        "reason": "实体被创建时触发该事件。所有类型的实体均可以触发该事件",
        "line_ref": "事件节点.md:64-73",
        "description": "关卡实体、角色实体和玩家实体会在进入关卡时触发该事件"
    },
    
    "实体销毁时": {
        "allowed_entities": ["关卡"],  # 事件节点.md:77 "该事件仅在关卡实体上可以触发"
        "reason": "关卡内任意实体被销毁时触发该事件，该事件仅在关卡实体上可以触发",
        "line_ref": "事件节点.md:75-92",
        "description": "任意类型的实体销毁均可以触发该事件，包括角色实体被击倒。仅包含因战斗或【销毁实体】节点而造成的销毁"
    },
    
    "实体移除/销毁时": {
        "allowed_entities": ["关卡"],  # 事件节点.md:96 "该事件仅在关卡实体上可以触发"
        "reason": "关卡内任意实体被移除或销毁时触发该事件，该事件仅在关卡实体上可以触发",
        "line_ref": "事件节点.md:94-103",
        "description": "实体被销毁或被移除均会触发该事件。因此实体被销毁时，会依次触发【实体销毁时】以及【实体移除/销毁时】事件"
    },
    
    # ========== 玩家与角色相关事件 (事件节点.md:118-178) ==========
    
    "角色倒下时": {
        "allowed_entities": ["角色"],  # 事件节点.md:122 "角色实体上的节点图可以触发该事件"
        "reason": "角色倒下时，角色实体上的节点图可以触发该事件",
        "line_ref": "事件节点.md:120-129",
    },
    
    "角色复苏时": {
        "allowed_entities": ["角色"],  # 事件节点.md:133 "角色实体上的的节点图可以触发该事件"
        "reason": "角色复苏时，角色实体上的的节点图可以触发该事件",
        "line_ref": "事件节点.md:131-138",
    },
    
    "玩家传送完成时": {
        "allowed_entities": ["玩家"],  # 事件节点.md:142 "在玩家实体的节点图上可以触发该事件"
        "reason": "玩家传送完成时，在玩家实体的节点图上可以触发该事件",
        "line_ref": "事件节点.md:140-149",
        "description": "玩家首次进入关卡时，也会触发该事件"
    },
    
    "玩家所有角色倒下时": {
        "allowed_entities": ["玩家"],  # 事件节点.md:153 "玩家实体的节点图上触发该事件"
        "reason": "玩家的所有角色实体均倒下时，玩家实体的节点图上触发该事件",
        "line_ref": "事件节点.md:151-159",
    },
    
    "玩家所有角色复苏时": {
        "allowed_entities": ["玩家"],  # 事件节点.md:163 "玩家实体的节点图触发该事件"
        "reason": "玩家的所有角色均复苏时，玩家实体的节点图触发该事件",
        "line_ref": "事件节点.md:161-168",
    },
    
    "玩家异常倒下并复苏时": {
        "allowed_entities": ["玩家"],  # 事件节点.md:172 "玩家实体上触发该事件"
        "reason": "角色因溺水、坠入深渊等原因倒下并复苏时，玩家实体上触发该事件",
        "line_ref": "事件节点.md:170-177",
    },
    
    # ========== 碰撞触发器事件 ==========
    
    "进入碰撞触发器时": {
        "allowed_entities": ["所有带碰撞触发器组件的实体"],
        "reason": "实体进入碰撞触发器范围时触发，在配置碰撞触发器的实体上触发",
        "line_ref": "事件节点.md:179-194",
    },
    
    "离开碰撞触发器时": {
        "allowed_entities": ["所有带碰撞触发器组件的实体"],
        "reason": "实体离开碰撞触发器范围时触发，在配置碰撞触发器的实体上触发",
        "line_ref": "事件节点.md:195-210",
    },
    
    # ========== 定时器和全局计时器事件 ==========
    
    "定时器到时": {
        "allowed_entities": ["所有带定时器组件的实体"],
        "reason": "定时器组件配置的定时器到时触发该事件",
        "line_ref": "事件节点.md:211-223",
    },
    
    "全局计时器到时": {
        "allowed_entities": ["所有带全局计时器组件的实体"],
        "reason": "全局计时器组件配置的定时器到时触发该事件",
        "line_ref": "事件节点.md:224-236",
    },
    
    # ========== 命中检测事件 ==========
    
    "命中检测触发时": {
        "allowed_entities": ["所有带命中检测组件的实体"],
        "reason": "命中检测触发时，在配置命中检测组件的实体上触发该事件",
        "line_ref": "事件节点.md:237-256",
    },
    
    # ========== 角色移动速度事件 ==========
    
    "角色移动速度达到条件时": {
        "allowed_entities": ["角色"],
        "reason": "为角色实体添加单位状态效果【监听移动速率】，达成条件会触发该事件",
        "line_ref": "事件节点.md:50-62",
    },
}


# 节点类型定义 (基于基础概念.md:36-44)
NODE_TYPES = {
    "事件节点": {
        "has_logic_in": False,
        "has_logic_out": True,
        "has_param_in": False,
        "has_param_out": True,
        "description": "节点图执行流的起始节点，描述游戏中发生的事件",
        "reference": "基础概念.md:41"
    },
    "执行节点": {
        "has_logic_in": True,
        "has_logic_out": True,
        "has_param_in": True,
        "has_param_out": True,
        "description": "执行特定功能，产生实际影响游戏运行的效果",
        "reference": "基础概念.md:40"
    },
    "流程控制节点": {
        "has_logic_in": "多个",
        "has_logic_out": "多个",
        "has_param_in": True,
        "has_param_out": True,
        "description": "影响执行流流程的节点，包括多个逻辑出引脚",
        "reference": "基础概念.md:42"
    },
    "运算节点": {
        "has_logic_in": False,
        "has_logic_out": False,
        "has_param_in": True,
        "has_param_out": True,
        "description": "描述运算行为的节点，仅可在运算流中使用",
        "reference": "基础概念.md:43"
    },
    "查询节点": {
        "has_logic_in": False,
        "has_logic_out": False,
        "has_param_in": "可能有",
        "has_param_out": True,
        "description": "描述查询行为的节点，仅可在运算流中使用",
        "reference": "基础概念.md:44"
    },
}


def can_node_mount_on_entity(node_name: str, entity_type: str) -> tuple[bool, str]:
    """检查节点是否可以挂载到指定实体类型
    
    Args:
        node_name: 节点名称
        entity_type: 实体类型
        
    Returns:
        (是否可以挂载, 错误信息)
    """
    if node_name not in NODE_ENTITY_RESTRICTIONS:
        # 节点不在限制列表中，表示没有特殊限制
        return True, ""
    
    restriction = NODE_ENTITY_RESTRICTIONS[node_name]
    allowed = restriction["allowed_entities"]
    
    # 检查是否允许所有实体
    if "所有实体" in allowed:
        return True, ""
    
    # 检查是否允许所有带特定组件的实体
    if allowed[0].startswith("所有带") and allowed[0].endswith("的实体"):
        # 这种情况需要检查实体是否有对应组件，暂时返回True
        return True, ""
    
    # 检查具体实体类型
    if entity_type in allowed:
        return True, ""
    
    # 不允许挂载
    error_msg = (
        f"节点'{node_name}'只能挂载在以下实体类型：{', '.join(allowed)}\n"
        f"当前实体类型：{entity_type}\n"
        f"原因：{restriction['reason']}\n"
        f"参考：{restriction['line_ref']}"
    )
    return False, error_msg


