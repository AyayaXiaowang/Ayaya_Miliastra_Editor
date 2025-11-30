"""节点图任务的步进模式辅助工具。"""

from __future__ import annotations

from enum import Enum

from engine.configs.settings import settings


class GraphStepMode(str, Enum):
    HUMAN = "human"
    AI = "ai"

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
        return self is GraphStepMode.AI

    def flow_description(self) -> str:
        if self.is_human:
            return "按流程顺序创建并连接节点"
        return "先创建所有节点，配置参数，再逐个连接"


