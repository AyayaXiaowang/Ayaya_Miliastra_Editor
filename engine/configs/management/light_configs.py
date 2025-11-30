"""
光源配置模块
包含光源管理配置
"""

from dataclasses import dataclass, field
from typing import Tuple


# ============================================================================
# 光源管理配置
# ============================================================================

@dataclass
class LightSourceConfig:
    """光源配置"""
    light_id: str
    light_name: str
    light_type: str = "point"  # point/directional/spot/area
    color: str = "#FFFFFF"
    intensity: float = 1.0
    range_distance: float = 10.0  # 范围
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: Tuple[float, float, float] = (0.0, -1.0, 0.0)
    cast_shadows: bool = True
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "light_id": self.light_id,
            "light_name": self.light_name,
            "light_type": self.light_type,
            "color": self.color,
            "intensity": self.intensity,
            "range_distance": self.range_distance,
            "position": list(self.position),
            "direction": list(self.direction),
            "cast_shadows": self.cast_shadows,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'LightSourceConfig':
        return LightSourceConfig(
            light_id=data["light_id"],
            light_name=data["light_name"],
            light_type=data.get("light_type", "point"),
            color=data.get("color", "#FFFFFF"),
            intensity=data.get("intensity", 1.0),
            range_distance=data.get("range_distance", 10.0),
            position=tuple(data.get("position", [0.0, 0.0, 0.0])),
            direction=tuple(data.get("direction", [0.0, -1.0, 0.0])),
            cast_shadows=data.get("cast_shadows", True),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 光源配置测试 ===\n")
    
    # 测试光源配置
    print("1. 光源配置:")
    light = LightSourceConfig(
        light_id="light_001",
        light_name="主光源",
        light_type="directional",
        color="#FFFFCC",
        intensity=1.5,
        range_distance=50.0,
        position=(0.0, 20.0, 0.0),
        direction=(0.0, -1.0, 0.0),
        cast_shadows=True
    )
    print(f"   光源名: {light.light_name}")
    print(f"   类型: {light.light_type}")
    print(f"   颜色: {light.color}")
    print(f"   强度: {light.intensity}")
    print(f"   范围: {light.range_distance}米")
    print(f"   投射阴影: {light.cast_shadows}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = light.serialize()
    restored = LightSourceConfig.deserialize(data)
    print(f"   序列化成功: {light.light_name == restored.light_name}")
    
    print("\n✅ 光源配置测试完成")

