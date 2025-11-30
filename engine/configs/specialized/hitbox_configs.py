"""
受击盒设置配置
基于知识库：受击盒设置.md
"""
from dataclasses import dataclass, field
from typing import List, Tuple
from enum import Enum


# ============================================================================
# 受击盒设置 (受击盒设置.md)
# ============================================================================

class TriggerShape(str, Enum):
    """触发区域形状"""
    CUBOID = "长方体"
    SPHERE = "球体"
    CAPSULE = "胶囊体"


@dataclass
class HitboxTriggerArea:
    """受击触发区域"""
    shape: TriggerShape
    center_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 长方体、胶囊体
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)  # 长方体
    radius: float = 1.0  # 球体、胶囊体
    height: float = 2.0  # 胶囊体
    
    doc_reference: str = "受击盒设置.md:17-20"


@dataclass
class HitboxTrigger:
    """受击触发器"""
    enabled_on_init: bool = True
    trigger_areas: List[HitboxTriggerArea] = field(default_factory=list)
    
    doc_reference: str = "受击盒设置.md:15-16"
    notes: str = "多个受击触发区之间以并集相互组合"


@dataclass
class HitboxComponentConfig:
    """受击盒组件配置"""
    enabled_on_init: bool = True
    triggers: List[HitboxTrigger] = field(default_factory=list)
    
    doc_reference: str = "受击盒设置.md:7-10"
    notes: str = "默认具有一个不可删除的受击盒组件"


# ============================================================================
# 验证函数
# ============================================================================

def validate_hitbox_config(entity_type: str) -> List[str]:
    """验证受击盒配置可用性"""
    errors = []
    
    # 检查是否支持受击盒
    if entity_type in ["关卡", "玩家"]:
        errors.append(
            f"[受击盒错误] 实体类型'{entity_type}'不支持受击盒组件\n"
            "受击盒用于攻击命中检测，需要物理实体"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 受击盒配置测试 ===\n")
    
    # 测试受击盒配置
    print("1. 受击盒配置：")
    hitbox = HitboxComponentConfig(
        enabled_on_init=True,
        triggers=[
            HitboxTrigger(
                enabled_on_init=True,
                trigger_areas=[
                    HitboxTriggerArea(
                        shape=TriggerShape.SPHERE,
                        center_offset=(0.0, 1.0, 0.0),
                        radius=2.0
                    )
                ]
            )
        ]
    )
    print(f"   触发器数量：{len(hitbox.triggers)}")
    print(f"   第一个触发区形状：{hitbox.triggers[0].trigger_areas[0].shape.value}")
    
    print("\n[OK] 受击盒配置测试完成")

