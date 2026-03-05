from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from engine.configs.specialized.ui_widget_configs import (
    PROGRESSBAR_COLOR_CODE_BY_HEX,
    PROGRESSBAR_COLOR_BLUE_HEX,
    PROGRESSBAR_COLOR_GREEN_HEX,
    PROGRESSBAR_COLOR_RED_HEX,
    PROGRESSBAR_COLOR_WHITE_HEX,
    PROGRESSBAR_COLOR_YELLOW_HEX,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .common import _parse_float_pair, _parse_int_pair


def _resolve_progressbar_color_code(*, color: str, color_code: int | None) -> int:
    if color_code is not None:
        return int(color_code)
    raw = str(color or "").strip()

    # 唯一真版本：仅接受五色 hex 或五色英文名/中文名（不再兼容旧 hex/旧别名/近似映射）
    name_to_hex = {
        "green": PROGRESSBAR_COLOR_GREEN_HEX,
        "red": PROGRESSBAR_COLOR_RED_HEX,
        "yellow": PROGRESSBAR_COLOR_YELLOW_HEX,
        "blue": PROGRESSBAR_COLOR_BLUE_HEX,
        "white": PROGRESSBAR_COLOR_WHITE_HEX,
        "绿色": PROGRESSBAR_COLOR_GREEN_HEX,
        "红色": PROGRESSBAR_COLOR_RED_HEX,
        "黄色": PROGRESSBAR_COLOR_YELLOW_HEX,
        "蓝色": PROGRESSBAR_COLOR_BLUE_HEX,
        "白色": PROGRESSBAR_COLOR_WHITE_HEX,
    }
    if not raw.startswith("#"):
        mapped_hex = name_to_hex.get(raw.lower()) if raw.isascii() else name_to_hex.get(raw)
        if mapped_hex is None:
            raise ValueError(
                f"不支持的颜色: {raw!r}（仅允许五色："
                f"{PROGRESSBAR_COLOR_GREEN_HEX}/{PROGRESSBAR_COLOR_WHITE_HEX}/{PROGRESSBAR_COLOR_YELLOW_HEX}/"
                f"{PROGRESSBAR_COLOR_BLUE_HEX}/{PROGRESSBAR_COLOR_RED_HEX}，或 green/white/yellow/blue/red，"
                f"或 绿色/白色/黄色/蓝色/红色）"
            )
        raw = str(mapped_hex)

    hex_upper = raw.upper()
    resolved = PROGRESSBAR_COLOR_CODE_BY_HEX.get(str(hex_upper))
    if resolved is None:
        raise ValueError(
            f"不支持的颜色 hex: {hex_upper!r}（仅允许: {sorted(PROGRESSBAR_COLOR_CODE_BY_HEX.keys())}）"
        )
    return int(resolved)


def _command_ui_recolor_progressbars(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers.misc.progress_bars import patch_progressbars_color_in_gil

    # 约定：green/绿色 对应默认色（样本中“未设置颜色”即为绿色，color_code=0）
    target_color_code = _resolve_progressbar_color_code(color=str(arguments.color), color_code=arguments.color_code)

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = patch_progressbars_color_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        target_color_code=target_color_code,
        allow_multi_occurrence=bool(arguments.allow_multi_occurrence),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台输出简要摘要
    print("=" * 80)
    print("进度条颜色写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- target_color_code: {report.get('target_color_code')}")
    print(f"- allow_multi_occurrence: {report.get('allow_multi_occurrence')}")
    print(f"- progressbars: {report.get('progressbar_total')}")
    print(f"- patched_blobs: {report.get('patched_blob_total')}")
    verify = report.get("verify")
    if isinstance(verify, dict):
        print(f"- verify_mismatch_total: {verify.get('mismatch_total')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_recolor_progressbars_full(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers.misc.progressbar_recolor_full import (
        recolor_progressbars_in_gil_by_reencoding_payload,
    )

    target_color_code = _resolve_progressbar_color_code(color=str(arguments.color), color_code=arguments.color_code)

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = recolor_progressbars_in_gil_by_reencoding_payload(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        target_color_code=int(target_color_code),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    verify = report.get("verify")
    mismatch_total = verify.get("mismatch_total") if isinstance(verify, dict) else None

    print("=" * 80)
    print("进度条颜色写回完成（full reencode）：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- target_color_code: {report.get('target_color_code')}")
    print(f"- progressbars: {report.get('progressbar_total')}")
    if mismatch_total is not None:
        print(f"- verify_mismatch_total: {mismatch_total}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_demo_progressbar_variants(arguments: argparse.Namespace) -> None:
    import json
    import tempfile

    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
    from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob
    from ugc_file_tools.ui_patchers.misc.progressbar_variants import (
        ProgressbarVariantPatch,
        apply_progressbar_variant_patches_in_gil,
    )
    from ugc_file_tools.ui.readable_dump import (
        extract_primary_guid as _extract_primary_guid,
        extract_ui_record_list as _extract_ui_record_list,
    )

    input_path = Path(arguments.input_gil_file).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    layout_guid = int(arguments.layout_guid) if arguments.layout_guid is not None else None
    limit = int(arguments.limit)
    if limit <= 0:
        raise ValueError("--limit 必须为正整数")
    hide_every = int(arguments.hide_every)
    if hide_every < 0:
        raise ValueError("--hide-every 必须为非负整数（0 表示不隐藏）")

    with tempfile.TemporaryDirectory() as temporary_directory:
        raw_json_path = Path(temporary_directory) / "ui.raw.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise TypeError("DLL dump-json 输出格式错误：期望为 dict")

    ui_record_list = _extract_ui_record_list(raw_dump_object)

    progressbar_guids: List[int] = []
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if not isinstance(guid_value, int):
            continue
        if _find_progressbar_binding_blob(record) is None:
            continue
        if layout_guid is not None:
            parent_value = record.get("504")
            if not isinstance(parent_value, int) or int(parent_value) != int(layout_guid):
                continue
        progressbar_guids.append(int(guid_value))

    progressbar_guids = sorted(set(progressbar_guids))
    if not progressbar_guids:
        raise RuntimeError("未找到任何进度条（请检查 layout_guid 是否正确）。")

    target_guids = progressbar_guids[:limit]

    shapes = [0, 1, 2]  # 横向/纵向/圆环
    styles = [0, 2, 3, 1]  # 百分比/当前值/真实比例/不显示
    colors = [1, 2, 3, 4, 0]  # 红/黄/蓝/白/默认
    current_names = ["进度0", "进度50", "进度100"]
    min_name = "进度0"
    max_name = "进度100"

    patches: List[ProgressbarVariantPatch] = []
    for index, guid in enumerate(target_guids):
        visible: Optional[bool] = None
        if hide_every > 0:
            visible = (int(index) % int(hide_every)) != 0
        patches.append(
            ProgressbarVariantPatch(
                guid=int(guid),
                shape_code=int(shapes[index % len(shapes)]),
                style_code=int(styles[index % len(styles)]),
                color_code=int(colors[index % len(colors)]),
                group_id=101,
                current_name=str(current_names[index % len(current_names)]),
                min_name=str(min_name),
                max_name=str(max_name),
                visible=visible,
            )
        )

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = apply_progressbar_variant_patches_in_gil(
        input_gil_file_path=input_path,
        output_gil_file_path=output_gil_path,
        patches=patches,
        restrict_layout_guid=layout_guid,
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("进度条差异化演示写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- layout_guid: {report.get('restrict_layout_guid')}")
    print(f"- requested: {report.get('requested_patch_total')}")
    print(f"- patched: {report.get('patched_total')}")
    verify = report.get("verify")
    if isinstance(verify, dict):
        print(f"- verify_ok: {verify.get('ok')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_add_progressbars_corners(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers import add_progressbars_to_corners

    corners_text = str(arguments.corners or "").strip()
    corner_list = [part.strip() for part in corners_text.split(",") if part.strip() != ""]
    if not corner_list:
        raise ValueError("corners 不能为空，例如: top-left,top-right")

    canvas_width, canvas_height = _parse_int_pair(arguments.canvas_size)
    margin_x, margin_y = _parse_float_pair(arguments.margin)

    parent_guid = int(arguments.parent_guid) if arguments.parent_guid is not None else None

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = add_progressbars_to_corners(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        corners=corner_list,
        canvas_size=(float(canvas_width), float(canvas_height)),
        margin=(float(margin_x), float(margin_y)),
        parent_guid=parent_guid,
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("进度条新增完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- parent_guid: {report.get('parent_guid')}")
    print(f"- added_total: {report.get('added_total')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_create_progressbar_template_and_place(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers import create_progressbar_template_and_place_in_layout

    pc_pos = _parse_float_pair(arguments.pc_pos)
    pc_size = _parse_float_pair(arguments.pc_size)
    mobile_pos = _parse_float_pair(arguments.mobile_pos)
    mobile_size = _parse_float_pair(arguments.mobile_size)

    instance_name_text = str(arguments.instance_name or "").strip()
    instance_name = instance_name_text if instance_name_text != "" else None

    create_layout_name_text = str(arguments.create_layout_name or "").strip()
    create_layout_name = create_layout_name_text if create_layout_name_text != "" else None

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = create_progressbar_template_and_place_in_layout(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        template_name=str(arguments.template_name),
        library_root_guid=int(arguments.library_root_guid),
        target_layout_guid=int(arguments.layout_guid) if arguments.layout_guid is not None else None,
        create_layout_name=create_layout_name,
        base_layout_guid_for_create=int(arguments.base_layout_guid) if arguments.base_layout_guid is not None else None,
        instance_name=instance_name,
        pc_canvas_position=(float(pc_pos[0]), float(pc_pos[1])),
        pc_size=(float(pc_size[0]), float(pc_size[1])),
        mobile_canvas_position=(float(mobile_pos[0]), float(mobile_pos[1])),
        mobile_size=(float(mobile_size[0]), float(mobile_size[1])),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created_template = report.get("created_template") if isinstance(report, dict) else None
    placed_instance = report.get("placed_instance") if isinstance(report, dict) else None
    created_layout = report.get("created_layout") if isinstance(report, dict) else None

    print("=" * 80)
    print("进度条模板 + 布局引用写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    if isinstance(created_layout, dict):
        print(f"- created_layout_guid: {created_layout.get('guid')} ({created_layout.get('name')})")
    if isinstance(created_template, dict):
        print(f"- template_entry_guid: {created_template.get('entry_guid')}")
        print(f"- template_root_guid: {created_template.get('template_root_guid')}")
        print(f"- template_name: {created_template.get('name')}")
    if isinstance(placed_instance, dict):
        print(f"- instance_guid: {placed_instance.get('guid')}")
        print(f"- layout_guid: {placed_instance.get('layout_guid')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_create_progressbar_template_and_place_many(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers import create_progressbar_template_and_place_many_in_layout

    pc_pos = _parse_float_pair(arguments.pc_pos)
    pc_step = _parse_float_pair(arguments.pc_step)
    pc_size = _parse_float_pair(arguments.pc_size)
    mobile_pos = _parse_float_pair(arguments.mobile_pos)
    mobile_step = _parse_float_pair(arguments.mobile_step)
    mobile_size = _parse_float_pair(arguments.mobile_size)

    instance_name_prefix_text = str(arguments.instance_name_prefix or "").strip()
    instance_name_prefix = instance_name_prefix_text if instance_name_prefix_text != "" else None

    create_layout_name_text = str(arguments.create_layout_name or "").strip()
    create_layout_name = create_layout_name_text if create_layout_name_text != "" else None

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = create_progressbar_template_and_place_many_in_layout(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        template_name=str(arguments.template_name),
        library_root_guid=int(arguments.library_root_guid),
        target_layout_guid=int(arguments.layout_guid) if arguments.layout_guid is not None else None,
        create_layout_name=create_layout_name,
        base_layout_guid_for_create=int(arguments.base_layout_guid) if arguments.base_layout_guid is not None else None,
        instance_name_prefix=instance_name_prefix,
        instance_total=int(arguments.instance_total),
        pc_canvas_position=(float(pc_pos[0]), float(pc_pos[1])),
        pc_step=(float(pc_step[0]), float(pc_step[1])),
        pc_size=(float(pc_size[0]), float(pc_size[1])),
        mobile_canvas_position=(float(mobile_pos[0]), float(mobile_pos[1])),
        mobile_step=(float(mobile_step[0]), float(mobile_step[1])),
        mobile_size=(float(mobile_size[0]), float(mobile_size[1])),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created_template = report.get("created_template") if isinstance(report, dict) else None
    created_layout = report.get("created_layout") if isinstance(report, dict) else None

    print("=" * 80)
    print("进度条自定义模板 + 布局多实例写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    if isinstance(created_layout, dict):
        print(f"- created_layout_guid: {created_layout.get('guid')} ({created_layout.get('name')})")
    if isinstance(created_template, dict):
        print(f"- template_entry_guid: {created_template.get('entry_guid')}")
        print(f"- template_root_guid: {created_template.get('template_root_guid')}")
        print(f"- template_name: {created_template.get('name')}")
    print(f"- placed_instance_total: {report.get('placed_instance_total')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def register_ui_progressbars_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    recolor_progressbars_parser = ui_subparsers.add_parser(
        "recolor-progressbars",
        help="将存档内所有进度条控件的颜色批量改为指定颜色，并输出新的 .gil（采用二进制等长补丁写回）。",
    )
    recolor_progressbars_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    recolor_progressbars_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    recolor_progressbars_parser.add_argument(
        "--color",
        dest="color",
        default=PROGRESSBAR_COLOR_GREEN_HEX,
        help=(
            "目标颜色（唯一真版本）：五色 hex（#92CD21/#E2DBCE/#F3C330/#36F3F3/#F47B7B）"
            "或 green/white/yellow/blue/red 或 绿色/白色/黄色/蓝色/红色。"
        ),
    )
    recolor_progressbars_parser.add_argument(
        "--color-code",
        dest="color_code",
        type=int,
        default=None,
        help="可选：直接指定颜色枚举值（覆盖 --color）。",
    )
    recolor_progressbars_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验所有进度条 color_code 是否等于目标值（不一致则在 report 中体现）。",
    )
    recolor_progressbars_parser.add_argument(
        "--allow-multi-occurrence",
        dest="allow_multi_occurrence",
        action="store_true",
        help="可选（危险）：允许同一 progressbar binding blob bytes 在 .gil 中出现多次时也写回；会对所有出现位置做等长替换，最终以 verify dump 为准。",
    )
    recolor_progressbars_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    recolor_progressbars_parser.set_defaults(entrypoint=_command_ui_recolor_progressbars)

    recolor_progressbars_full_parser = ui_subparsers.add_parser(
        "recolor-progressbars-full",
        help="将存档内所有进度条控件的颜色批量改为指定颜色，并输出新的 .gil（通过 payload 重编码写回，允许插入缺失字段）。",
    )
    recolor_progressbars_full_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    recolor_progressbars_full_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    recolor_progressbars_full_parser.add_argument(
        "--color",
        dest="color",
        default=PROGRESSBAR_COLOR_GREEN_HEX,
        help=(
            "目标颜色（唯一真版本）：五色 hex（#92CD21/#E2DBCE/#F3C330/#36F3F3/#F47B7B）"
            "或 green/white/yellow/blue/red 或 绿色/白色/黄色/蓝色/红色。"
        ),
    )
    recolor_progressbars_full_parser.add_argument(
        "--color-code",
        dest="color_code",
        type=int,
        default=None,
        help="可选：直接指定颜色枚举值（覆盖 --color）。",
    )
    recolor_progressbars_full_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验所有进度条 color_code 是否等于目标值。",
    )
    recolor_progressbars_full_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    recolor_progressbars_full_parser.set_defaults(entrypoint=_command_ui_recolor_progressbars_full)

    demo_variants_parser = ui_subparsers.add_parser(
        "demo-progressbar-variants",
        help="对一批进度条写入“形状/样式/颜色/绑定/可见性”的差异化配置，便于用 dump 直观看到可控性。",
    )
    demo_variants_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    demo_variants_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    demo_variants_parser.add_argument(
        "--layout-guid",
        dest="layout_guid",
        type=int,
        default=None,
        help="可选：仅对该布局 root GUID 下的进度条做演示（record['504']==layout_guid）。不填则对全存档进度条取前 N 个。",
    )
    demo_variants_parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=24,
        help="取前多少个进度条写入差异化配置（按 guid 升序）。默认 24。",
    )
    demo_variants_parser.add_argument(
        "--hide-every",
        dest="hide_every",
        type=int,
        default=7,
        help="每隔 N 个进度条设置为不可见（初始可见性 flag=0）；0 表示不隐藏。默认 7。",
    )
    demo_variants_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查 patched guid 是否存在。",
    )
    demo_variants_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    demo_variants_parser.set_defaults(entrypoint=_command_ui_demo_progressbar_variants)

    add_progressbars_parser = ui_subparsers.add_parser(
        "add-progressbars-corners",
        help="在进度条父组下新增进度条控件（复制模板）并写回新 .gil；默认添加到左上/右上角。",
    )
    add_progressbars_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    add_progressbars_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    add_progressbars_parser.add_argument(
        "--corners",
        dest="corners",
        default="top-left,top-right",
        help="要添加到哪些角落（逗号分隔）：top-left,top-right,bottom-left,bottom-right；默认 top-left,top-right",
    )
    add_progressbars_parser.add_argument(
        "--canvas-size",
        dest="canvas_size",
        default="1600,900",
        help="Canvas 尺寸（用于角落定位），格式 '宽,高'，默认 1600,900",
    )
    add_progressbars_parser.add_argument(
        "--margin",
        dest="margin",
        default="20,20",
        help="角落边距（控件中心会额外加上半尺寸），格式 'x,y'，默认 20,20",
    )
    add_progressbars_parser.add_argument(
        "--parent-guid",
        dest="parent_guid",
        type=int,
        default=None,
        help="可选：进度条父组 GUID（不填则尝试从现有进度条 record 的 504 字段推断）。",
    )
    add_progressbars_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查新增 GUID 是否存在。",
    )
    add_progressbars_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    add_progressbars_parser.set_defaults(entrypoint=_command_ui_add_progressbars_corners)

    create_template_and_place_parser = ui_subparsers.add_parser(
        "create-progressbar-template-and-place",
        help="在模板库中新建“进度条自定义模板”（条目+template_root），并在指定布局（或新建布局）中放置一个无模板实例，然后写回新 .gil。",
    )
    create_template_and_place_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    create_template_and_place_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    create_template_and_place_parser.add_argument(
        "--template-name",
        dest="template_name",
        required=True,
        help="模板名称（控件组库条目显示名）。",
    )
    create_template_and_place_parser.add_argument(
        "--library-root-guid",
        dest="library_root_guid",
        type=int,
        default=1073741838,
        help="控件组库根节点 GUID（test5/test6 为 1073741838）。",
    )
    create_template_and_place_parser.add_argument(
        "--layout-guid",
        dest="layout_guid",
        type=int,
        default=None,
        help="可选：放置到哪个布局 root GUID（与 --create-layout-name 二选一）。",
    )
    create_template_and_place_parser.add_argument(
        "--create-layout-name",
        dest="create_layout_name",
        default="",
        help="可选：创建一个新布局并放置实例（与 --layout-guid 二选一）。",
    )
    create_template_and_place_parser.add_argument(
        "--base-layout-guid",
        dest="base_layout_guid",
        type=int,
        default=None,
        help="可选：创建新布局时，复制哪个布局 root 作为模板（不填则自动选择一个“自定义布局”）。",
    )
    create_template_and_place_parser.add_argument(
        "--instance-name",
        dest="instance_name",
        default="",
        help="可选：实例名称（不填则复用 --template-name）。",
    )
    create_template_and_place_parser.add_argument(
        "--pc-pos",
        dest="pc_pos",
        default="1,1",
        help="电脑端画布坐标（左下角原点），格式 'x,y'，默认 1,1",
    )
    create_template_and_place_parser.add_argument(
        "--pc-size",
        dest="pc_size",
        default="200,200",
        help="电脑端尺寸，格式 'w,h'，默认 200,200",
    )
    create_template_and_place_parser.add_argument(
        "--mobile-pos",
        dest="mobile_pos",
        default="5,5",
        help="手机端画布坐标（左下角原点），格式 'x,y'，默认 5,5",
    )
    create_template_and_place_parser.add_argument(
        "--mobile-size",
        dest="mobile_size",
        default="10,10",
        help="手机端尺寸，格式 'w,h'，默认 10,10",
    )
    create_template_and_place_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查新增 GUID 是否存在。",
    )
    create_template_and_place_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    create_template_and_place_parser.set_defaults(entrypoint=_command_ui_create_progressbar_template_and_place)

    create_template_and_place_many_parser = ui_subparsers.add_parser(
        "create-progressbar-template-and-place-many",
        help="在模板库中新建“进度条自定义模板”（条目+template_root），并在指定布局（或新建布局）中放置多个无模板实例，然后写回新 .gil。",
    )
    create_template_and_place_many_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    create_template_and_place_many_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    create_template_and_place_many_parser.add_argument(
        "--template-name",
        dest="template_name",
        required=True,
        help="模板名称（控件组库条目显示名）。",
    )
    create_template_and_place_many_parser.add_argument(
        "--library-root-guid",
        dest="library_root_guid",
        type=int,
        default=1073741838,
        help="控件组库根节点 GUID（test5/test6 为 1073741838）。",
    )
    create_template_and_place_many_parser.add_argument(
        "--layout-guid",
        dest="layout_guid",
        type=int,
        default=None,
        help="可选：放置到哪个布局 root GUID（与 --create-layout-name 二选一）。",
    )
    create_template_and_place_many_parser.add_argument(
        "--create-layout-name",
        dest="create_layout_name",
        default="",
        help="可选：创建一个新布局并放置实例（与 --layout-guid 二选一）。",
    )
    create_template_and_place_many_parser.add_argument(
        "--base-layout-guid",
        dest="base_layout_guid",
        type=int,
        default=None,
        help="可选：创建新布局时，复制哪个布局 root 作为模板（不填则自动选择一个“自定义布局”）。",
    )
    create_template_and_place_many_parser.add_argument(
        "--instance-name-prefix",
        dest="instance_name_prefix",
        default="",
        help="可选：实例名称前缀（不填则使用 --template-name）。实例会命名为 '<prefix>1','<prefix>2',...。",
    )
    create_template_and_place_many_parser.add_argument(
        "--instance-total",
        dest="instance_total",
        type=int,
        default=3,
        help="要放置多少个实例，默认 3。",
    )
    create_template_and_place_many_parser.add_argument(
        "--pc-pos",
        dest="pc_pos",
        default="100,100",
        help="电脑端第 1 个实例的画布坐标（左下角原点），格式 'x,y'，默认 100,100",
    )
    create_template_and_place_many_parser.add_argument(
        "--pc-step",
        dest="pc_step",
        default="0,120",
        help="电脑端实例坐标步进（每个实例相对前一个偏移），格式 'dx,dy'，默认 0,120",
    )
    create_template_and_place_many_parser.add_argument(
        "--pc-size",
        dest="pc_size",
        default="200,50",
        help="电脑端尺寸，格式 'w,h'，默认 200,50",
    )
    create_template_and_place_many_parser.add_argument(
        "--mobile-pos",
        dest="mobile_pos",
        default="100,100",
        help="手机端第 1 个实例的画布坐标（左下角原点），格式 'x,y'，默认 100,100",
    )
    create_template_and_place_many_parser.add_argument(
        "--mobile-step",
        dest="mobile_step",
        default="0,100",
        help="手机端实例坐标步进（每个实例相对前一个偏移），格式 'dx,dy'，默认 0,100",
    )
    create_template_and_place_many_parser.add_argument(
        "--mobile-size",
        dest="mobile_size",
        default="200,50",
        help="手机端尺寸，格式 'w,h'，默认 200,50",
    )
    create_template_and_place_many_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查新增 GUID 是否存在。",
    )
    create_template_and_place_many_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    create_template_and_place_many_parser.set_defaults(
        entrypoint=_command_ui_create_progressbar_template_and_place_many
    )


