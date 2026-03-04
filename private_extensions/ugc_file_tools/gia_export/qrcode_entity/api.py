from __future__ import annotations

from pathlib import Path

from ugc_file_tools.gia.container import wrap_gia_container


def build_qrcode_entity_gia_proto_bytes(
    *,
    text: str,
    black_template_id: int,
    white_template_id: int,
    global_scale: float,
    start_position_x: float,
    start_position_y: float,
    start_position_z: float,
    entity_id_start: int,
) -> bytes:
    """
    构造二维码方块墙的 GIACollection protobuf bytes（不包含 `.gia` 容器 header/footer）。

    说明：
    - 依赖 `qrcode` + `Pillow` 生成二维码像素；
    - 依赖 `protobuf` 生成 message bytes；
    - 不在此处做 try/except：缺依赖/参数错误直接抛错（fail-fast）。
    """
    from .block_assembler import BlockAssembler
    from .qrcode_helper import generate_qrcode_pixels, pixels_to_blocks, resolve_block_templates

    pixels = generate_qrcode_pixels(str(text))
    black_template, white_template = resolve_block_templates(
        black_template_id=int(black_template_id),
        white_template_id=int(white_template_id),
    )
    blocks = pixels_to_blocks(
        pixels=pixels,
        black_template=black_template,
        white_template=white_template,
        global_scale=float(global_scale),
        start_position_x=float(start_position_x),
        start_position_y=float(start_position_y),
        start_position_z=float(start_position_z),
    )
    assembler = BlockAssembler(entity_id_start=int(entity_id_start))
    return assembler.assemble(blocks)


def build_qrcode_entity_gia_file_bytes(
    *,
    text: str,
    black_template_id: int,
    white_template_id: int,
    global_scale: float,
    start_position_x: float,
    start_position_y: float,
    start_position_z: float,
    entity_id_start: int,
) -> bytes:
    """构造完整 `.gia` 文件 bytes（包含容器 header/footer）。"""
    proto_bytes = build_qrcode_entity_gia_proto_bytes(
        text=str(text),
        black_template_id=int(black_template_id),
        white_template_id=int(white_template_id),
        global_scale=float(global_scale),
        start_position_x=float(start_position_x),
        start_position_y=float(start_position_y),
        start_position_z=float(start_position_z),
        entity_id_start=int(entity_id_start),
    )
    return wrap_gia_container(proto_bytes)


def write_qrcode_entity_gia_file(
    *,
    output_gia_path: Path,
    text: str,
    black_template_id: int,
    white_template_id: int,
    global_scale: float,
    start_position_x: float,
    start_position_y: float,
    start_position_z: float,
    entity_id_start: int,
) -> Path:
    """写出二维码实体 `.gia` 到指定路径并返回写入后的绝对路径。"""
    out_path = Path(output_gia_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(
        build_qrcode_entity_gia_file_bytes(
            text=str(text),
            black_template_id=int(black_template_id),
            white_template_id=int(white_template_id),
            global_scale=float(global_scale),
            start_position_x=float(start_position_x),
            start_position_y=float(start_position_y),
            start_position_z=float(start_position_z),
            entity_id_start=int(entity_id_start),
        )
    )
    return out_path

