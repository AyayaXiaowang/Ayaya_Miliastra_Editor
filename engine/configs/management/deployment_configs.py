"""
部署配置模块
包含实体布设组管理配置
"""

from dataclasses import dataclass, field
from typing import List


# ============================================================================
# 实体布设组管理配置
# ============================================================================

@dataclass
class EntityDeploymentGroupConfig:
    """实体布设组配置"""
    group_id: str
    group_name: str
    entity_instances: List[str] = field(default_factory=list)  # 实例ID列表
    spawn_mode: str = "all_at_once"  # all_at_once/sequential/random
    spawn_delay: float = 0.0  # 延迟（秒）
    respawn_enabled: bool = False
    respawn_interval: float = 30.0
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "entity_instances": self.entity_instances,
            "spawn_mode": self.spawn_mode,
            "spawn_delay": self.spawn_delay,
            "respawn_enabled": self.respawn_enabled,
            "respawn_interval": self.respawn_interval,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'EntityDeploymentGroupConfig':
        return EntityDeploymentGroupConfig(
            group_id=data["group_id"],
            group_name=data["group_name"],
            entity_instances=data.get("entity_instances", []),
            spawn_mode=data.get("spawn_mode", "all_at_once"),
            spawn_delay=data.get("spawn_delay", 0.0),
            respawn_enabled=data.get("respawn_enabled", False),
            respawn_interval=data.get("respawn_interval", 30.0),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 部署配置测试 ===\n")
    
    # 测试实体布设组
    print("1. 实体布设组配置:")
    group = EntityDeploymentGroupConfig(
        group_id="group_001",
        group_name="敌人波次1",
        entity_instances=["enemy_001", "enemy_002", "enemy_003"],
        spawn_mode="sequential",
        spawn_delay=2.0,
        respawn_enabled=True,
        respawn_interval=60.0
    )
    print(f"   组名: {group.group_name}")
    print(f"   实体数量: {len(group.entity_instances)}")
    print(f"   生成模式: {group.spawn_mode}")
    print(f"   延迟: {group.spawn_delay}秒")
    print(f"   重生: {group.respawn_enabled}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = group.serialize()
    restored = EntityDeploymentGroupConfig.deserialize(data)
    print(f"   序列化成功: {group.group_name == restored.group_name}")
    
    print("\n✅ 部署配置测试完成")

