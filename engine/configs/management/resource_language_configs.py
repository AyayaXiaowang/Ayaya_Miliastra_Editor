"""
技能资源与多语言配置模块
包含技能资源和多语言文本配置
"""

from dataclasses import dataclass, field
from typing import List, Dict


# ============================================================================
# 技能资源配置
# ============================================================================

@dataclass
class SkillResourceConfig:
    """技能资源配置 - 按官方文档"""
    resource_id: str  # 配置ID（唯一标识）
    resource_name: str  # 技能资源名
    growth_type: str = "无条件增长"  # 增长类型：无条件增长/跟随技能(保留值)/跟随技能(不保留值)
    max_obtainable_value: float = 100.0  # 可获取最大值
    initial_value: float = 100.0  # 初始值
    recovery_rate: float = 5.0  # 恢复速率（每秒）
    referenced_skills: List[str] = field(default_factory=list)  # 引用信息（哪些技能引用了此资源）
    icon: str = ""
    color: str = "#0000FF"  # 显示颜色
    description: str = ""
    
    # 兼容旧字段
    resource_type: str = "custom"  # 保留用于兼容
    max_value: float = 100.0  # 兼容旧字段
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "growth_type": self.growth_type,
            "max_obtainable_value": self.max_obtainable_value,
            "initial_value": self.initial_value,
            "recovery_rate": self.recovery_rate,
            "referenced_skills": self.referenced_skills,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            # 兼容
            "resource_type": self.resource_type,
            "max_value": self.max_value,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'SkillResourceConfig':
        return SkillResourceConfig(
            resource_id=data["resource_id"],
            resource_name=data["resource_name"],
            growth_type=data.get("growth_type", "无条件增长"),
            max_obtainable_value=data.get("max_obtainable_value", data.get("max_value", 100.0)),
            initial_value=data.get("initial_value", 100.0),
            recovery_rate=data.get("recovery_rate", 5.0),
            referenced_skills=data.get("referenced_skills", []),
            icon=data.get("icon", ""),
            color=data.get("color", "#0000FF"),
            description=data.get("description", ""),
            # 兼容
            resource_type=data.get("resource_type", "custom"),
            max_value=data.get("max_value", 100.0),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 多语言文本配置
# ============================================================================

@dataclass
class MultiLanguageTextConfig:
    """多语言文本配置"""
    text_key: str
    translations: Dict[str, str] = field(default_factory=dict)  # 语言代码 -> 翻译文本
    category: str = "general"
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "text_key": self.text_key,
            "translations": self.translations,
            "category": self.category,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'MultiLanguageTextConfig':
        return MultiLanguageTextConfig(
            text_key=data["text_key"],
            translations=data.get("translations", {}),
            category=data.get("category", "general"),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 技能资源与多语言配置测试 ===\n")
    
    # 测试技能资源
    print("1. 技能资源配置:")
    resource = SkillResourceConfig(
        resource_id="res_001",
        resource_name="魔力",
        growth_type="无条件增长",
        max_obtainable_value=100.0,
        initial_value=100.0,
        recovery_rate=5.0,
        color="#0000FF"
    )
    print(f"   资源名: {resource.resource_name}")
    print(f"   增长类型: {resource.growth_type}")
    print(f"   最大值: {resource.max_obtainable_value}")
    print(f"   初始值: {resource.initial_value}")
    print(f"   恢复速率: {resource.recovery_rate}/秒")
    
    # 测试多语言文本
    print("\n2. 多语言文本配置:")
    text = MultiLanguageTextConfig(
        text_key="ui.welcome",
        translations={
            "zh-CN": "欢迎",
            "en-US": "Welcome",
            "ja-JP": "ようこそ"
        },
        category="ui"
    )
    print(f"   文本键: {text.text_key}")
    print(f"   翻译数量: {len(text.translations)}")
    print(f"   中文: {text.translations.get('zh-CN')}")
    print(f"   英文: {text.translations.get('en-US')}")
    
    # 测试序列化
    print("\n3. 序列化测试:")
    resource_data = resource.serialize()
    resource_restored = SkillResourceConfig.deserialize(resource_data)
    print(f"   资源序列化成功: {resource.resource_name == resource_restored.resource_name}")
    
    text_data = text.serialize()
    text_restored = MultiLanguageTextConfig.deserialize(text_data)
    print(f"   文本序列化成功: {text.text_key == text_restored.text_key}")
    
    print("\n✅ 技能资源与多语言配置测试完成")

