"""配置数据类 - 基于知识库文档定义的所有配置项

所有配置类都可以从子模块直接导入
例如: from engine.configs.entities import ReviveConfig
或者: from engine.configs.combat import CombatPresetsModel
"""

# 导入子模块以便使用 from engine.configs import management
from . import combat, components, entities, management, specialized, rules  # noqa: F401

__all__ = [
    'combat',
    'components', 
    'entities',
    'management',
    'specialized',
    'rules',
]

