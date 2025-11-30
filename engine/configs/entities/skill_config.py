"""
技能配置
基于: 技能.md
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class SkillType(Enum):
    """技能类型"""
    INSTANT = "瞬发技能"  # 无法编辑动画，在接受输入的瞬间立即触发逻辑
    HOLD = "长按技能"  # 提供循环动画类型的技能，玩家长按对应的输入即可进入循环动画
    NORMAL = "普通技能"  # 基础的技能类型
    COMBO = "连段技能"  # 可以配置一连串的连续动作，并在接受特定时点的输入后，在动作之间进行跳转
    AIM = "瞄准技能"  # 提供成套的瞄准动作，并在施放技能时使角色进入瞄准状态


class TargetRangeType(Enum):
    """索敌范围类型"""
    CYLINDER = "圆柱体"  # 使用半径和高度进行描述
    SECTOR = "扇形"  # 半径、高度、角度、旋转


class AimEnterMode(Enum):
    """瞄准进入方式"""
    HOLD = "长按"  # 长按技能进入瞄准状态，松开后退出
    TOGGLE = "点按切换"  # 点按技能进入瞄准状态，再次点击退出


class SkillSlot(Enum):
    """技能槽位"""
    NORMAL_ATTACK = "普通攻击"  # 对应PC端鼠标左键
    SKILL_1 = "技能1"  # 对应PC端键盘Q键
    SKILL_2 = "技能2"  # 对应PC端键盘E键
    SKILL_3 = "技能3"  # 对应PC端键盘R键
    SKILL_4 = "技能4"  # 对应PC端键盘T键


@dataclass
class TargetRange:
    """索敌范围配置"""
    range_type: TargetRangeType = TargetRangeType.CYLINDER
    radius: float = 5.0  # 半径
    height: float = 2.0  # 高度
    angle: float = 90.0  # 扇形角度（仅扇形类型）
    rotation: float = 0.0  # 旋转（仅扇形类型）


@dataclass
class SkillBasicSettings:
    """基础设置"""
    enable_cliff_protection: bool = False  # 启用运动坠崖保护
    can_use_in_air: bool = False  # 是否可以在空中释放
    skill_note: str = ""  # 技能备注


@dataclass
class SkillNumericConfig:
    """数值配置"""
    has_cooldown: bool = False  # 是否有冷却时间
    cooldown_time: float = 0.0  # 冷却时间(s)
    
    has_usage_limit: bool = False  # 是否有次数限制
    usage_count: int = 1  # 使用次数
    
    has_cost: bool = False  # 是否有消耗
    cost_type: str = ""  # 消耗类型（技能资源类型）
    cost_amount: float = 0.0  # 消耗量
    
    target_range: TargetRange = field(default_factory=TargetRange)  # 索敌范围


@dataclass
class SkillLifecycleConfig:
    """生命周期管理"""
    destroy_on_limit: bool = False  # 达到次数上限是否销毁技能
    max_usage_count: int = 0  # 次数上限


@dataclass
class ComboSkillConfig:
    """连段配置（连段技能专用）"""
    enable_charge_branch: bool = False  # 是否开启蓄力分支
    shared_charge_precast: bool = False  # 蓄力公共前摇


@dataclass
class AimSkillConfig:
    """瞄准配置（瞄准技能专用）"""
    aim_enter_mode: AimEnterMode = AimEnterMode.HOLD  # 瞄准进入方式
    can_move_while_aiming: bool = False  # 瞄准中是否可移动
    custom_fire_duration: bool = False  # 是否自定义瞄准发射动画时长
    fire_animation_duration: float = 1.0  # 瞄准发射动画时长


@dataclass
class AnimationSlot:
    """动画槽位"""
    slot_name: str
    animation_id: str = ""
    duration: float = 0.0


@dataclass
class EventTrackItem:
    """事件轨道项"""
    event_type: str  # 开始/结束/节点图/状态
    time_point: float = 0.0
    end_time_point: float = 0.0  # 状态轨道用
    node_graph_id: str = ""  # 节点图事件用
    state_config: dict = field(default_factory=dict)  # 状态配置


@dataclass
class BranchConfig:
    """分支配置（长按技能、瞄准技能用）"""
    branch_id: str
    animation_slots: List[AnimationSlot] = field(default_factory=list)
    event_tracks: List[EventTrackItem] = field(default_factory=list)


@dataclass
class ComboResponseEvent:
    """连段响应事件（连段技能用）"""
    pre_input_duration: float = 0.5  # 预输入阶段时长
    response_count: int = 1  # 可响应段数
    response_targets: List[str] = field(default_factory=list)  # 响应跳转动画槽位ID
    
    can_jump_to_charge: bool = False  # 当前预输入是否可跳转蓄力分支
    charge_success_duration: float = 1.0  # 蓄力成功时长


@dataclass
class AimStateConfig:
    """进入瞄准状态配置"""
    camera_fov: float = 60.0  # 镜头视野
    aim_offset: tuple = (0.0, 0.0, 0.0)  # 瞄准视角偏移
    pitch_range: tuple = (-45.0, 45.0)  # 俯仰角度范围
    enter_transition_duration: float = 0.3  # 进入过渡时长(秒)
    exit_transition_duration: float = 0.3  # 退出过渡时长(秒)


@dataclass
class SkillAnimationConfig:
    """技能动画配置"""
    animation_slots: List[AnimationSlot] = field(default_factory=list)  # 动作轴
    event_tracks: List[EventTrackItem] = field(default_factory=list)  # 逻辑轴
    
    # 长按技能专用
    loop_animation_duration: float = 0.0  # 循环动画持续时长
    branches: List[BranchConfig] = field(default_factory=list)  # 分支
    branch_track_config: dict = field(default_factory=dict)  # 分支轨道配置
    
    # 连段技能专用
    combo_track: List[ComboResponseEvent] = field(default_factory=list)  # 连段轨道
    public_precast_slot: Optional[AnimationSlot] = None  # 公共前摇
    charge_branch_animation: Optional['SkillAnimationConfig'] = None  # 蓄力分支动画
    
    # 瞄准技能专用
    aim_state_config: Optional[AimStateConfig] = None  # 瞄准状态配置
    enable_crosshair: bool = False  # 开启准星


@dataclass
class SkillConfig:
    """
    技能配置
    
    参考: 技能.md
    """
    config_id: str  # 配置ID：技能的唯一标识
    skill_type: SkillType = SkillType.NORMAL  # 技能类型
    
    # 基础设置
    basic_settings: SkillBasicSettings = field(default_factory=SkillBasicSettings)
    
    # 数值配置
    numeric_config: SkillNumericConfig = field(default_factory=SkillNumericConfig)
    
    # 生命周期管理
    lifecycle_config: SkillLifecycleConfig = field(default_factory=SkillLifecycleConfig)
    
    # 连段配置（连段技能专用）
    combo_config: Optional[ComboSkillConfig] = None
    
    # 瞄准配置（瞄准技能专用）
    aim_config: Optional[AimSkillConfig] = None
    
    # 动画配置
    animation_config: SkillAnimationConfig = field(default_factory=SkillAnimationConfig)
    
    # 技能槽位
    skill_slot: Optional[SkillSlot] = None
    
    def serialize(self) -> dict:
        """序列化为字典"""
        data = {
            "config_id": self.config_id,
            "skill_type": self.skill_type.value,
            "basic_settings": {
                "enable_cliff_protection": self.basic_settings.enable_cliff_protection,
                "can_use_in_air": self.basic_settings.can_use_in_air,
                "skill_note": self.basic_settings.skill_note
            },
            "numeric_config": {
                "has_cooldown": self.numeric_config.has_cooldown,
                "cooldown_time": self.numeric_config.cooldown_time,
                "has_usage_limit": self.numeric_config.has_usage_limit,
                "usage_count": self.numeric_config.usage_count,
                "has_cost": self.numeric_config.has_cost,
                "cost_type": self.numeric_config.cost_type,
                "cost_amount": self.numeric_config.cost_amount,
                "target_range": {
                    "range_type": self.numeric_config.target_range.range_type.value,
                    "radius": self.numeric_config.target_range.radius,
                    "height": self.numeric_config.target_range.height,
                    "angle": self.numeric_config.target_range.angle,
                    "rotation": self.numeric_config.target_range.rotation
                }
            },
            "lifecycle_config": {
                "destroy_on_limit": self.lifecycle_config.destroy_on_limit,
                "max_usage_count": self.lifecycle_config.max_usage_count
            }
        }
        
        if self.combo_config:
            data["combo_config"] = {
                "enable_charge_branch": self.combo_config.enable_charge_branch,
                "shared_charge_precast": self.combo_config.shared_charge_precast
            }
        
        if self.aim_config:
            data["aim_config"] = {
                "aim_enter_mode": self.aim_config.aim_enter_mode.value,
                "can_move_while_aiming": self.aim_config.can_move_while_aiming,
                "custom_fire_duration": self.aim_config.custom_fire_duration,
                "fire_animation_duration": self.aim_config.fire_animation_duration
            }
        
        if self.skill_slot:
            data["skill_slot"] = self.skill_slot.value
        
        # 简化动画配置序列化
        data["animation_config"] = {
            "animation_slots": [{"slot_name": s.slot_name, "animation_id": s.animation_id, "duration": s.duration} for s in self.animation_config.animation_slots],
            "event_tracks": [{"event_type": e.event_type, "time_point": e.time_point} for e in self.animation_config.event_tracks]
        }
        
        return data
    
    @staticmethod
    def deserialize(data: dict) -> 'SkillConfig':
        """从字典反序列化"""
        skill = SkillConfig(
            config_id=data["config_id"],
            skill_type=SkillType(data["skill_type"])
        )
        
        # 基础设置
        bs = data.get("basic_settings", {})
        skill.basic_settings = SkillBasicSettings(
            enable_cliff_protection=bs.get("enable_cliff_protection", False),
            can_use_in_air=bs.get("can_use_in_air", False),
            skill_note=bs.get("skill_note", "")
        )
        
        # 数值配置
        nc = data.get("numeric_config", {})
        skill.numeric_config = SkillNumericConfig(
            has_cooldown=nc.get("has_cooldown", False),
            cooldown_time=nc.get("cooldown_time", 0.0),
            has_usage_limit=nc.get("has_usage_limit", False),
            usage_count=nc.get("usage_count", 1),
            has_cost=nc.get("has_cost", False),
            cost_type=nc.get("cost_type", ""),
            cost_amount=nc.get("cost_amount", 0.0)
        )
        
        # 目标范围
        tr = nc.get("target_range", {})
        if tr:
            skill.numeric_config.target_range = TargetRange(
                range_type=TargetRangeType(tr.get("range_type", "圆柱体")),
                radius=tr.get("radius", 5.0),
                height=tr.get("height", 2.0),
                angle=tr.get("angle", 90.0),
                rotation=tr.get("rotation", 0.0)
            )
        
        # 生命周期
        lc = data.get("lifecycle_config", {})
        skill.lifecycle_config = SkillLifecycleConfig(
            destroy_on_limit=lc.get("destroy_on_limit", False),
            max_usage_count=lc.get("max_usage_count", 0)
        )
        
        # 连段配置
        if "combo_config" in data:
            cc = data["combo_config"]
            skill.combo_config = ComboSkillConfig(
                enable_charge_branch=cc.get("enable_charge_branch", False),
                shared_charge_precast=cc.get("shared_charge_precast", False)
            )
        
        # 瞄准配置
        if "aim_config" in data:
            ac = data["aim_config"]
            skill.aim_config = AimSkillConfig(
                aim_enter_mode=AimEnterMode(ac.get("aim_enter_mode", "长按")),
                can_move_while_aiming=ac.get("can_move_while_aiming", False),
                custom_fire_duration=ac.get("custom_fire_duration", False),
                fire_animation_duration=ac.get("fire_animation_duration", 1.0)
            )
        
        # 技能槽位
        if "skill_slot" in data:
            skill.skill_slot = SkillSlot(data["skill_slot"])
        
        return skill


if __name__ == "__main__":
    print("=" * 60)
    print("技能配置测试")
    print("=" * 60)
    
    # 创建一个普通技能
    skill = SkillConfig(
        config_id="skill_fireball_001",
        skill_type=SkillType.NORMAL
    )
    skill.basic_settings.can_use_in_air = True
    skill.basic_settings.skill_note = "火球术"
    skill.numeric_config.has_cooldown = True
    skill.numeric_config.cooldown_time = 5.0
    skill.numeric_config.target_range.range_type = TargetRangeType.SECTOR
    skill.numeric_config.target_range.radius = 10.0
    skill.skill_slot = SkillSlot.SKILL_1
    
    print("\n✅ 创建普通技能成功")
    print(f"  技能ID: {skill.config_id}")
    print(f"  技能类型: {skill.skill_type.value}")
    print(f"  冷却时间: {skill.numeric_config.cooldown_time}秒")
    print(f"  索敌范围: {skill.numeric_config.target_range.range_type.value} (半径{skill.numeric_config.target_range.radius}m)")
    print(f"  技能槽位: {skill.skill_slot.value}")
    
    # 测试序列化
    data = skill.serialize()
    skill2 = SkillConfig.deserialize(data)
    print(f"\n✅ 序列化/反序列化测试通过")
    print(f"  反序列化后技能ID: {skill2.config_id}")

