"""
计时器与变量配置模块
包含计时器管理和关卡变量配置
"""

from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# 计时器管理配置
# ============================================================================

@dataclass
class TimerManagementConfig:
    """计时器配置"""
    timer_id: str
    timer_name: str
    initial_time: float = 60.0  # 初始时间（秒）
    is_loop: bool = False  # 是否循环
    auto_start: bool = False  # 是否自动开始
    trigger_condition: str = ""  # 触发条件描述
    callback_graph: str = ""  # 回调节点图ID
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "timer_id": self.timer_id,
            "timer_name": self.timer_name,
            "initial_time": self.initial_time,
            "is_loop": self.is_loop,
            "auto_start": self.auto_start,
            "trigger_condition": self.trigger_condition,
            "callback_graph": self.callback_graph,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'TimerManagementConfig':
        return TimerManagementConfig(
            timer_id=data["timer_id"],
            timer_name=data["timer_name"],
            initial_time=data.get("initial_time", 60.0),
            is_loop=data.get("is_loop", False),
            auto_start=data.get("auto_start", False),
            trigger_condition=data.get("trigger_condition", ""),
            callback_graph=data.get("callback_graph", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 关卡变量配置
# ============================================================================

@dataclass
class LevelVariableConfig:
    """关卡变量配置"""
    variable_id: str
    variable_name: str
    data_type: str  # integer/float/string/boolean/vector3
    default_value: Any = None
    is_global: bool = True  # 是否全局可访问
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "variable_id": self.variable_id,
            "variable_name": self.variable_name,
            "data_type": self.data_type,
            "default_value": self.default_value,
            "is_global": self.is_global,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'LevelVariableConfig':
        return LevelVariableConfig(
            variable_id=data["variable_id"],
            variable_name=data["variable_name"],
            data_type=data["data_type"],
            default_value=data.get("default_value"),
            is_global=data.get("is_global", True),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 计时器与变量配置测试 ===\n")
    
    # 测试计时器
    print("1. 计时器配置:")
    timer = TimerManagementConfig(
        timer_id="timer_001",
        timer_name="主计时器",
        initial_time=120.0,
        is_loop=True
    )
    print(f"   计时器名: {timer.timer_name}")
    print(f"   初始时间: {timer.initial_time}秒")
    print(f"   是否循环: {timer.is_loop}")
    
    # 测试关卡变量
    print("\n2. 关卡变量配置:")
    variable = LevelVariableConfig(
        variable_id="var_001",
        variable_name="敌人数量",
        data_type="integer",
        default_value=10
    )
    print(f"   变量名: {variable.variable_name}")
    print(f"   类型: {variable.data_type}")
    print(f"   默认值: {variable.default_value}")
    
    # 测试序列化
    print("\n3. 序列化测试:")
    timer_data = timer.serialize()
    timer_restored = TimerManagementConfig.deserialize(timer_data)
    print(f"   序列化成功: {timer.timer_name == timer_restored.timer_name}")
    
    print("\n✅ 计时器与变量配置测试完成")

