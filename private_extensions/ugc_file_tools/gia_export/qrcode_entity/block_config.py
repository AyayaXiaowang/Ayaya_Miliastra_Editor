from __future__ import annotations


class BlockTemplate:
    def __init__(
        self,
        template_id: int,
        color_tuple: tuple[int, int, int],
        size_units: float,
        default_scale_tuple: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ):
        self.template_id = int(template_id)
        self.color_tuple = tuple(int(x) for x in color_tuple)
        self.size_units = float(size_units)
        self.default_scale_tuple = tuple(float(x) for x in default_scale_tuple)


class BlockConfig:
    """
    可用的方块模板清单（用于二维码方块墙）。

    说明：
    - 该清单源自历史工具集的可用模板集合；
    - `entity qrcode` 允许用户通过 template_id 选择黑/白方块。
    """

    AVAILABLE_BLOCKS: list[BlockTemplate] = [
        # 木质箱子
        BlockTemplate(template_id=20001224, color_tuple=(135, 114, 100), size_units=1.0),
        # 石质元素立方体
        BlockTemplate(template_id=20001034, color_tuple=(149, 160, 145), size_units=5.0),
        # 木质箱子（绿）
        BlockTemplate(template_id=20001237, color_tuple=(154, 180, 137), size_units=1.5),
        # 木质箱子（蓝）
        BlockTemplate(template_id=20001238, color_tuple=(151, 178, 181), size_units=1.5),
        # 木质箱子（紫）
        BlockTemplate(template_id=20001239, color_tuple=(179, 149, 183), size_units=1.5),
        # 石质墙体（黄）
        BlockTemplate(
            template_id=20001869,
            color_tuple=(242, 183, 81),
            size_units=3.0,
            default_scale_tuple=(1.0, 1.3, 1.0),
        ),
        # 石质墙体（红）
        BlockTemplate(
            template_id=20001870,
            color_tuple=(248, 132, 68),
            size_units=3.0,
            default_scale_tuple=(1.0, 1.3, 1.0),
        ),
        # 石质墙体（灰）
        BlockTemplate(
            template_id=20001872,
            color_tuple=(201, 210, 204),
            size_units=3.0,
            default_scale_tuple=(1.0, 1.3, 1.0),
        ),
        # 水质立方体
        BlockTemplate(template_id=20001874, color_tuple=(16, 127, 255), size_units=1.0),
        # 通常立方体（奶黄）
        BlockTemplate(template_id=20001875, color_tuple=(229, 211, 153), size_units=1.0),
        # 坚固立方体（暗蓝）
        BlockTemplate(template_id=20001876, color_tuple=(105, 171, 204), size_units=1.0),
        # 冰质立方体
        BlockTemplate(template_id=20001877, color_tuple=(146, 246, 255), size_units=1.0),
        # 火质立方体
        BlockTemplate(template_id=20001878, color_tuple=(255, 129, 57), size_units=1.0),
        # 雷质立方体
        BlockTemplate(template_id=20001879, color_tuple=(182, 111, 255), size_units=1.0),
        # 矩形木质矮柜
        BlockTemplate(
            template_id=20001082,
            color_tuple=(95, 87, 92),
            size_units=1.0,
            default_scale_tuple=(1.0, 1.25, 1.0),
        ),
        # 积木立方体（木色）
        BlockTemplate(template_id=20001096, color_tuple=(182, 168, 148), size_units=6.0),
        # 积木立方体（深色）
        BlockTemplate(template_id=20001097, color_tuple=(151, 140, 130), size_units=6.0),
        # 积木立方体（浅色）
        BlockTemplate(template_id=20001100, color_tuple=(189, 197, 195), size_units=6.0),
        # 石质天花板（白）
        BlockTemplate(
            template_id=20002146,
            color_tuple=(210, 220, 232),
            size_units=5.0,
            default_scale_tuple=(1.0, 41.7, 1.0),
        ),
        # 木质天花板（黑）
        BlockTemplate(
            template_id=20002121,
            color_tuple=(48, 55, 75),
            size_units=5.0,
            default_scale_tuple=(1.0, 41.7, 1.0),
        ),
        # 积木平台（绿）
        BlockTemplate(
            template_id=10005014,
            color_tuple=(77, 175, 116),
            size_units=5.0,
            default_scale_tuple=(1.0, 10.1, 1.0),
        ),
    ]

