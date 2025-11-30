"""
完整的实体规则定义系统 - 基于知识库文档
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class EntityType(str, Enum):
    """实体类型枚举"""
    LEVEL = "关卡"
    CHARACTER = "角色"
    OBJECT_STATIC = "物件-静态"
    OBJECT_DYNAMIC = "物件-动态"
    PROJECTILE = "本地投射物"
    PLAYER = "玩家"
    CREATURE = "造物"
    UI_WIDGET = "UI控件"
    SKILL = "技能"


@dataclass
class EntityRules:
    """实体规则定义"""
    entity_type: str
    description: str
    
    # 变换信息
    has_position: bool = True
    has_rotation: bool = True
    has_scale: bool = True
    
    # 物理特性
    is_physical: bool = True
    has_guid: bool = True
    
    # 允许的组件
    allowed_components: List[str] = field(default_factory=list)
    
    # 特殊事件
    special_events: List[str] = field(default_factory=list)
    
    # 生命周期
    lifecycle_notes: str = ""
    
    # 文档引用
    doc_reference: str = ""
    
    # 其他特性
    extra_features: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 实体规则定义（基于知识库文档）
# ============================================================================

ENTITY_RULES_DB = {
    # 关卡实体 - 基于 关卡.md
    EntityType.LEVEL: EntityRules(
        entity_type="关卡",
        description="纯逻辑实体，承载关卡逻辑",
        has_position=True,
        has_rotation=False,  # 关卡.md:34 "只有位置信息，没有旋转、缩放信息"
        has_scale=False,
        is_physical=False,  # 关卡.md:30-31 "无物理实体，是一个纯逻辑实体"
        has_guid=True,
        allowed_components=[
            "自定义变量",  # 关卡.md:16
            "全局计时器",  # 关卡.md:17
        ],
        special_events=[
            "实体销毁时",  # 关卡.md:26-28
            "实体移除/销毁时",  # 关卡.md:26-28
        ],
        lifecycle_notes="随关卡初始化创建，随关卡销毁而销毁",  # 关卡.md:36-37
        doc_reference="关卡.md",
        extra_features={
            "auto_create": True,  # 关卡.md:4 "新建一个关卡后会自动创建"
            "receives_entity_destroy_events": True,  # 物件和敌人销毁时转发到关卡
        }
    ),
    
    # 角色实体 - 基于 角色.md
    EntityType.CHARACTER: EntityRules(
        entity_type="角色",
        description="玩家实际控制的走跑爬飞单位，有物理实体",
        has_position=True,
        has_rotation=True,
        has_scale=True,
        is_physical=True,  # 角色.md:1 "有物理实体"
        has_guid=False,  # 角色.md:26 "动态初始化，因此不具有对应的GUID"
        allowed_components=[
            "碰撞触发器",  # 角色.md:10
            "自定义变量",  # 角色.md:11
            "全局计时器",  # 角色.md:12
            "单位状态",  # 角色.md:13
            "特效播放",  # 角色.md:14
            "单位挂接点",  # 角色.md:15
            "碰撞触发源",  # 角色.md:16
            "音效播放器",  # 角色.md:17
            "背包",  # 角色.md:18
            "战利品",  # 角色.md:19
            "铭牌",  # 角色.md:20
            "气泡",  # 角色.md:21
            "装备栏",  # 角色.md:22-23 "仅角色可以添加"
        ],
        special_events=[
            "角色倒下时",
            "角色复苏时",
            "实体销毁时",  # 角色.md:27 "生命值归零时可收到实体销毁时事件"
            "实体移除/销毁时",  # 角色.md:27
        ],
        lifecycle_notes="运行时根据模板配置动态初始化",  # 角色.md:26
        doc_reference="角色.md",
        extra_features={
            "health_zero_event": True,  # 生命值归零时特殊处理
            "player_controlled": True,  # 玩家实际控制的单位
            "online_remove_event": True,  # 角色.md:28 "玩家返回大厅，关卡收到移除事件"
        }
    ),
    
    # 静态物件 - 基于 物件.md
    EntityType.OBJECT_STATIC: EntityRules(
        entity_type="物件-静态",
        description="纯表现向实体，用于环境、氛围表现",
        has_position=True,
        has_rotation=True,
        has_scale=True,
        is_physical=True,
        has_guid=True,
        allowed_components=[],  # 物件.md:10 "不支持组件、节点图等任何功能"
        special_events=[],
        lifecycle_notes="静态物件无动态功能",
        doc_reference="物件.md:8-10",
        extra_features={
            "no_components": True,  # 完全不支持组件
            "no_node_graphs": True,  # 完全不支持节点图
            "visual_only": True,  # 纯视觉表现
        }
    ),
    
    # 动态物件 - 基于 物件.md
    EntityType.OBJECT_DYNAMIC: EntityRules(
        entity_type="物件-动态",
        description="运行时可根据配置呈现不同动画表现的物件",
        has_position=True,
        has_rotation=True,
        has_scale=True,
        is_physical=True,
        has_guid=True,
        allowed_components=[
            # 物件.md:29-31 "部分物件会默认携带一些自身常用的组件"
            # 根据通用组件文档，动态物件可以使用大部分组件
            "自定义变量",
            "全局计时器",
            "定时器",
            "碰撞触发器",
            "碰撞触发源",
            "特效播放",
            "运动器",
            "战利品",
            "铭牌",
            "气泡",
        ],
        special_events=[
            # 物件.md:27 "物件销毁时，事件会被推送到关卡实体上"
            # 所以物件自身不接收销毁事件
        ],
        lifecycle_notes="可配置预设状态，呈现不同动画",  # 物件.md:13
        doc_reference="物件.md:12-14",
        extra_features={
            "has_preset_states": True,  # 预设状态系统
            "can_move_with_motor": True,  # 物件.md:4 "可通过挂载运动器组件移动"
            "destroy_event_to_level": True,  # 销毁事件转发到关卡
            "has_basic_info": True,  # 物件.md:19-22 有完整的基础信息
            "has_specialized_config": True,  # 物件.md:24-26 有特化配置
        }
    ),
    
    # 玩家实体
    EntityType.PLAYER: EntityRules(
        entity_type="玩家",
        description="玩家实体，区别于角色实体",
        has_position=True,
        has_rotation=False,
        has_scale=False,
        is_physical=False,
        has_guid=True,
        allowed_components=[
            "自定义变量",
            "全局计时器",
        ],
        special_events=[
            "玩家传送完成时",
            "玩家所有角色倒下时",
            "玩家所有角色复苏时",
        ],
        lifecycle_notes="玩家实体与角色实体一一对应（超限模式）",
        doc_reference="玩家.md",
        extra_features={
            "has_character": True,
            "revive_system": True,
        }
    ),
    
    # 本地投射物
    EntityType.PROJECTILE: EntityRules(
        entity_type="本地投射物",
        description="投射物实体，用于技能弹道等",
        has_position=True,
        has_rotation=True,
        has_scale=True,
        is_physical=True,
        has_guid=False,
        allowed_components=[
            "特效播放",
            "投射运动器",
            "命中检测",
        ],
        special_events=[],
        lifecycle_notes="动态创建，有生命周期设置",
        doc_reference="本地投射物.md",
        extra_features={
            "has_lifetime": True,
            "has_combat_params": True,
        }
    ),
    
    # 造物实体
    EntityType.CREATURE: EntityRules(
        entity_type="造物",
        description="造物实体，有AI行为",
        has_position=True,
        has_rotation=True,
        has_scale=True,
        is_physical=True,
        has_guid=True,
        allowed_components=[
            "自定义变量",
            "全局计时器",
            "单位状态",
            "特效播放",
            "碰撞触发器",
            "碰撞触发源",
            "战利品",
            "背包",
            "铭牌",
        ],
        special_events=[
            "造物倒下时",
            "造物复苏时",
        ],
        lifecycle_notes="有AI行为系统和仇恨系统",
        doc_reference="造物.md",
        extra_features={
            "has_ai": True,
            "has_aggro_system": True,
        }
    ),
}


# ============================================================================
# 验证函数
# ============================================================================

def validate_entity_transform(entity_type: EntityType, transform_data: dict) -> List[str]:
    """验证实体的变换信息"""
    rules = ENTITY_RULES_DB.get(entity_type)
    if not rules:
        return [f"未知实体类型: {entity_type}"]
    
    errors = []
    
    if not rules.has_rotation and "rotation" in transform_data:
        errors.append(
            f"[变换错误] 实体类型'{rules.entity_type}'不支持旋转信息\n"
            f"参考：{rules.doc_reference}"
        )
    
    if not rules.has_scale and "scale" in transform_data:
        errors.append(
            f"[变换错误] 实体类型'{rules.entity_type}'不支持缩放信息\n"
            f"参考：{rules.doc_reference}"
        )
    
    return errors


def validate_entity_components(entity_type: EntityType, components: List[str]) -> List[str]:
    """验证实体的组件"""
    rules = ENTITY_RULES_DB.get(entity_type)
    if not rules:
        return [f"未知实体类型: {entity_type}"]
    
    errors = []
    
    # 静态物件完全不支持组件
    if rules.extra_features.get("no_components") and components:
        errors.append(
            f"[组件错误] 实体类型'{rules.entity_type}'不支持任何组件\n"
            f"当前尝试添加的组件：{', '.join(components)}\n"
            f"参考：{rules.doc_reference} - 静态物件不支持组件、节点图等任何功能"
        )
        return errors
    
    # 检查组件是否在允许列表中
    for component in components:
        if component not in rules.allowed_components:
            errors.append(
                f"[组件错误] 组件'{component}'不能添加到实体类型'{rules.entity_type}'上\n"
                f"允许的组件：{', '.join(rules.allowed_components)}\n"
                f"参考：{rules.doc_reference}"
            )
    
    return errors


def validate_entity_event(entity_type: EntityType, event_name: str) -> List[str]:
    """验证实体是否可以接收特定事件"""
    rules = ENTITY_RULES_DB.get(entity_type)
    if not rules:
        return [f"未知实体类型: {entity_type}"]
    
    errors = []
    
    # 检查特殊事件
    if event_name in ["实体销毁时", "实体移除/销毁时"]:
        if event_name in rules.special_events:
            return []  # 允许
        elif entity_type == EntityType.OBJECT_DYNAMIC:
            errors.append(
                f"[事件错误] 物件实体不接收'{event_name}'事件\n"
                f"该事件会被转发到关卡实体上处理\n"
                f"参考：角色.md:27 和 关卡.md:26-28"
            )
    
    return errors


if __name__ == "__main__":
    print("=== 实体规则系统测试 ===\n")
    
    # 测试关卡实体
    print("1. 关卡实体规则：")
    level_rules = ENTITY_RULES_DB[EntityType.LEVEL]
    print(f"   类型: {level_rules.entity_type}")
    print(f"   描述: {level_rules.description}")
    print(f"   变换: 位置={level_rules.has_position}, 旋转={level_rules.has_rotation}, 缩放={level_rules.has_scale}")
    print(f"   允许组件: {', '.join(level_rules.allowed_components)}")
    print(f"   特殊事件: {', '.join(level_rules.special_events)}")
    
    # 测试验证
    print("\n2. 验证测试：")
    errors = validate_entity_components(EntityType.OBJECT_STATIC, ["自定义变量", "碰撞触发器"])
    if errors:
        print("   发现错误：")
        for err in errors:
            print(f"   {err}")
    
    print("\n3. 所有实体类型概览：")
    for etype, rules in ENTITY_RULES_DB.items():
        print(f"   - {rules.entity_type}: {rules.description}")

