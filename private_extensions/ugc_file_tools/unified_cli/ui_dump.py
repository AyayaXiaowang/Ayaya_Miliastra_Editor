from __future__ import annotations

import argparse
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .common import _parse_int_pair


def _command_ui_dump(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json

    output_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(arguments.input_gil_file, str(output_path))


def _command_ui_dump_readable(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui.readable_dump import build_readable_ui_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    readable_object = build_readable_ui_dump(raw_dump_object)
    Path(output_json_file_path).write_text(
        json.dumps(readable_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_ui_dump_textboxes(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui.readable_dump import build_textbox_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    textbox_object = build_textbox_dump(
        raw_dump_object,
        include_transform=bool(arguments.with_transform),
    )
    Path(output_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_file_path).write_text(
        json.dumps(textbox_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_ui_dump_controls(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui.readable_dump import build_control_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    control_object = build_control_dump(
        raw_dump_object,
        include_name_candidates=bool(arguments.with_name_candidates),
    )
    Path(output_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_file_path).write_text(
        json.dumps(control_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_ui_dump_progressbars(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui_parsers.progress_bars import build_progressbar_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    canvas_width, canvas_height = _parse_int_pair(arguments.canvas_size)
    progressbar_object = build_progressbar_dump(
        raw_dump_object,
        canvas_size=(float(canvas_width), float(canvas_height)),
        include_raw_binding_blob_hex=bool(arguments.with_raw_blob),
    )

    Path(output_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_file_path).write_text(
        json.dumps(progressbar_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_ui_dump_item_displays(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui_parsers.item_displays import build_item_display_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    canvas_width, canvas_height = _parse_int_pair(arguments.canvas_size)
    item_display_object = build_item_display_dump(
        raw_dump_object,
        canvas_size=(float(canvas_width), float(canvas_height)),
        include_raw_binding_blob_hex=bool(arguments.with_raw_blob),
    )

    Path(output_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_file_path).write_text(
        json.dumps(item_display_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _command_ui_dump_layouts(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui_parsers.layouts import build_layout_dump

    input_gil_file_path = arguments.input_gil_file
    output_json_path = resolve_output_file_path_in_out_dir(Path(arguments.output_json_file))
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_file_path = str(output_json_path)
    raw_json_file_path = arguments.raw_json_file

    if raw_json_file_path is None:
        raw_json_file_path = str(output_json_path.with_suffix(".raw.json"))
    else:
        raw_json_path = resolve_output_file_path_in_out_dir(Path(raw_json_file_path))
        raw_json_path.parent.mkdir(parents=True, exist_ok=True)
        raw_json_file_path = str(raw_json_path)

    Path(raw_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    dump_gil_to_json(input_gil_file_path, raw_json_file_path)

    raw_dump_text = Path(raw_json_file_path).read_text(encoding="utf-8")
    raw_dump_object = json.loads(raw_dump_text)

    layout_object = build_layout_dump(raw_dump_object)

    Path(output_json_file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json_file_path).write_text(
        json.dumps(layout_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def register_ui_dump_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    dump_parser = ui_subparsers.add_parser("dump-json", help="将 .gil 导出为 JSON（只读）")
    dump_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_parser.set_defaults(entrypoint=_command_ui_dump)

    dump_readable_parser = ui_subparsers.add_parser(
        "dump-readable",
        help="将 .gil 导出为“可读的 UI JSON”（提取 ID/名字/RectTransform/可见标记等）",
    )
    dump_readable_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_readable_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_readable_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_readable_parser.set_defaults(entrypoint=_command_ui_dump_readable)

    dump_textboxes_parser = ui_subparsers.add_parser(
        "dump-textboxes",
        help="只导出 TextBox（可用于 update-content）的 JSON：guid/name/text（可选附带 transform）",
    )
    dump_textboxes_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_textboxes_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_textboxes_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_textboxes_parser.add_argument(
        "--with-transform",
        dest="with_transform",
        action="store_true",
        help="可选：额外输出 RectTransform（位置/大小/锚点/轴心/缩放）用于定位",
    )
    dump_textboxes_parser.set_defaults(entrypoint=_command_ui_dump_textboxes)

    dump_controls_parser = ui_subparsers.add_parser(
        "dump-controls",
        help="导出所有 UI 控件的 GUID（附带 index_id/名称，可选 name_candidates；并尝试推断模板资产ID）",
    )
    dump_controls_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_controls_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_controls_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_controls_parser.add_argument(
        "--with-name-candidates",
        dest="with_name_candidates",
        action="store_true",
        help="可选：输出 name_candidates（更完整但更大）",
    )
    dump_controls_parser.set_defaults(entrypoint=_command_ui_dump_controls)

    dump_progressbars_parser = ui_subparsers.add_parser(
        "dump-progressbars",
        help="解析并导出进度条控件：位置/大小/形状/样式/颜色/变量绑定（current/min/max）。",
    )
    dump_progressbars_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_progressbars_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_progressbars_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_progressbars_parser.add_argument(
        "--canvas-size",
        dest="canvas_size",
        default="1600,900",
        help="可选：Canvas 尺寸（用于将 anchored_position 还原为 UI 设计坐标），格式 '宽,高'，默认 1600,900",
    )
    dump_progressbars_parser.add_argument(
        "--with-raw-blob",
        dest="with_raw_blob",
        action="store_true",
        help="可选：输出绑定 blob 的 hex（调试用，体积较大）",
    )
    dump_progressbars_parser.set_defaults(entrypoint=_command_ui_dump_progressbars)

    dump_item_displays_parser = ui_subparsers.add_parser(
        "dump-item-displays",
        help="解析并导出道具展示控件：类型/按键映射/变量绑定（部分字段仍在逆向中）。",
    )
    dump_item_displays_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_item_displays_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_item_displays_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_item_displays_parser.add_argument(
        "--canvas-size",
        dest="canvas_size",
        default="1600,900",
        help="可选：Canvas 尺寸（用于将 anchored_position 还原为 UI 设计坐标），格式 '宽,高'，默认 1600,900",
    )
    dump_item_displays_parser.add_argument(
        "--with-raw-blob",
        dest="with_raw_blob",
        action="store_true",
        help="可选：输出绑定 blob 的 hex（调试用，体积较大）",
    )
    dump_item_displays_parser.set_defaults(entrypoint=_command_ui_dump_item_displays)

    dump_layouts_parser = ui_subparsers.add_parser(
        "dump-layouts",
        help="导出布局注册表与每个布局的固有子控件列表（含布局层面的可见性覆盖字段）。",
    )
    dump_layouts_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    dump_layouts_parser.add_argument("output_json_file", help="输出 .json 文件路径")
    dump_layouts_parser.add_argument(
        "--raw-json",
        dest="raw_json_file",
        help="可选：保存 DLL 原始 dump-json 输出的路径（默认与输出同名 .raw.json）",
    )
    dump_layouts_parser.set_defaults(entrypoint=_command_ui_dump_layouts)


