"""
组件配置 - 计时器
基于知识库文档定义的计时器组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class TimerType(Enum):
    """计时器类型（全局计时器.md 第26行）"""
    COUNTDOWN = "倒计时"
    COUNTUP = "正计时"


class SourceEntityType(Enum):
    """来源实体类型（全局计时器.md 第38行）"""
    LEVEL = "关卡实体"
    PLAYER = "玩家实体"


@dataclass
class TimerSegment:
    """定时器时间段"""
    # 时间间隔(s)，最小精度0.03s（定时器.md 第13行）
    interval: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {"间隔(s)": self.interval}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimerSegment':
        return cls(interval=data.get("间隔(s)", 0.03))


@dataclass
class TimerDefinition:
    """
    定时器定义（通过节点图创建）
    """
    # 定时器名称（标识）
    timer_name: str
    # 是否循环
    is_loop: bool = False
    # 分段时间序列
    segments: List[TimerSegment] = field(default_factory=list)
    # 归属实体
    owner_entity: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "定时器名称": self.timer_name,
            "是否循环": self.is_loop,
            "分段时间": [seg.to_dict() for seg in self.segments],
            "归属实体": self.owner_entity
        }


@dataclass
class GlobalTimerDefinition:
    """
    全局计时器定义
    """
    # 计时器名称（引用标识）
    timer_name: str
    # 全局计时器类型
    timer_type: TimerType
    # 时长(s)（倒计时需要配置）
    duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "计时器名称": self.timer_name,
            "全局计时器类型": self.timer_type.value,
            "时长(s)": self.duration if self.timer_type == TimerType.COUNTDOWN else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GlobalTimerDefinition':
        timer_type_str = data.get("全局计时器类型", TimerType.COUNTDOWN.value)
        timer_type = TimerType(timer_type_str)
        return cls(
            timer_name=data.get("计时器名称", ""),
            timer_type=timer_type,
            duration=data.get("时长(s)", 0.0)
        )


@dataclass
class GlobalTimerComponentConfig:
    """
    全局计时器组件配置
    """
    # 引用的全局计时器列表（组件引用的计时器会随实体创建一同激活，全局计时器.md 第52行）
    referenced_timers: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "引用的计时器": self.referenced_timers
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GlobalTimerComponentConfig':
        return cls(
            referenced_timers=data.get("引用的计时器", [])
        )

