from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BlockModel:
    """二维码方块墙中的单个方块（实体实例）的建模数据。"""

    template_id: int
    entity_id: int | None = None
    name: str = ""

    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    scale_z: float = 1.0

