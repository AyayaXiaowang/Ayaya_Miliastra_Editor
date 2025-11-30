"""
造物常规设置配置
基于知识库：常规设置.md
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


# ============================================================================
# 造物常规设置 (常规设置.md)
# ============================================================================

class BehaviorMode(str, Enum):
    """造物行为模式（枚举）"""
    # 具体值由造物行为模式图鉴定义
    pass


class OutOfCombatBehavior(str, Enum):
    """未入战行为"""
    WANDER = "游荡"
    PATROL = "巡逻"
    # 其他行为由行为模式池定义


class CombatDetectionType(str, Enum):
    """入战区域检测类型"""
    RANGE_SENSE = "范围感知"
    VIEW_DETECTION = "视野检测"


class ViewType(str, Enum):
    """视野类型"""
    FULL_VIEW = "全视野"
    VIEW_CONE = "视锥"


class PatrolLoopType(str, Enum):
    """巡逻循环类型"""
    ONE_WAY = "单程"
    ROUND_TRIP = "往返"
    LOOP = "循环"


class PatrolStartPosition(str, Enum):
    """巡逻起始位置"""
    NEAREST_POINT = "最近点"
    START_POINT = "起点"


class TerritoryShape(str, Enum):
    """领地形状"""
    NONE = "无"
    SPHERE = "球体"
    CYLINDER = "圆柱体"


@dataclass
class WanderConfig:
    """游荡配置"""
    movement_area_radius: float = 10.0  # 移动区域半径(m)
    movement_interval: Tuple[float, float] = (2.0, 5.0)  # 移动间隔时间(s)
    movement_distance: Tuple[float, float] = (3.0, 8.0)  # 单次移动距离(m)
    
    doc_reference: str = "常规设置.md:39-49"


@dataclass
class PatrolWaypoint:
    """巡逻路点"""
    waypoint_index: int
    move_speed: str = "跑"  # 走/跑
    arrival_radius: float = 1.0  # 抵达判定半径(m)
    stay_duration: float = 0.0  # 停留时间(s)
    rotate_on_arrival: bool = False  # 到达路点后转向
    notify_on_arrival: bool = False  # 到达时通知节点图
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    doc_reference: str = "常规设置.md:82-92"


@dataclass
class PatrolTemplate:
    """巡逻模板"""
    template_index: int
    enabled_on_init: bool = False
    loop_type: PatrolLoopType = PatrolLoopType.LOOP
    start_position: PatrolStartPosition = PatrolStartPosition.NEAREST_POINT
    global_path_id: int = 0  # 引用的全局路径ID
    waypoints: List[PatrolWaypoint] = field(default_factory=list)
    
    doc_reference: str = "常规设置.md:58-92"
    notes: str = "同一造物同时最多生效一个巡逻模板"


@dataclass
class CombatDetectionConfig:
    """入战区域配置"""
    detection_type: CombatDetectionType
    range_sense_distance: float = 10.0  # 范围感知距离
    view_type: ViewType = ViewType.FULL_VIEW
    view_cone_distance: float = 15.0  # 视锥距离
    full_view_radius: float = 15.0  # 全视野半径
    chain_combat_distance: float = 5.0  # 连携入战距离(m)
    
    doc_reference: str = "常规设置.md:98-117"


@dataclass
class DisengageConfig:
    """脱战设置"""
    disengage_distance: float = 20.0  # 脱战距离(m)
    disengage_on_pathfinding_fail: bool = True  # 寻路失败脱战
    pathfinding_fail_delay: float = 3.0  # 脱战延时(s)
    
    doc_reference: str = "常规设置.md:119-127"


@dataclass
class TerritoryConfig:
    """领地设置"""
    territory_shape: TerritoryShape = TerritoryShape.SPHERE
    territory_radius: float = 20.0  # 球体半径
    cylinder_radius: float = 20.0  # 圆柱体半径
    cylinder_height: float = 10.0  # 圆柱体高度
    disengage_when_player_leaves: bool = False  # 玩家离开区域后脱战
    leave_disengage_delay: float = 2.0  # 脱战延时(s)
    
    doc_reference: str = "常规设置.md:129-136"
    notes: str = "领地以造物的创建坐标为中心，不会随造物运动改变位置"


@dataclass
class CreatureSkillConfig:
    """造物技能配置"""
    skill_name: str
    enabled: bool = True
    initial_cooldown: Tuple[float, float] = (0.0, 2.0)  # 初始冷却区间(s)
    default_cooldown: Tuple[float, float] = (5.0, 10.0)  # 默认冷却区间(s)
    
    doc_reference: str = "常规设置.md:138-147"


@dataclass
class CreatureGeneralSettingsConfig:
    """造物常规设置（完整）"""
    behavior_mode: BehaviorMode
    out_of_combat_behavior: OutOfCombatBehavior
    wander_config: Optional[WanderConfig] = None
    patrol_templates: List[PatrolTemplate] = field(default_factory=list)
    combat_detection: CombatDetectionConfig = field(default_factory=CombatDetectionConfig)
    disengage_config: DisengageConfig = field(default_factory=DisengageConfig)
    territory_config: TerritoryConfig = field(default_factory=TerritoryConfig)
    skills: List[CreatureSkillConfig] = field(default_factory=list)
    
    doc_reference: str = "常规设置.md"
    entity_type_restriction: str = "仅造物可用"


# ============================================================================
# 验证函数
# ============================================================================

def validate_creature_general_settings(entity_type: str) -> List[str]:
    """验证造物常规设置可用性"""
    errors = []
    
    # 常规设置是造物专有 (常规设置.md:2)
    if entity_type != "造物":
        errors.append(
            "[常规设置错误] 常规设置是造物的专有特化配置\n"
            f"当前实体类型：{entity_type}\n"
            "参考：常规设置.md:2"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 造物常规设置配置测试 ===\n")
    
    # 测试游荡配置
    print("1. 造物游荡配置：")
    wander = WanderConfig(
        movement_area_radius=15.0,
        movement_interval=(3.0, 6.0),
        movement_distance=(5.0, 10.0)
    )
    print(f"   游荡范围：{wander.movement_area_radius}米")
    print(f"   移动间隔：{wander.movement_interval}秒")
    
    # 测试巡逻配置
    print("\n2. 造物巡逻配置：")
    patrol = PatrolTemplate(
        template_index=1,
        enabled_on_init=True,
        loop_type=PatrolLoopType.LOOP,
        global_path_id=100,
        waypoints=[
            PatrolWaypoint(waypoint_index=1, move_speed="跑", arrival_radius=1.5),
            PatrolWaypoint(waypoint_index=2, move_speed="走", stay_duration=3.0)
        ]
    )
    print(f"   循环类型：{patrol.loop_type.value}")
    print(f"   路点数量：{len(patrol.waypoints)}")
    
    print("\n[OK] 造物常规设置配置测试完成")

