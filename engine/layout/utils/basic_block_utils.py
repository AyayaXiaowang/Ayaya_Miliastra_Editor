from __future__ import annotations

from typing import Iterable, List

from engine.graph.models import BasicBlock


def build_basic_block(node_ids: Iterable[str], color: str, alpha: float = 0.2) -> BasicBlock:
    """
    构建 BasicBlock，集中管理透明度/节点列表等共有设置。
    """
    return BasicBlock(nodes=list(node_ids), color=color, alpha=alpha)


