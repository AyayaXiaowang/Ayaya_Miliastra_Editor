"""
组件配置 - 运动器
基于知识库文档定义的各类运动器组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum
from .collision_configs import TriggerArea


@dataclass
class ProjectileMotorConfig:
    """投射运动器组件配置（待完善）"""
    # 运动参数
    motion_params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "运动参数": self.motion_params
        }


class FollowType(Enum):
    """跟随类型（跟随运动器.md 第16-19行）"""
    COMPLETE_FOLLOW = "完全跟随"
    FOLLOW_POSITION = "跟随位置"
    FOLLOW_ROTATION = "跟随旋转"


class TrackingMode(Enum):
    """追踪方式（跟随运动器.md 第22-38行）"""
    ADSORPTION = "吸附追踪"
    DELAYED = "延时追踪"
    FIXED_SPEED = "定速追踪"


class CoordinateSystemType(Enum):
    """坐标系类型（跟随运动器.md 第41行）"""
    WORLD = "世界坐标系"
    RELATIVE = "相对坐标系"


@dataclass
class FollowMotorComponentConfig:
    """
    跟随运动器组件配置
    来源：跟随运动器.md (第1-49行)
    注意：同时只能生效一个跟随运动器（第3行）
    """
    # 初始生效
    initially_active: bool = False
    # 追踪目标（GUID）
    target_guid: str = ""
    # 跟随类型
    follow_type: FollowType = FollowType.COMPLETE_FOLLOW
    # 跟随挂接点
    follow_attach_point: str = ""
    # 追踪方式
    tracking_mode: TrackingMode = TrackingMode.ADSORPTION
    # 过渡时间（延时追踪）
    transition_time: float = 1.0
    # 初始速度（定速追踪）
    initial_speed: float = 5.0
    # 加速率（定速追踪）
    acceleration: float = 0.0
    # 加速时长（定速追踪）
    acceleration_duration: float = 0.0
    # 是否修正朝向运动方向（定速追踪）
    correct_direction: bool = False
    # 到达目标半径（定速追踪）
    arrival_radius: float = 0.5
    # 坐标系类型
    coordinate_system: CoordinateSystemType = CoordinateSystemType.WORLD
    # 偏移
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "初始生效": self.initially_active,
            "追踪目标": self.target_guid,
            "跟随类型": self.follow_type.value,
            "跟随挂接点": self.follow_attach_point,
            "追踪方式": self.tracking_mode.value,
            "过渡时间": self.transition_time if self.tracking_mode == TrackingMode.DELAYED else None,
            "初始速度": self.initial_speed if self.tracking_mode == TrackingMode.FIXED_SPEED else None,
            "加速率": self.acceleration if self.tracking_mode == TrackingMode.FIXED_SPEED else None,
            "加速时长": self.acceleration_duration if self.tracking_mode == TrackingMode.FIXED_SPEED else None,
            "是否修正朝向运动方向": self.correct_direction if self.tracking_mode == TrackingMode.FIXED_SPEED else None,
            "到达目标半径": self.arrival_radius if self.tracking_mode == TrackingMode.FIXED_SPEED else None,
            "坐标系类型": self.coordinate_system.value,
            "偏移": self.offset,
            "旋转": self.rotation
        }


class BasicMotorType(Enum):
    """基础运动器类型（基础运动器.md 第11-50行）"""
    UNIFORM_LINEAR = "匀速直线运动器"
    UNIFORM_ROTATION = "匀速旋转运动器"
    TARGET_ROTATION = "朝向目标旋转运动器"
    PATH_MOTION = "路径运动器"


class PathLoopType(Enum):
    """路径循环类型（基础运动器.md 第40-43行）"""
    ONE_WAY = "单程"
    ROUND_TRIP = "往返"
    LOOP = "循环"


class BasicMotorState(Enum):
    """基础运动器状态（基础运动器.md 第52-55行）"""
    INACTIVE = "未激活"
    RUNNING = "运作中"
    PAUSED = "暂停中"


@dataclass
class PathPoint:
    """路径点定义（基础运动器.md 第44-49行）"""
    # 到达时长
    arrival_duration: float = 1.0
    # 相对位置
    relative_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 相对旋转
    relative_rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 到达通知节点图
    notify_on_arrival: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "到达时长": self.arrival_duration,
            "相对位置": self.relative_position,
            "相对旋转": self.relative_rotation,
            "到达通知节点图": self.notify_on_arrival
        }


@dataclass
class BasicMotorDefinition:
    """
    基础运动器定义
    来源：基础运动器.md (第13-50行)
    """
    # 运动器名称（唯一标识）
    motor_name: str
    # 运动器类型
    motor_type: BasicMotorType = BasicMotorType.UNIFORM_LINEAR
    # 初始生效
    initially_active: bool = False
    # 生效时长
    duration: float = 0.0
    # 初始速度（匀速直线）
    initial_velocity: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 旋转轴朝向（匀速旋转）
    rotation_axis: List[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    # 角速度（匀速旋转）
    angular_velocity: float = 90.0
    # 绝对目标角度（朝向目标旋转）
    target_angle: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 循环类型（路径运动器）
    loop_type: PathLoopType = PathLoopType.ONE_WAY
    # 路径点列表（路径运动器）
    path_points: List[PathPoint] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "运动器名称": self.motor_name,
            "运动器类型": self.motor_type.value,
            "初始生效": self.initially_active,
            "生效时长": self.duration
        }
        if self.motor_type == BasicMotorType.UNIFORM_LINEAR:
            result["初始速度"] = self.initial_velocity
        elif self.motor_type == BasicMotorType.UNIFORM_ROTATION:
            result["旋转轴朝向"] = self.rotation_axis
            result["角速度"] = self.angular_velocity
        elif self.motor_type == BasicMotorType.TARGET_ROTATION:
            result["绝对目标角度"] = self.target_angle
        elif self.motor_type == BasicMotorType.PATH_MOTION:
            result["循环类型"] = self.loop_type.value
            result["路径点列表"] = [point.to_dict() for point in self.path_points]
        return result


@dataclass
class BasicMotorComponentConfig:
    """
    基础运动器组件配置
    来源：基础运动器.md (第1-82行)
    注意：可支持同时生效多个基础运动器（第4行）
    """
    # 基础运动器列表
    motors: List[BasicMotorDefinition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "基础运动器列表": [motor.to_dict() for motor in self.motors]
        }


class PerturbatorType(Enum):
    """角色扰动装置类型（角色扰动装置.md 第23行）"""
    EJECTOR = "弹射器"
    ATTRACTOR = "牵引器"
    FORCE_FIELD = "力场器"


class PerturbatorDirection(Enum):
    """扰动方向类型（角色扰动装置.md 第44-51行）"""
    SPECIFIED_DIRECTION = "指定方向"
    CHARACTER_TO_ENTITY = "角色至实体连线方向"
    ENTITY_TO_CHARACTER = "实体至角色连线方向"
    SPHERE_CENTER_LINE = "球心与触发区中心连线"


@dataclass
class PerturbatorDefinition:
    """
    角色扰动装置定义
    来源：角色扰动装置.md (第18-114行)
    """
    # 序号
    perturbator_index: int
    # 初始生效
    initially_active: bool = False
    # 装置类型
    perturbator_type: PerturbatorType = PerturbatorType.EJECTOR
    # 运动速率(m/s)
    motion_speed: float = 10.0
    # 稳定阶段时长(s)
    stable_duration: float = 0.5
    # 衰减阶段时长(s)
    decay_duration: float = 0.5
    # 本地过滤器（节点图引用）
    local_filter: str = ""
    # 触发区域列表
    trigger_areas: List[TriggerArea] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "序号": self.perturbator_index,
            "初始生效": self.initially_active,
            "装置类型": self.perturbator_type.value,
            "运动速率": self.motion_speed,
            "稳定阶段时长": self.stable_duration,
            "衰减阶段时长": self.decay_duration,
            "本地过滤器": self.local_filter,
            "触发区域": [area.to_dict() for area in self.trigger_areas]
        }


@dataclass
class CharacterPerturbatorComponentConfig:
    """
    角色扰动装置组件配置
    来源：角色扰动装置.md (第1-135行)
    注意：可配置多个扰动装置，但同时只能生效一个（第3行）
    """
    # 角色扰动装置列表
    perturbators: List[PerturbatorDefinition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "角色扰动装置列表": [p.to_dict() for p in self.perturbators]
        }

