from __future__ import annotations

import argparse
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .common import _parse_float_pair


def _command_ui_import_web_template(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers import import_web_ui_control_group_template_to_gil_layout
    from engine.utils.cache.cache_paths import get_ui_guid_registry_cache_file
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_guid_registry import (
        try_resolve_workspace_root_and_package_id_from_template_json_path,
    )

    pc_canvas_size = _parse_float_pair(str(arguments.pc_canvas_size))
    mobile_canvas_size = _parse_float_pair(str(arguments.mobile_canvas_size))

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)

    ui_guid_registry_file_path = None
    if getattr(arguments, "ui_guid_registry", None) is not None:
        ui_guid_registry_file_path = Path(arguments.ui_guid_registry).resolve()
    else:
        # 约定：若 template_json 位于项目存档目录下，则自动使用运行时缓存中的 registry：
        #   assets/资源库/项目存档/<package_id>/管理配置/**/<xxx>.ui_bundle.json
        # -> <runtime_cache>/ui_artifacts/<package_id>/ui_guid_registry.json
        template_path = Path(arguments.template_json_file).resolve()
        resolved = try_resolve_workspace_root_and_package_id_from_template_json_path(template_path)
        if resolved is not None:
            workspace_root, package_id = resolved
            ui_guid_registry_file_path = get_ui_guid_registry_cache_file(workspace_root, package_id).resolve()

    report = import_web_ui_control_group_template_to_gil_layout(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        template_json_file_path=Path(arguments.template_json_file),
        target_layout_guid=(int(arguments.layout_guid) if arguments.layout_guid is not None else None),
        new_layout_name=(str(arguments.layout_name) if arguments.layout_name is not None else None),
        base_layout_guid=(int(arguments.base_layout_guid) if arguments.base_layout_guid is not None else None),
        empty_layout=bool(arguments.empty_layout),
        clone_children=not bool(arguments.empty_layout),
        pc_canvas_size=pc_canvas_size,
        mobile_canvas_size=mobile_canvas_size,
        enable_progressbars=not bool(arguments.skip_progressbars),
        enable_textboxes=not bool(arguments.skip_textboxes),
        textbox_template_gil_file_path=(
            Path(arguments.textbox_template_gil) if arguments.textbox_template_gil is not None else None
        ),
        item_display_template_gil_file_path=(
            Path(arguments.item_display_template_gil) if arguments.item_display_template_gil is not None else None
        ),
        verify_with_dll_dump=bool(arguments.verify),
        ui_guid_registry_file_path=ui_guid_registry_file_path,
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    layout_info = report.get("layout") if isinstance(report, dict) else None
    layout_guid = None
    created_layout = None
    if isinstance(layout_info, dict):
        layout_guid = layout_info.get("target_layout_guid")
        created_layout = layout_info.get("created_layout")
        layout_index = layout_info.get("layout_index")
    else:
        layout_index = None

    result = report.get("result") if isinstance(report, dict) else None

    print("=" * 80)
    print("Web UI 模板导入完成（当前阶段：进度条/色块 + 文本框 + 道具展示）：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- template_json: {report.get('template_json')}")
    print(f"- layout_guid: {layout_guid}")
    print(f"- layout_index: {layout_index}")
    if isinstance(created_layout, dict):
        print(f"- created_layout_name: {created_layout.get('name')}")
        print(f"- cloned_children_total: {created_layout.get('cloned_children_total')}")
    if isinstance(result, dict):
        print(f"- imported_progressbars_total: {result.get('imported_progressbars_total')}")
        print(f"- imported_textboxes_total: {result.get('imported_textboxes_total')}")
        print(f"- imported_item_displays_total: {result.get('imported_item_displays_total')}")
        print(f"- skipped_widgets_total: {result.get('skipped_widgets_total')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def register_ui_web_import_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    parser = ui_subparsers.add_parser(
        "import-web-template",
        help="将 Web Workbench 导出的 UIControlGroupTemplate JSON 写入 .gil（当前阶段：进度条/色块 + 文本框 + 道具展示）",
    )
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser.add_argument("output_gil_file", help="输出 .gil 文件路径")
    parser.add_argument(
        "template_json_file",
        help="Web Workbench 导出的 JSON 文件路径（支持 UIControlGroupTemplate 或 UILayout bundle）。",
    )
    parser.add_argument(
        "--ui-guid-registry",
        dest="ui_guid_registry",
        default=None,
        help=(
            "可选：指定 UIKey→GUID 注册表路径（ui_guid_registry.json）。"
            "若不传且 template_json 位于项目存档目录下，则会自动推断为："
            "<runtime_cache>/ui_artifacts/<package_id>/ui_guid_registry.json"
        ),
    )

    parser.add_argument("--layout-guid", dest="layout_guid", type=int, default=None, help="目标布局 GUID（不为空则不新建布局）")
    parser.add_argument("--layout-name", dest="layout_name", default=None, help="新布局名称（仅在未传 --layout-guid 时生效）")
    parser.add_argument("--base-layout-guid", dest="base_layout_guid", type=int, default=None, help="基底布局 GUID（仅在新建布局时生效）")
    parser.add_argument("--empty-layout", dest="empty_layout", action="store_true", help="创建空布局（不克隆固有 children）")

    parser.add_argument("--pc-canvas-size", dest="pc_canvas_size", default="1600,900", help="电脑画布尺寸：'宽,高'")
    parser.add_argument("--mobile-canvas-size", dest="mobile_canvas_size", default="1280,720", help="手机画布尺寸：'宽,高'")

    parser.add_argument("--skip-progressbars", dest="skip_progressbars", action="store_true", help="跳过进度条（一般不建议）")
    parser.add_argument("--skip-textboxes", dest="skip_textboxes", action="store_true", help="跳过文本框导入（默认会导入）。")
    parser.add_argument(
        "--enable-textboxes",
        dest="skip_textboxes",
        action="store_false",
        help="兼容参数：显式启用文本框导入（默认启用）。",
    )
    parser.set_defaults(skip_textboxes=False)
    parser.add_argument(
        "--textbox-template-gil",
        dest="textbox_template_gil",
        default=None,
        help=(
            "可选：提供一份“包含 TextBox 控件”的样本 .gil，作为 TextBox record 模板来源。"
            "当 base .gil 内不存在 TextBox 且 ui_schema_library 未命中模板时，需要提供一次用于沉淀；后续可省略。"
        ),
    )
    parser.add_argument(
        "--item-display-template-gil",
        dest="item_display_template_gil",
        default=None,
        help=(
            "可选：提供一份“包含 道具展示 控件”的样本 .gil，作为 道具展示 record 模板来源。"
            "当 base .gil 内不存在 道具展示 且 ui_schema_library 未命中模板时，需要提供一次用于沉淀；后续可省略。"
        ),
    )

    parser.add_argument("--verify", dest="verify", action="store_true", help="写回后用 DLL dump 验证 GUID 存在")
    parser.add_argument("--report-json", dest="report_json", default=None, help="输出报告 JSON（落到 ugc_file_tools/out/）")
    parser.set_defaults(entrypoint=_command_ui_import_web_template)


