from __future__ import annotations

from typing import Any, Mapping

from .block_config import BlockTemplate
from .block_helper import BlockHelper
from .block_model import BlockModel


DEFAULT_AXIS_MAPPING: dict[str, str] = {
    "horizontal": "x",
    "vertical": "y",
    "depth": "z",
}


def generate_qrcode_image(
    text: str,
    *,
    version: int = 1,
    error_correction: int | None = None,
    box_size: int = 1,
    border: int = 1,
) -> Any:
    """
    生成二维码 Image（返回 PIL Image 类型，但这里避免在 import 阶段强依赖 Pillow）。

    依赖：
    - qrcode
    - Pillow
    """
    import qrcode

    if error_correction is None:
        error_correction = int(qrcode.constants.ERROR_CORRECT_L)

    qr_code_builder = qrcode.QRCode(
        version=int(version),
        error_correction=int(error_correction),
        box_size=int(box_size),
        border=int(border),
    )
    qr_code_builder.add_data(str(text))
    qr_code_builder.make(fit=True)
    return qr_code_builder.make_image(fill_color="black", back_color="white")


def qrcode_image_to_pixels(qrcode_image: Any, *, flip_vertical: bool = True) -> list[list[bool]]:
    binary_image = qrcode_image.convert("1")
    image_width, image_height = binary_image.size

    pixels: list[list[bool]] = []
    row_indices = range(image_height - 1, -1, -1) if bool(flip_vertical) else range(image_height)
    for pixel_row_index in row_indices:
        row: list[bool] = []
        for pixel_column_index in range(image_width):
            pixel_value = binary_image.getpixel((pixel_column_index, pixel_row_index))
            row.append(pixel_value == 0)
        pixels.append(row)
    return pixels


def generate_qrcode_pixels(
    text: str,
    *,
    version: int = 1,
    error_correction: int | None = None,
    box_size: int = 1,
    border: int = 1,
    flip_vertical: bool = True,
) -> list[list[bool]]:
    image = generate_qrcode_image(
        str(text),
        version=int(version),
        error_correction=(int(error_correction) if error_correction is not None else None),
        box_size=int(box_size),
        border=int(border),
    )
    return qrcode_image_to_pixels(image, flip_vertical=bool(flip_vertical))


def resolve_block_templates(*, black_template_id: int, white_template_id: int) -> tuple[BlockTemplate, BlockTemplate]:
    black_template = BlockHelper.get_template_by_id(int(black_template_id))
    if black_template is None:
        raise ValueError(f"未找到黑色方块模板: template_id={int(black_template_id)}")

    white_template = BlockHelper.get_template_by_id(int(white_template_id))
    if white_template is None:
        raise ValueError(f"未找到白色方块模板: template_id={int(white_template_id)}")

    return black_template, white_template


def pixels_to_blocks(
    *,
    pixels: list[list[bool]],
    black_template: BlockTemplate,
    white_template: BlockTemplate,
    global_scale: float,
    start_position_x: float,
    start_position_y: float,
    start_position_z: float,
    axis_mapping: Mapping[str, str] | None = None,
) -> list[BlockModel]:
    resolved_axis_mapping = dict(DEFAULT_AXIS_MAPPING)
    if axis_mapping is not None:
        resolved_axis_mapping.update(dict(axis_mapping))

    horizontal_axis_name = resolved_axis_mapping["horizontal"]
    vertical_axis_name = resolved_axis_mapping["vertical"]

    blocks: list[BlockModel] = []
    pixel_rows = int(len(pixels))
    pixel_columns = int(len(pixels[0])) if pixel_rows > 0 else 0

    for pixel_row_index in range(pixel_rows):
        for pixel_column_index in range(pixel_columns):
            is_black = bool(pixels[pixel_row_index][pixel_column_index])
            selected_template = black_template if is_black else white_template
            block_name_prefix = "QR_黑" if is_black else "QR_白"

            axis_increments = {"x": 0.0, "y": 0.0, "z": 0.0}
            axis_increments[str(horizontal_axis_name)] += float(pixel_column_index) * float(global_scale)
            axis_increments[str(vertical_axis_name)] += float(pixel_row_index) * float(global_scale)

            position_x = float(start_position_x) + float(axis_increments["x"])
            position_y = float(start_position_y) + float(axis_increments["y"])
            position_z = float(start_position_z) + float(axis_increments["z"])

            scale_x, scale_y, scale_z = BlockHelper.calculate_scale(selected_template, float(global_scale))

            blocks.append(
                BlockModel(
                    template_id=int(selected_template.template_id),
                    name=f"{block_name_prefix}_{pixel_column_index}_{pixel_row_index}",
                    position_x=float(position_x),
                    position_y=float(position_y),
                    position_z=float(position_z),
                    scale_x=float(scale_x),
                    scale_y=float(scale_y),
                    scale_z=float(scale_z),
                )
            )

    return blocks

