"""
局内存档管理配置模块
用于描述局内存档相关的“局内存档管理”资源（引擎内部资源类型为 SAVE_POINT）。
"""

from dataclasses import dataclass, field
from typing import List, Tuple


# ============================================================================
# 局内存档管理配置
# ============================================================================

@dataclass
class SavePointConfig:
    """局内存档配置（单个局内存档管理/局内存档模板资源）"""
    save_point_id: str
    save_point_name: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    auto_save: bool = False  # 是否自动存档
    save_scope: str = "full"  # full/partial
    save_data_keys: List[str] = field(default_factory=list)  # 要保存的数据键
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "save_point_id": self.save_point_id,
            "save_point_name": self.save_point_name,
            "position": list(self.position),
            "auto_save": self.auto_save,
            "save_scope": self.save_scope,
            "save_data_keys": self.save_data_keys,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'SavePointConfig':
        return SavePointConfig(
            save_point_id=data["save_point_id"],
            save_point_name=data["save_point_name"],
            position=tuple(data.get("position", [0.0, 0.0, 0.0])),
            auto_save=data.get("auto_save", False),
            save_scope=data.get("save_scope", "full"),
            save_data_keys=data.get("save_data_keys", []),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 局内存档配置测试 ===\n")
    
    # 测试局内存档配置
    print("1. 局内存档配置:")
    save_point = SavePointConfig(
        save_point_id="save_001",
        save_point_name="第一章局内存档",
        position=(100.0, 0.0, 50.0),
        auto_save=True,
        save_scope="full"
    )
    print(f"   局内存档名: {save_point.save_point_name}")
    print(f"   位置: {save_point.position}")
    print(f"   自动存档: {save_point.auto_save}")
    print(f"   存档范围: {save_point.save_scope}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = save_point.serialize()
    restored = SavePointConfig.deserialize(data)
    print(f"   序列化成功: {save_point.save_point_name == restored.save_point_name}")
    
    print("\n✅ 局内存档配置测试完成")

