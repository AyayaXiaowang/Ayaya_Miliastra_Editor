"""
外围系统配置模块
包含外围系统管理配置
"""

from dataclasses import dataclass, field


# ============================================================================
# 外围系统管理配置
# ============================================================================

@dataclass
class PeripheralSystemConfig:
    """外围系统配置"""
    system_id: str
    system_name: str
    system_type: str = "achievement"  # achievement/leaderboard/ranking
    enabled: bool = True
    config_data: dict = field(default_factory=dict)  # 系统特定配置
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "system_id": self.system_id,
            "system_name": self.system_name,
            "system_type": self.system_type,
            "enabled": self.enabled,
            "config_data": self.config_data,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'PeripheralSystemConfig':
        return PeripheralSystemConfig(
            system_id=data["system_id"],
            system_name=data["system_name"],
            system_type=data.get("system_type", "achievement"),
            enabled=data.get("enabled", True),
            config_data=data.get("config_data", {}),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 外围系统配置测试 ===\n")
    
    # 测试外围系统
    print("1. 外围系统配置:")
    system = PeripheralSystemConfig(
        system_id="system_001",
        system_name="成就系统",
        system_type="achievement",
        enabled=True,
        config_data={
            "max_achievements": 100,
            "show_notifications": True
        }
    )
    print(f"   系统名: {system.system_name}")
    print(f"   系统类型: {system.system_type}")
    print(f"   是否启用: {system.enabled}")
    print(f"   配置数据: {system.config_data}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = system.serialize()
    restored = PeripheralSystemConfig.deserialize(data)
    print(f"   序列化成功: {system.system_name == restored.system_name}")
    
    print("\n✅ 外围系统配置测试完成")

