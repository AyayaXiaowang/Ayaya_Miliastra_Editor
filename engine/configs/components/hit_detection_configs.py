"""
组件配置 - 命中检测
基于知识库文档定义的命中检测组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum
from .collision_configs import TriggerShape, CollisionTargetType


class HitTriggerType(Enum):
    """触发类型（命中检测.md 第19行）"""
    SINGLE = "单次触发"
    NO_REPEAT = "不重复触发"
    REPEAT = "重复触发"


class CCDType(Enum):
    """CCD类型（命中检测.md 第23行）"""
    THRESHOLD = "速度超过阈值"
    ALWAYS = "持续生效"


class CampFilter(Enum):
    """阵营筛选（命中检测.md 第28行）"""
    NONE = "无"
    HOSTILE = "敌对阵营"
    FRIENDLY = "友善阵营"
    FRIENDLY_WITH_SELF = "友善阵营包含自身实体"
    SELF_CAMP = "自身阵营"
    ALL = "所有阵营"
    ALL_EXCLUDE_SELF = "所有阵营排除自身实体"


class HitLayerType(Enum):
    """命中层筛选（命中检测.md 第30行）"""
    HIT_BOX = "受击盒"
    SCENE = "场景"
    OBJECT_COLLISION = "物件自身碰撞"


@dataclass
class HitDetectionArea:
    """
    命中区域配置
    来源：命中检测.md (第33-45行)
    """
    # 触发区形状
    shape: TriggerShape = TriggerShape.CUBOID
    # 中心（相对实体或元件中心的偏移）
    center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转（仅长方体）
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 缩放倍率（仅长方体）
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    # 半径（球体/胶囊体）
    radius: float = 1.0
    # 角度（仅胶囊体）
    angle: float = 0.0
    # 高度（仅胶囊体）
    height: float = 2.0
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "触发区形状": self.shape.value,
            "中心": self.center
        }
        if self.shape == TriggerShape.CUBOID:
            result["旋转"] = self.rotation
            result["缩放倍率"] = self.scale
        elif self.shape == TriggerShape.SPHERE:
            result["半径"] = self.radius
        elif self.shape == TriggerShape.CAPSULE:
            result["半径"] = self.radius
            result["角度"] = self.angle
            result["高度"] = self.height
        return result


@dataclass
class HitDetectionConfig:
    """
    命中检测组件配置
    来源：命中检测.md (第14-45行)
    """
    # 触发类型
    trigger_type: HitTriggerType = HitTriggerType.SINGLE
    # 触发间隔（仅重复触发时可配置）
    trigger_interval: float = 0.1
    # 检测延迟时间
    detection_delay: float = 0.0
    # 开启CCD（连续碰撞检测）
    enable_ccd: bool = False
    # CCD类型
    ccd_type: CCDType = CCDType.THRESHOLD
    # 速度阈值（仅CCD类型为速度超过阈值时有效）
    speed_threshold: float = 10.0
    # 检测半径
    detection_radius: float = 0.5
    # 过滤器节点图
    filter_graph: str = ""
    # 启用下方筛选
    enable_filtering: bool = False
    # 阵营筛选
    camp_filter: CampFilter = CampFilter.ALL_EXCLUDE_SELF
    # 实体类型筛选
    entity_type_filter: List[CollisionTargetType] = field(default_factory=list)
    # 命中层筛选
    hit_layer_filter: List[HitLayerType] = field(default_factory=list)
    # 命中时执行能力单元
    hit_ability_units: List[str] = field(default_factory=list)
    # 命中区域列表
    hit_areas: List[HitDetectionArea] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "触发类型": self.trigger_type.value,
            "触发间隔": self.trigger_interval if self.trigger_type == HitTriggerType.REPEAT else None,
            "检测延迟时间": self.detection_delay,
            "开启CCD": self.enable_ccd,
            "CCD类型": self.ccd_type.value if self.enable_ccd else None,
            "速度阈值": self.speed_threshold if self.enable_ccd and self.ccd_type == CCDType.THRESHOLD else None,
            "检测半径": self.detection_radius,
            "过滤器节点图": self.filter_graph,
            "启用下方筛选": self.enable_filtering,
            "阵营筛选": self.camp_filter.value if self.enable_filtering else None,
            "实体类型筛选": [t.value for t in self.entity_type_filter] if self.enable_filtering else [],
            "命中层筛选": [layer.value for layer in self.hit_layer_filter] if self.enable_filtering else [],
            "命中时执行能力单元": self.hit_ability_units,
            "命中区域": [area.to_dict() for area in self.hit_areas]
        }

