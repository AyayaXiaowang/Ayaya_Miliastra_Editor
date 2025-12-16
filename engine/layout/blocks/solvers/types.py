from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING

from ...internal.layout_models import LayoutBlock

if TYPE_CHECKING:
    from ...internal.layout_context import LayoutContext


StableBlockSortKey = Callable[[LayoutBlock], tuple[int, str, str]]


@dataclass(frozen=True)
class PositioningEngineConfig:
    """
    BlockPositioningEngine 的只读配置（跨阶段稳定）。

    注意：这里不承载运行期可变集合（例如 positioned_blocks / bucket_map），避免阶段之间隐式共享难追踪。
    """

    initial_x: float
    initial_y: float
    block_x_spacing: float
    block_y_spacing: float
    enable_tight_block_spacing: bool
    global_context: Optional["LayoutContext"]
    block_map: Dict[str, LayoutBlock]
    parents_map: Dict[LayoutBlock, Set[LayoutBlock]]
    stable_sort_key: StableBlockSortKey


@dataclass
class PositioningRuntimeState:
    """
    BlockPositioningEngine 的运行期状态（跨阶段持续累积）。

    说明：该对象包含可变集合引用，阶段实现会原地更新它，从而保持与旧实现一致的副作用语义。
    """

    positioned_blocks: Set[LayoutBlock]
    bucket_size: float
    bucket_map: Dict[int, List[LayoutBlock]]


