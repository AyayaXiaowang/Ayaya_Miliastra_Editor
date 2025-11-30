"""
职业系统配置
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class ProfessionType(str, Enum):
    """职业类型"""
    WARRIOR = "战士"
    MAGE = "法师"
    ARCHER = "弓箭手"
    ASSASSIN = "刺客"
    HEALER = "治疗"
    TANK = "坦克"
    CUSTOM = "自定义"


@dataclass
class ProfessionLevelConfig:
    """职业等级配置"""
    level: int
    required_exp: int
    unlock_skills: List[str] = field(default_factory=list)
    attribute_bonus: Dict[str, float] = field(default_factory=dict)


@dataclass
class ProfessionConfig:
    """
    职业配置 (职业.md)
    """
    profession_id: str
    profession_name: str
    profession_type: ProfessionType = ProfessionType.CUSTOM
    description: str = ""
    
    # 等级配置
    max_level: int = 100
    level_configs: List[ProfessionLevelConfig] = field(default_factory=list)
    
    # 初始属性
    initial_attributes: Dict[str, float] = field(default_factory=dict)
    
    # 初始技能
    initial_skills: List[str] = field(default_factory=list)
    
    # 职业特性
    profession_traits: List[str] = field(default_factory=list)
    
    # 文档引用
    doc_reference: str = "职业.md"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "职业ID": self.profession_id,
            "职业名称": self.profession_name,
            "职业类型": self.profession_type.value,
            "描述": self.description,
            "最大等级": self.max_level,
            "等级配置": [vars(lc) for lc in self.level_configs],
            "初始属性": self.initial_attributes,
            "初始技能": self.initial_skills,
            "职业特性": self.profession_traits
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ProfessionConfig':
        return ProfessionConfig(
            profession_id=data.get("职业ID", ""),
            profession_name=data.get("职业名称", ""),
            profession_type=ProfessionType(data.get("职业类型", "自定义")),
            description=data.get("描述", ""),
            max_level=data.get("最大等级", 100),
            initial_attributes=data.get("初始属性", {}),
            initial_skills=data.get("初始技能", []),
            profession_traits=data.get("职业特性", [])
        )


if __name__ == "__main__":
    print("=== 职业配置测试 ===")
    
    # 创建战士职业
    warrior = ProfessionConfig(
        profession_id="warrior_001",
        profession_name="狂战士",
        profession_type=ProfessionType.WARRIOR,
        description="近战高输出职业",
        max_level=50,
        initial_attributes={"攻击力": 100, "防御力": 50, "生命值": 1000},
        initial_skills=["重击", "旋风斩"],
        profession_traits=["狂暴", "嗜血"]
    )
    
    print(f"职业名称: {warrior.profession_name}")
    print(f"类型: {warrior.profession_type.value}")
    print(f"初始技能: {', '.join(warrior.initial_skills)}")

