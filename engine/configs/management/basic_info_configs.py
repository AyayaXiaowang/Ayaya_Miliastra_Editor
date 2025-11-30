"""
基础信息配置系统
基于知识库文档实现
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


# ============================================================================
# 变换配置 (变化、原生碰撞、可见性和初始化.md)
# ============================================================================

@dataclass
class TransformConfig:
    """
    变换配置 - 描述单位在场景中的几何信息
    参考：变化、原生碰撞、可见性和初始化.md:1-11
    """
    position: tuple = (0.0, 0.0, 0.0)  # 世界坐标系下的位置
    rotation: tuple = (0.0, 0.0, 0.0)  # 世界坐标系下的旋转
    scale: tuple = (1.0, 1.0, 1.0)     # 放大倍率
    lock_transform: bool = False  # 编辑时属性，锁定后无法修改
    
    doc_reference: str = "变化、原生碰撞、可见性和初始化.md:1-9"


@dataclass
class NativeCollisionConfig:
    """
    原生碰撞配置 - 物件的基础碰撞
    参考：变化、原生碰撞、可见性和初始化.md:13-24
    """
    enabled_on_init: bool = True  # 初始化时碰撞是否生效
    is_climbable: bool = False    # 是否可攀爬（需要角色有攀爬能力）
    preview_collision: bool = False  # 编辑时预览碰撞外形
    
    doc_reference: str = "变化、原生碰撞、可见性和初始化.md:15-20"
    notes: str = "原生碰撞作为基础信息，其形状无法被修改"


@dataclass
class VisibilityConfig:
    """
    可见性配置 - 实体模型是否可见
    参考：变化、原生碰撞、可见性和初始化.md:26-32
    """
    visible: bool = True  # 模型是否可见
    
    doc_reference: str = "变化、原生碰撞、可见性和初始化.md:28-29"
    notes: str = "仅影响模型，不影响碰撞、触发器、节点图等其他逻辑"


@dataclass
class InitializationConfig:
    """
    初始化配置 - 关卡初始化时是否创建实体
    参考：变化、原生碰撞、可见性和初始化.md:34-41
    """
    create_on_init: bool = True  # 关卡初始化时是否创建
    
    doc_reference: str = "变化、原生碰撞、可见性和初始化.md:36-37"
    notes: str = "若关闭，需通过节点图动态创建"


# ============================================================================
# 阵营配置 (阵营.md)
# ============================================================================

@dataclass
class CampConfig:
    """
    阵营配置 - 为对抗性玩法将实体划分为不同群体
    参考：阵营.md
    """
    camp_id: int  # 阵营ID
    camp_name: str  # 阵营名称
    default_players: List[str] = field(default_factory=list)  # 初始包含的玩家
    default_entities: List[str] = field(default_factory=list)  # 初始包含的物件和造物
    
    # 阵营关系（单向）
    hostile_camps: List[int] = field(default_factory=list)  # 敌对阵营列表
    friendly_camps: List[int] = field(default_factory=list)  # 友善阵营列表
    
    doc_reference: str = "阵营.md"
    notes: str = "阵营关系是单向的，A对B敌对不代表B对A敌对"


class CampRelation(str, Enum):
    """阵营关系类型"""
    HOSTILE = "敌对"
    FRIENDLY = "友善"


# ============================================================================
# 单位标签配置 (单位标签.md)
# ============================================================================

@dataclass
class UnitTagDefinition:
    """
    单位标签定义 - 全局定义的标签
    参考：单位标签.md:1-21
    """
    tag_index: int  # 唯一标识，用于节点图内标识
    tag_name: str   # 标签名称，起提示作用
    
    doc_reference: str = "单位标签.md:19"
    applicable_entity_types: List[str] = field(default_factory=lambda: [
        "造物", "角色", "物件"  # 单位标签.md:2 "拥有物理实体的单位类型"
    ])


@dataclass
class UnitTagConfig:
    """
    实体上的单位标签配置
    参考：单位标签.md:22-23
    """
    tags: List[int] = field(default_factory=list)  # 标签索引列表
    
    doc_reference: str = "单位标签.md:23"
    notes: str = "一个实体可以同时具备多个标签"


# ============================================================================
# 模型配置 (模型.md)
# ============================================================================

class PresetStateIndex(int, Enum):
    """预设状态索引 - 每组状态代表一种动画状态"""
    # 具体值由模型资产定义


@dataclass
class PresetStateConfig:
    """
    预设状态配置 - 物件的独有属性
    参考：模型.md:4-23
    """
    state_index: int  # 预设状态索引（如宝箱的开关状态组）
    state_value: int  # 当前状态值（如0=关闭，1=打开）
    
    doc_reference: str = "模型.md:10-18"
    notes: str = "每组状态索引下的所有子状态都是互斥的且可相互切换"
    entity_type_restriction: str = "仅物件可用"


@dataclass
class MountPointConfig:
    """
    单位挂接点配置
    参考：模型.md:25-34
    """
    mount_point_name: str  # 挂接点名称
    position: tuple  # 位置
    
    doc_reference: str = "模型.md:26-31"
    notes: str = "每个实体都有默认的'中心原点'挂点；造物和角色有骨骼挂点"


@dataclass
class DecorationConfig:
    """
    装饰物配置 - 在元件/实体上挂接静态物件模型
    参考：模型.md:36-63
    """
    model_asset_id: str  # 装饰物模型资产ID
    attached_mount_point: str  # 附着的挂接点
    relative_transform: TransformConfig  # 相对挂接点的变换
    native_collision: NativeCollisionConfig  # 碰撞配置
    
    doc_reference: str = "模型.md:56-62"
    notes: str = "装饰物配置不会导致元件或实体数量增减"


# ============================================================================
# 负载优化配置 (负载优化.md)
# ============================================================================

class ViewDetectionMode(str, Enum):
    """视野检测模式"""
    FOLLOW_ENTITY_CONFIG = "跟随实体配置"  # 依据元件/实体上的属性配置
    DISABLED = "关闭"  # 关闭视野检测优化


@dataclass
class LoadOptimizationGlobalConfig:
    """
    负载优化全局配置
    参考：负载优化.md:7-11
    """
    view_detection_mode: ViewDetectionMode = ViewDetectionMode.FOLLOW_ENTITY_CONFIG
    grid_size: float = 40.0  # 网格大小（米）超限模式下为40m*40m
    view_range_grids: int = 3  # 视野范围（格数）周围3格
    
    doc_reference: str = "负载优化.md:38-43"


@dataclass
class LoadOptimizationEntityConfig:
    """
    实体的负载优化配置
    参考：负载优化.md:13-14
    """
    enable_optimization: bool = False  # 是否启用负载优化
    
    doc_reference: str = "负载优化.md:14"
    notes: str = "开启后，该物件可能在距离角色过远时在本地销毁（逻辑仍存在）"


# ============================================================================
# 节点图变量配置 (节点图变量.md)
# ============================================================================

@dataclass
class NodeGraphVariableConfig:
    """
    节点图变量配置
    参考：节点图变量.md
    """
    variable_name: str
    variable_type: str  # 数据类型
    default_value: Any = None
    is_exposed_to_level: bool = False  # 是否暴露到关卡层
    
    doc_reference: str = "节点图变量.md:8-9"
    lifecycle: str = "跟随节点图"
    scope: str = "仅在定义该变量的节点图内可访问"
    notes: str = "与自定义变量的区别：生命周期跟随节点图，作用域仅限节点图内"


# ============================================================================
# 验证函数
# ============================================================================

def validate_transform_for_entity(entity_type: str, transform: TransformConfig) -> List[str]:
    """验证实体的变换配置是否合法"""
    errors = []
    
    # 关卡实体不支持旋转和缩放 (关卡.md:34)
    if entity_type == "关卡":
        if transform.rotation != (0.0, 0.0, 0.0):
            errors.append(
                "[变换错误] 关卡实体不支持旋转信息\n"
                "参考：关卡.md:34 '只有位置信息，没有旋转、缩放信息'"
            )
        if transform.scale != (1.0, 1.0, 1.0):
            errors.append(
                "[变换错误] 关卡实体不支持缩放信息\n"
                "参考：关卡.md:34"
            )
    
    return errors


def validate_preset_state_for_entity(entity_type: str) -> List[str]:
    """验证预设状态是否可用"""
    errors = []
    
    # 只有物件可以使用预设状态 (模型.md:5)
    if entity_type not in ["物件-动态"]:
        errors.append(
            "[预设状态错误] 预设状态是物件的独有属性\n"
            f"当前实体类型：{entity_type}\n"
            "参考：模型.md:5 '预设状态是物件的独有属性'"
        )
    
    return errors


def validate_unit_tags_for_entity(entity_type: str) -> List[str]:
    """验证单位标签是否可用"""
    errors = []
    
    # 只有拥有物理实体的单位可以使用 (单位标签.md:2)
    allowed_types = ["造物", "角色", "物件-动态"]
    if entity_type not in allowed_types:
        errors.append(
            "[单位标签错误] 单位标签仅适用于拥有物理实体的单位\n"
            f"当前实体类型：{entity_type}\n"
            f"允许的类型：{', '.join(allowed_types)}\n"
            "参考：单位标签.md:2"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 基础信息配置系统测试 ===\n")
    
    # 测试变换配置
    print("1. 关卡实体变换验证：")
    level_transform = TransformConfig(
        position=(100.0, 0.0, 100.0),
        rotation=(0.0, 45.0, 0.0),  # 不允许旋转
        scale=(2.0, 2.0, 2.0)       # 不允许缩放
    )
    errors = validate_transform_for_entity("关卡", level_transform)
    if errors:
        for err in errors:
            print(f"   {err}")
    
    # 测试阵营配置
    print("\n2. 阵营配置示例：")
    camp = CampConfig(
        camp_id=1,
        camp_name="玩家阵营",
        default_players=["player_1", "player_2"],
        hostile_camps=[2, 3],
        friendly_camps=[1]
    )
    print(f"   阵营名称：{camp.camp_name}")
    print(f"   敌对阵营：{camp.hostile_camps}")
    
    # 测试单位标签
    print("\n3. 单位标签验证：")
    errors = validate_unit_tags_for_entity("关卡")  # 关卡没有物理实体
    if errors:
        for err in errors:
            print(f"   {err}")
    
    print("\n✅ 基础信息配置系统测试完成")
