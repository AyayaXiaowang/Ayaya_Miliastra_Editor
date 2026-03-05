from __future__ import annotations

from .block_config import BlockConfig, BlockTemplate


class BlockHelper:
    @staticmethod
    def calculate_scale(template: BlockTemplate, global_scale: float = 1.0) -> tuple[float, float, float]:
        """
        计算方块缩放：
        - 使用 default_scale_tuple 把方块变为 size_units 的正方体
        - 再归一化到 1 单位
        - 最后乘以 global_scale
        """
        base_x, base_y, base_z = template.default_scale_tuple
        normalized_x = float(base_x) / float(template.size_units)
        normalized_y = float(base_y) / float(template.size_units)
        normalized_z = float(base_z) / float(template.size_units)
        return (
            normalized_x * float(global_scale),
            normalized_y * float(global_scale),
            normalized_z * float(global_scale),
        )

    @staticmethod
    def get_template_by_id(template_id: int) -> BlockTemplate | None:
        tid = int(template_id)
        for block in BlockConfig.AVAILABLE_BLOCKS:
            if int(block.template_id) == tid:
                return block
        return None

