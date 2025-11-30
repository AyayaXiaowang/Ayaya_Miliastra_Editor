"""
主镜头、全局路径和预设点配置模块

本模块实现以下高级概念配置：
- 主镜头系统配置
- 全局路径配置
- 预设点配置

注意：部分原始资料可能不完整，配置以常见游戏系统设计经验为基础进行补全
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum


# ==================== 主镜头系统配置 ====================

class CameraMode(Enum):
    """镜头模式"""
    THIRD_PERSON = "第三人称"
    FIRST_PERSON = "第一人称"
    FREE = "自由视角"
    FIXED = "固定视角"
    FOLLOW = "跟随视角"


class CameraTransitionType(Enum):
    """镜头过渡类型"""
    INSTANT = "瞬间切换"
    LINEAR = "线性过渡"
    SMOOTH = "平滑过渡"
    EASE_IN_OUT = "缓入缓出"


@dataclass
class CameraConfig:
    """主镜头配置
    
    配置项说明：
    - camera_mode: 镜头模式
    - follow_distance: 跟随距离
    - field_of_view: 视野角度（FOV）
    - camera_height: 镜头高度
    - look_at_offset: 观察点偏移
    - enable_collision: 启用碰撞检测
    - transition_type: 切换过渡类型
    - transition_duration: 过渡时长（秒）
    """
    camera_mode: CameraMode = CameraMode.THIRD_PERSON
    follow_distance: float = 5.0  # 跟随距离
    field_of_view: float = 60.0  # 视野角度（FOV）
    camera_height: float = 1.5  # 镜头高度
    look_at_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 观察点偏移
    enable_collision: bool = True  # 启用碰撞检测
    transition_type: CameraTransitionType = CameraTransitionType.SMOOTH
    transition_duration: float = 1.0  # 过渡时长（秒）
    
    # 第一人称相关
    first_person_height: float = 1.6  # 第一人称镜头高度
    
    # 自由视角相关
    free_camera_speed: float = 10.0  # 自由视角移动速度
    free_camera_rotation_speed: float = 5.0  # 自由视角旋转速度
    
    # 固定视角相关
    fixed_position: Tuple[float, float, float] = (0.0, 10.0, -10.0)  # 固定位置
    fixed_rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 固定旋转
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "镜头模式": self.camera_mode.value,
            "跟随距离": self.follow_distance,
            "视野角度(FOV)": self.field_of_view,
            "镜头高度": self.camera_height,
            "观察点偏移": list(self.look_at_offset),
            "启用碰撞检测": self.enable_collision,
            "切换过渡类型": self.transition_type.value,
            "过渡时长(秒)": self.transition_duration,
            "第一人称镜头高度": self.first_person_height,
            "自由视角移动速度": self.free_camera_speed,
            "自由视角旋转速度": self.free_camera_rotation_speed,
            "固定位置": list(self.fixed_position),
            "固定旋转": list(self.fixed_rotation)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CameraConfig':
        camera_mode_value = data.get("镜头模式", "第三人称")
        camera_mode = CameraMode.THIRD_PERSON
        for mode in CameraMode:
            if mode.value == camera_mode_value:
                camera_mode = mode
                break
        
        transition_type_value = data.get("切换过渡类型", "平滑过渡")
        transition_type = CameraTransitionType.SMOOTH
        for trans in CameraTransitionType:
            if trans.value == transition_type_value:
                transition_type = trans
                break
        
        return cls(
            camera_mode=camera_mode,
            follow_distance=data.get("跟随距离", 5.0),
            field_of_view=data.get("视野角度(FOV)", 60.0),
            camera_height=data.get("镜头高度", 1.5),
            look_at_offset=tuple(data.get("观察点偏移", [0.0, 0.0, 0.0])),
            enable_collision=data.get("启用碰撞检测", True),
            transition_type=transition_type,
            transition_duration=data.get("过渡时长(秒)", 1.0),
            first_person_height=data.get("第一人称镜头高度", 1.6),
            free_camera_speed=data.get("自由视角移动速度", 10.0),
            free_camera_rotation_speed=data.get("自由视角旋转速度", 5.0),
            fixed_position=tuple(data.get("固定位置", [0.0, 10.0, -10.0])),
            fixed_rotation=tuple(data.get("固定旋转", [0.0, 0.0, 0.0]))
        )


# ==================== 全局路径系统配置 ====================

class PathType(Enum):
    """路径类型"""
    LINEAR = "线性路径"
    BEZIER = "贝塞尔路径"
    SPLINE = "样条路径"
    WAYPOINT = "路点路径"


class PathLoopMode(Enum):
    """路径循环模式"""
    ONCE = "单次"
    LOOP = "循环"
    PING_PONG = "往返"


@dataclass
class PathPoint:
    """路径点"""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    speed: float = 1.0  # 到达此点的速度
    wait_time: float = 0.0  # 在此点等待的时间（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "位置": list(self.position),
            "旋转": list(self.rotation),
            "速度": self.speed,
            "等待时间": self.wait_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PathPoint':
        return cls(
            position=tuple(data.get("位置", [0.0, 0.0, 0.0])),
            rotation=tuple(data.get("旋转", [0.0, 0.0, 0.0])),
            speed=data.get("速度", 1.0),
            wait_time=data.get("等待时间", 0.0)
        )


@dataclass
class GlobalPathConfig:
    """全局路径配置
    
    配置项说明：
    - path_id: 路径ID
    - path_type: 路径类型
    - path_points: 路径点列表
    - loop_mode: 循环模式
    - default_speed: 默认移动速度
    - auto_start: 自动开始
    - smooth_factor: 平滑系数（用于样条路径）
    """
    path_id: str = ""
    path_type: PathType = PathType.LINEAR
    path_points: List[PathPoint] = field(default_factory=list)
    loop_mode: PathLoopMode = PathLoopMode.ONCE
    default_speed: float = 1.0
    auto_start: bool = False
    smooth_factor: float = 0.5  # 平滑系数（0-1）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "路径ID": self.path_id,
            "路径类型": self.path_type.value,
            "路径点列表": [point.to_dict() for point in self.path_points],
            "循环模式": self.loop_mode.value,
            "默认移动速度": self.default_speed,
            "自动开始": self.auto_start,
            "平滑系数": self.smooth_factor
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GlobalPathConfig':
        path_type_value = data.get("路径类型", "线性路径")
        path_type = PathType.LINEAR
        for pt in PathType:
            if pt.value == path_type_value:
                path_type = pt
                break
        
        loop_mode_value = data.get("循环模式", "单次")
        loop_mode = PathLoopMode.ONCE
        for lm in PathLoopMode:
            if lm.value == loop_mode_value:
                loop_mode = lm
                break
        
        path_points = [
            PathPoint.from_dict(point_data)
            for point_data in data.get("路径点列表", [])
        ]
        
        return cls(
            path_id=data.get("路径ID", ""),
            path_type=path_type,
            path_points=path_points,
            loop_mode=loop_mode,
            default_speed=data.get("默认移动速度", 1.0),
            auto_start=data.get("自动开始", False),
            smooth_factor=data.get("平滑系数", 0.5)
        )


# ==================== 预设点系统配置 ====================

class PresetPointType(Enum):
    """预设点类型"""
    SPAWN_POINT = "生成点"
    REVIVAL_POINT = "复苏点"
    TELEPORT_POINT = "传送点"
    WAYPOINT = "路点"
    CAMERA_POINT = "镜头点"
    TRIGGER_POINT = "触发点"


@dataclass
class PresetPointConfig:
    """预设点配置
    
    配置项说明：
    - point_id: 预设点ID
    - point_type: 预设点类型
    - position: 位置
    - rotation: 旋转
    - is_active: 是否激活
    - priority: 优先级
    - tags: 标签列表
    - custom_data: 自定义数据
    """
    point_id: str = ""
    point_type: PresetPointType = PresetPointType.SPAWN_POINT
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_active: bool = True
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "预设点ID": self.point_id,
            "预设点类型": self.point_type.value,
            "位置": list(self.position),
            "旋转": list(self.rotation),
            "是否激活": self.is_active,
            "优先级": self.priority,
            "标签列表": self.tags.copy(),
            "自定义数据": self.custom_data.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PresetPointConfig':
        point_type_value = data.get("预设点类型", "生成点")
        point_type = PresetPointType.SPAWN_POINT
        for pt in PresetPointType:
            if pt.value == point_type_value:
                point_type = pt
                break
        
        return cls(
            point_id=data.get("预设点ID", ""),
            point_type=point_type,
            position=tuple(data.get("位置", [0.0, 0.0, 0.0])),
            rotation=tuple(data.get("旋转", [0.0, 0.0, 0.0])),
            is_active=data.get("是否激活", True),
            priority=data.get("优先级", 0),
            tags=data.get("标签列表", []).copy(),
            custom_data=data.get("自定义数据", {}).copy()
        )


# ==================== 相关节点定义 ====================

CAMERA_NODES = {
    "切换镜头模式": {
        "类型": "执行节点",
        "功能": "切换玩家的镜头模式",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "镜头模式", "类型": "枚举", "说明": "要切换到的镜头模式"}
        ],
        "输出引脚": []
    },
    
    "设置镜头参数": {
        "类型": "执行节点",
        "功能": "设置镜头的各项参数",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "跟随距离", "类型": "浮点数", "说明": "镜头跟随距离"},
            {"名称": "视野角度", "类型": "浮点数", "说明": "视野角度(FOV)"}
        ],
        "输出引脚": []
    },
    
    "镜头震动": {
        "类型": "执行节点",
        "功能": "触发镜头震动效果",
        "输入引脚": [
            {"名称": "玩家实体", "类型": "实体", "说明": "目标玩家实体"},
            {"名称": "强度", "类型": "浮点数", "说明": "震动强度"},
            {"名称": "持续时间", "类型": "浮点数", "说明": "震动持续时间（秒）"}
        ],
        "输出引脚": []
    }
}


PATH_NODES = {
    "开始路径移动": {
        "类型": "执行节点",
        "功能": "使实体开始沿指定路径移动",
        "输入引脚": [
            {"名称": "实体", "类型": "实体", "说明": "要移动的实体"},
            {"名称": "路径ID", "类型": "字符串", "说明": "全局路径ID"},
            {"名称": "速度", "类型": "浮点数", "说明": "移动速度"}
        ],
        "输出引脚": []
    },
    
    "停止路径移动": {
        "类型": "执行节点",
        "功能": "停止实体的路径移动",
        "输入引脚": [
            {"名称": "实体", "类型": "实体", "说明": "要停止的实体"}
        ],
        "输出引脚": []
    },
    
    "获取路径进度": {
        "类型": "查询节点",
        "功能": "获取实体在路径上的移动进度",
        "输入引脚": [
            {"名称": "实体", "类型": "实体", "说明": "查询的实体"}
        ],
        "输出引脚": [
            {"名称": "进度", "类型": "浮点数", "说明": "路径进度（0-1）"},
            {"名称": "当前点索引", "类型": "整数", "说明": "当前路径点索引"}
        ]
    }
}


PRESET_POINT_NODES = {
    "激活预设点": {
        "类型": "执行节点",
        "功能": "激活指定的预设点",
        "输入引脚": [
            {"名称": "预设点ID", "类型": "字符串", "说明": "要激活的预设点ID"}
        ],
        "输出引脚": []
    },
    
    "注销预设点": {
        "类型": "执行节点",
        "功能": "注销指定的预设点",
        "输入引脚": [
            {"名称": "预设点ID", "类型": "字符串", "说明": "要注销的预设点ID"}
        ],
        "输出引脚": []
    },
    
    "传送到预设点": {
        "类型": "执行节点",
        "功能": "将实体传送到指定预设点",
        "输入引脚": [
            {"名称": "实体", "类型": "实体", "说明": "要传送的实体"},
            {"名称": "预设点ID", "类型": "字符串", "说明": "目标预设点ID"}
        ],
        "输出引脚": []
    },
    
    "根据标签查找预设点": {
        "类型": "查询节点",
        "功能": "根据标签查找预设点",
        "输入引脚": [
            {"名称": "标签", "类型": "字符串", "说明": "查找的标签"}
        ],
        "输出引脚": [
            {"名称": "预设点列表", "类型": "列表", "说明": "符合条件的预设点ID列表"}
        ]
    },
    
    "获取最近的预设点": {
        "类型": "查询节点",
        "功能": "获取距离指定位置最近的预设点",
        "输入引脚": [
            {"名称": "位置", "类型": "向量", "说明": "参考位置"},
            {"名称": "预设点类型", "类型": "枚举", "说明": "预设点类型（可选）"}
        ],
        "输出引脚": [
            {"名称": "预设点ID", "类型": "字符串", "说明": "最近的预设点ID"},
            {"名称": "距离", "类型": "浮点数", "说明": "距离"}
        ]
    }
}


# 导出所有节点
ALL_CAMERA_PATH_NODES = {
    **CAMERA_NODES,
    **PATH_NODES,
    **PRESET_POINT_NODES
}

