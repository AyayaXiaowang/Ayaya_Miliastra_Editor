"""
CombatPlayerEditorPanel 拆分模块：类型与轻量上下文。

该文件仅包含 dataclass，用于在多个 mixin 之间共享类型约束，
避免在入口模块 `combat_player_panel_sections.py` 中堆叠大量实现细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class _PlayerEditorStruct:
    """内部使用的玩家编辑结构，方便类型约束。"""

    player: Dict[str, Any]
    role: Dict[str, Any]


@dataclass
class _GraphBindingContext:
    """为 GraphsTab 提供的轻量上下文对象。

    仅暴露:
    - default_graphs: 当前对象挂载的节点图 ID 列表
    - graph_variable_overrides: 节点图暴露变量覆盖字典
    """

    default_graphs: List[str]
    graph_variable_overrides: Dict[str, Dict[str, object]]


