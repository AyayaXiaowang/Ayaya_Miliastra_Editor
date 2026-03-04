from __future__ import annotations

import argparse
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .common import _parse_float_pair, _parse_int_pair


def _command_ui_add_textbox(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers.misc.textboxes import add_textbox_to_gil

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    add_textbox_to_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        parent_guid=int(arguments.parent_guid),
        name=str(arguments.name),
        content=str(arguments.content),
        canvas_position=(float(arguments.position_x), float(arguments.position_y)),
        size=(float(arguments.width), float(arguments.height)),
    )


def _command_ui_image_to_textboxes(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers.misc.textboxes import write_image_as_textboxes_in_gil

    resolution_x, resolution_y = _parse_int_pair(arguments.resolution)
    position_x, position_y = _parse_float_pair(arguments.position)

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    write_image_as_textboxes_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        parent_guid=int(arguments.parent_guid),
        image_file_path=Path(arguments.image_file),
        resolution=(int(resolution_x), int(resolution_y)),
        position_top_left=(float(position_x), float(position_y)),
        text_box_height=float(arguments.text_box_height),
        grain_size=int(arguments.grain_size),
    )


def _command_ui_update_textbox_content(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers.misc.textboxes import update_textbox_content_in_gil

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    update_textbox_content_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        guid=int(arguments.text_box_guid),
        content=str(arguments.content),
    )


def register_ui_textboxes_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    add_text_parser = ui_subparsers.add_parser("add-textbox", help="向 .gil 追加一个 TextBox")
    add_text_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    add_text_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    add_text_parser.add_argument("--parent-guid", dest="parent_guid", type=int, required=True, help="父组 GUID")
    add_text_parser.add_argument("--name", dest="name", required=True, help="TextBox 名称（UTF-8）")
    add_text_parser.add_argument("--content", dest="content", required=True, help="TextBox 文本内容（UTF-8 / 富文本）")
    add_text_parser.add_argument("--x", dest="position_x", type=float, default=0.0, help="位置 X")
    add_text_parser.add_argument("--y", dest="position_y", type=float, default=0.0, help="位置 Y")
    add_text_parser.add_argument("--width", dest="width", type=float, default=100.0, help="宽度")
    add_text_parser.add_argument("--height", dest="height", type=float, default=40.0, help="高度")
    add_text_parser.set_defaults(entrypoint=_command_ui_add_textbox)

    image_parser = ui_subparsers.add_parser("image-to-textboxes", help="将图片转为富文本 TextBox 网格并写入 .gil")
    image_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    image_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    image_parser.add_argument("image_file", help="图片文件路径（png/jpg 等）")
    image_parser.add_argument("--resolution", required=True, help="图片分辨率：'宽,高'，例如 560,315")
    image_parser.add_argument("--position", required=True, help="起始位置：'x,y'，例如 0,157")
    image_parser.add_argument("--text-box-height", dest="text_box_height", type=float, default=25.0, help="每个 TextBox 高度")
    image_parser.add_argument("--grain-size", dest="grain_size", type=int, default=5, help="像素粒度（越大越粗糙、TextBox 越少）")
    image_parser.add_argument("--parent-guid", dest="parent_guid", type=int, required=True, help="父组 GUID")
    image_parser.set_defaults(entrypoint=_command_ui_image_to_textboxes)

    update_parser = ui_subparsers.add_parser("update-content", help="按 GUID 更新一个 TextBox 的内容")
    update_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    update_parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    update_parser.add_argument("--guid", dest="text_box_guid", type=int, required=True, help="TextBox GUID")
    update_parser.add_argument("--content", dest="content", required=True, help="新的文本内容（UTF-8 / 富文本）")
    update_parser.set_defaults(entrypoint=_command_ui_update_textbox_content)


