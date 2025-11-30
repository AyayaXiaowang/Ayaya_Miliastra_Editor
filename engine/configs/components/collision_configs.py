"""
组件配置 - 碰撞
基于知识库文档定义的碰撞相关组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class TriggerShape(Enum):
    """触发区形状（碰撞触发器.md 第49行，碰撞触发源.md 第26行）"""
    CUBOID = "长方体"
    SPHERE = "球体"
    CAPSULE = "胶囊体"


class CollisionTargetType(Enum):
    """碰撞检测目标类型（碰撞触发器.md 第42行）"""
    CHARACTER = "角色"
    OBJECT = "物件"
    CREATURE = "造物"


@dataclass
class TriggerArea:
    """
    触发区域配置
    来源：碰撞触发器.md (第44-52行)
    """
    # 触发区形状
    shape: TriggerShape = TriggerShape.CUBOID
    # 中心（相对实体/元件中心的偏移）
    center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 缩放倍率
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "触发区形状": self.shape.value,
            "中心": self.center,
            "旋转": self.rotation,
            "缩放倍率": self.scale
        }


@dataclass
class CollisionTriggerDefinition:
    """
    单个碰撞触发器定义
    来源：碰撞触发器.md (第37-52行)
    """
    # 触发器序号
    trigger_index: int
    # 初始生效
    initially_active: bool = True
    # 生效目标（仅对配置的实体类型进行检测）
    target_types: List[CollisionTargetType] = field(default_factory=list)
    # 触发区列表（多个触发区会取并集）
    trigger_areas: List[TriggerArea] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "触发器序号": self.trigger_index,
            "初始生效": self.initially_active,
            "生效目标": [t.value for t in self.target_types],
            "触发区": [area.to_dict() for area in self.trigger_areas]
        }


@dataclass
class CollisionTriggerConfig:
    """
    碰撞触发器组件配置
    来源：碰撞触发器.md (第22-52行)
    """
    # 初始生效触发器列表
    initially_active_triggers: List[int] = field(default_factory=list)
    # 所有触发器定义
    triggers: List[CollisionTriggerDefinition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "初始生效触发器": self.initially_active_triggers,
            "触发器列表": [t.to_dict() for t in self.triggers]
        }


@dataclass
class CollisionTriggerSourceConfig:
    """
    碰撞触发源组件配置
    来源：碰撞触发源.md (第20-29行)
    注意：组件仅可同时生效一个碰撞触发源（第3行）
    """
    # 初始生效（是否在物件创建时激活）
    initially_active: bool = True
    # 触发区形状
    shape: TriggerShape = TriggerShape.CUBOID
    # 中心（相对实体/元件中心的偏移）
    center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 缩放倍率
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "初始生效": self.initially_active,
            "触发区形状": self.shape.value,
            "中心": self.center,
            "旋转": self.rotation,
            "缩放倍率": self.scale
        }


@dataclass
class ExtraCollisionDefinition:
    """
    额外碰撞定义
    来源：额外碰撞.md (第33-48行)
    """
    # 碰撞区序号
    collision_index: int
    # 初始生效
    initially_active: bool = True
    # 是否可攀爬
    climbable: bool = False
    # 碰撞区域列表
    collision_areas: List[TriggerArea] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "碰撞区序号": self.collision_index,
            "初始生效": self.initially_active,
            "是否可攀爬": self.climbable,
            "碰撞区域": [area.to_dict() for area in self.collision_areas]
        }


@dataclass
class ExtraCollisionComponentConfig:
    """
    额外碰撞组件配置
    来源：额外碰撞.md (第1-56行)
    注意：可支持同时生效多个额外碰撞（第4行）
    """
    # 原生碰撞生效
    native_collision_active: bool = True
    # 额外碰撞列表
    extra_collisions: List[ExtraCollisionDefinition] = field(default_factory=list)
    # 初始生效额外碰撞序号列表
    initially_active_collisions: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "原生碰撞生效": self.native_collision_active,
            "额外碰撞列表": [ec.to_dict() for ec in self.extra_collisions],
            "初始生效额外碰撞": self.initially_active_collisions
        }

