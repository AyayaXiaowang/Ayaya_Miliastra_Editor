"""节点图任务的步进模式辅助工具。"""

from __future__ import annotations

from enum import Enum

from engine.configs.settings import settings


class GraphStepMode(str, Enum):
    HUMAN = "human"
    AI = "ai"
    AI_NODE_BY_NODE = "ai_node_by_node"

    @classmethod
    def current(cls) -> "GraphStepMode":
        value = getattr(settings, "TODO_GRAPH_STEP_MODE", cls.HUMAN.value)
        if value not in cls._value2member_map_:
            return cls.HUMAN
        return cls._value2member_map_[value]

    @property
    def is_human(self) -> bool:
        return self is GraphStepMode.HUMAN

    @property
    def is_ai(self) -> bool:
        return self in {GraphStepMode.AI, GraphStepMode.AI_NODE_BY_NODE}

    @property
    def is_ai_node_by_node(self) -> bool:
        return self is GraphStepMode.AI_NODE_BY_NODE

    def flow_description(self) -> str:
        if self.is_human:
            return "按流程顺序创建并连接节点"
        if self.is_ai_node_by_node:
            return "逐个节点：创建→类型→参数；最后统一连线"
        return "先配置后连线：创建/类型/参数完成后，最后统一连线"


