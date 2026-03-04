from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .claude_files import _build_package_skeleton, _write_claude_if_missing
from .combat_presets_exporter import _export_player_templates_and_classes_from_pyugc_dump
from .data_blob_exporter import _export_data_blobs_from_pyugc_object
from .dll_dump import _dump_gil_to_json_with_dll
from .dtype_type3_exporter import _export_decoded_dtype_type3_from_data_blobs
from .file_io import _write_json_file, _write_text_file
from .generic_scan_exporter import _export_generic_decoded_indexes_from_data_blobs
from .graph_validation import (
    _find_graph_generater_root_from_output_package_root,
    _validate_graph_generater_single_package,
)
from .instance_exporter import _export_instances_from_pyugc_dump
from .models import DataBlobRecord
from .object_scanners import _collect_string_values
from .node_graph_raw_exporter import export_pyugc_node_graphs_and_node_defs
from .node_graph_placeholders import _export_placeholder_node_graphs_from_references
from .parse_status import _build_parse_status_markdown
from .paths import _resolve_default_dtype_path, _resolve_parse_status_root_path
from .pyugc_decode import _decode_gil_with_pyugc
from .signal_exporter import _export_signals_from_pyugc_dump
from .struct_definition_exporter import _export_struct_definitions_from_pyugc_dump
from .section15_exporter import _export_section15_resources_from_pyugc_dump
from .template_exporter import _export_templates_from_pyugc_dump
from .template_placeholders import export_placeholder_templates_for_missing_instance_references


def export_gil_to_package(
    input_gil_file_path: Path,
    output_package_root: Path,
    dtype_path: Path,
    enable_dll_dump: bool,
    data_blob_min_bytes_for_decode: int,
    generic_scan_min_bytes: int,
    focus_graph_id: Optional[int],
    parse_status_root: Optional[Path] = None,
    export_raw_pyugc_dump: bool = True,
    export_node_graphs: bool = True,
    selected_node_graph_id_ints: Optional[Sequence[int]] = None,
    export_templates: bool = True,
    export_instances: bool = True,
    export_combat_presets: bool = True,
    export_section15: bool = True,
    export_struct_definitions: bool = True,
    export_signals: bool = True,
    export_data_blobs: bool = True,
    export_decoded_dtype_type3: bool = True,
    export_decoded_generic: bool = True,
) -> None:
    graph_generater_root = _find_graph_generater_root_from_output_package_root(output_package_root)
    if graph_generater_root is not None:
        project_archive_root = graph_generater_root / "assets" / "资源库" / "项目存档"
        if output_package_root.parent.resolve() != project_archive_root.resolve():
            raise ValueError(
                "输出目录必须是 Graph_Generater 项目存档的一级子目录："
                f"{str(project_archive_root.as_posix())}/<package_id>（存档包已废弃）"
            )

    _build_package_skeleton(output_package_root)

    header, pyugc_object = _decode_gil_with_pyugc(input_gil_file_path, dtype_path)

    exported_ui_widget_templates_index: List[Dict[str, Any]] = []

    pyugc_dump_rel: str | None = None
    pyugc_string_index_rel: str | None = None
    if bool(export_raw_pyugc_dump):
        pyugc_output_directory = output_package_root / "原始解析" / "pyugc"
        _write_json_file(pyugc_output_directory / "gil_header.json", header.__dict__)
        _write_json_file(pyugc_output_directory / "dump.json", pyugc_object)

        string_index = _collect_string_values(pyugc_object)
        sorted_strings = sorted(
            string_index.items(),
            key=lambda item: int(item[1].get("count", 0)),
            reverse=True,
        )
        _write_json_file(
            pyugc_output_directory / "string_index.json",
            [{"text": text, **meta} for text, meta in sorted_strings],
        )
        pyugc_dump_rel = "原始解析/pyugc/dump.json"
        pyugc_string_index_rel = "原始解析/pyugc/string_index.json"

    pyugc_node_graph_export_result: Dict[str, Any] = {}
    if bool(export_node_graphs):
        pyugc_node_graph_export_result = export_pyugc_node_graphs_and_node_defs(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
            selected_graph_id_ints=selected_node_graph_id_ints,
        )

    exported_templates_index: List[Dict[str, Any]] = []
    exported_instances_index: List[Dict[str, Any]] = []
    if bool(export_templates):
        exported_templates_index = _export_templates_from_pyugc_dump(pyugc_object, output_package_root)
    if bool(export_instances):
        exported_instances_index = _export_instances_from_pyugc_dump(pyugc_object, output_package_root)
    if bool(export_templates) and bool(export_instances):
        exported_templates_index = export_placeholder_templates_for_missing_instance_references(
            output_package_root=output_package_root,
            exported_templates_index=exported_templates_index,
            exported_instances_index=exported_instances_index,
        )

    combat_presets_export_result: Dict[str, Any] = {}
    if bool(export_combat_presets):
        combat_presets_export_result = _export_player_templates_and_classes_from_pyugc_dump(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
            focus_graph_id=focus_graph_id,
        )

    section15_export_result: Dict[str, Any] = {}
    if bool(export_section15):
        section15_export_result = _export_section15_resources_from_pyugc_dump(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
        )

    struct_definitions_export_result: Dict[str, Any] = {}
    if bool(export_struct_definitions):
        struct_definitions_export_result = _export_struct_definitions_from_pyugc_dump(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
        )

    signals_export_result: Dict[str, Any] = {}
    if bool(export_signals):
        signals_export_result = _export_signals_from_pyugc_dump(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
        )

    placeholder_graphs: List[Dict[str, Any]] = []
    if bool(export_node_graphs) and bool(export_section15):
        referenced_graph_sources = section15_export_result.get("referenced_graph_sources")
        if not isinstance(referenced_graph_sources, dict):
            referenced_graph_sources = {}
        placeholder_graphs = _export_placeholder_node_graphs_from_references(
            output_package_root=output_package_root,
            package_namespace=output_package_root.name,
            referenced_graph_sources=referenced_graph_sources,
        )

    binary_blob_index: List[DataBlobRecord] = []
    unique_blob_files = 0
    if bool(export_data_blobs):
        binary_blob_index, unique_blob_files = _export_data_blobs_from_pyugc_object(
            pyugc_object=pyugc_object,
            output_package_root=output_package_root,
        )

    if enable_dll_dump:
        dll_output_directory = output_package_root / "原始解析" / "dll"
        dll_dump_path = dll_output_directory / "dump.json"
        _dump_gil_to_json_with_dll(
            input_gil_file_path=input_gil_file_path,
            dll_dump_path=dll_dump_path,
        )
        dll_dump_object = json.loads(dll_dump_path.read_text(encoding="utf-8"))
        if not isinstance(dll_dump_object, dict):
            raise ValueError("DLL dump-json 顶层不是 dict")

        # UI 控件模板：依赖 DLL dump-json，导出到项目存档管理配置目录（用于后续写回/合并）
        from .ui_widget_templates_exporter import _export_ui_widget_templates_from_dll_dump

        exported_ui_widget_templates_index = _export_ui_widget_templates_from_dll_dump(
            dll_dump_object=dll_dump_object,
            output_package_root=output_package_root,
        )

        # UI schema library：遇到就记录（沉淀 record/blob 结构模板，减少重复逆向）
        from ugc_file_tools.ui_schema_library.recorder import record_ui_schema_library_from_dll_dump

        record_ui_schema_library_from_dll_dump(
            dll_dump_object=dll_dump_object,
            source_gil_file_path=input_gil_file_path,
        )

    if bool(export_data_blobs) and bool(export_decoded_dtype_type3):
        _export_decoded_dtype_type3_from_data_blobs(
            output_package_root=output_package_root,
            dtype_path=dtype_path,
            data_blob_index=binary_blob_index,
            data_blob_min_bytes_for_decode=data_blob_min_bytes_for_decode,
        )

    saved_full_min_bytes = int(max(256, data_blob_min_bytes_for_decode))
    if bool(export_data_blobs) and bool(export_decoded_generic):
        _export_generic_decoded_indexes_from_data_blobs(
            output_package_root=output_package_root,
            data_blob_index=binary_blob_index,
            generic_scan_min_bytes=generic_scan_min_bytes,
            saved_full_min_bytes=saved_full_min_bytes,
        )

    # 生成一份便于人工阅读的汇总报告（不追求语义正确，仅用于定位入口）
    report_object: Dict[str, Any] = {
        "cli": {
            "input_gil": str(input_gil_file_path),
            "output_package_root": str(output_package_root),
            "dtype_path": str(dtype_path),
            "enable_dll_dump": bool(enable_dll_dump),
            "data_min_bytes": int(data_blob_min_bytes_for_decode),
            "generic_scan_min_bytes": int(generic_scan_min_bytes),
            "focus_graph_id": (int(focus_graph_id) if focus_graph_id is not None else None),
        },
        "input_gil": str(input_gil_file_path),
        "output_package_root": str(output_package_root),
        "pyugc": {
            "header": header.__dict__,
            "dump": pyugc_dump_rel,
            "string_index": pyugc_string_index_rel,
        },
        "dll_dump": {
            "enabled": bool(enable_dll_dump),
            "dump": "原始解析/dll/dump.json" if enable_dll_dump else None,
        },
        "data_blobs": {
            "total_records": len(binary_blob_index),
            "unique_files": int(unique_blob_files),
            "index": ("原始解析/数据块/index.json" if bool(export_data_blobs) else None),
        },
        "decoded_generic": {
            "scan_min_bytes": int(generic_scan_min_bytes),
            "saved_full_min_bytes": saved_full_min_bytes,
            "saved_full_index": ("原始解析/数据块/decoded_generic/index.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
            "utf8_index": ("原始解析/数据块/decoded_generic/utf8_index.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
            "keyword_hits_index": ("原始解析/数据块/decoded_generic/keyword_hits_index.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
        },
        "decoded_dtype_type3": {
            "min_bytes": int(data_blob_min_bytes_for_decode),
            "index": ("原始解析/数据块/decoded_dtype_type3/index.json" if bool(export_data_blobs) and bool(export_decoded_dtype_type3) else None),
        },
        "node_graphs_pyugc": pyugc_node_graph_export_result,
        "extracted": {
            "templates_count": len(exported_templates_index),
            "templates_index": ("元件库/templates_index.json" if bool(export_templates) else None),
            "instances_count": len(exported_instances_index),
            "instances_index": ("实体摆放/instances_index.json" if bool(export_instances) else None),
            "player_templates_index": ("战斗预设/玩家模板/player_templates_index.json" if bool(export_combat_presets) else None),
            "player_classes_index": ("战斗预设/职业/player_classes_index.json" if bool(export_combat_presets) else None),
            "player_templates_count": len(combat_presets_export_result.get("player_templates", [])),
            "player_classes_count": len(combat_presets_export_result.get("player_classes", [])),
            "skills_index": ("战斗预设/技能/skills_index.json" if bool(export_section15) else None),
            "items_index": ("战斗预设/道具/items_index.json" if bool(export_section15) else None),
            "unit_statuses_index": ("战斗预设/单位状态/unit_statuses_index.json" if bool(export_section15) else None),
            "skills_count": len(section15_export_result.get("skills", [])),
            "items_count": len(section15_export_result.get("items", [])),
            "unit_statuses_count": len(section15_export_result.get("unit_statuses", [])),
            "currency_backpacks_index": ("管理配置/货币背包/currency_backpacks_index.json" if bool(export_section15) else None),
            "currency_backpacks_count": len(section15_export_result.get("currency_backpacks", [])),
            "level_settings_index": ("管理配置/关卡设置/level_settings_index.json" if bool(export_section15) else None),
            "level_settings_count": len(section15_export_result.get("level_settings", [])),
            "shields_index": ("管理配置/护盾/shields_index.json" if bool(export_section15) else None),
            "shields_count": len(section15_export_result.get("shields", [])),
            "unit_tags_index": ("管理配置/单位标签/unit_tags_index.json" if bool(export_section15) else None),
            "unit_tags_count": len(section15_export_result.get("unit_tags", [])),
            "equipment_data_index": ("管理配置/装备数据/equipment_data_index.json" if bool(export_section15) else None),
            "equipment_data_count": len(section15_export_result.get("equipment_data", [])),
            "growth_curves_index": ("管理配置/成长曲线/growth_curves_index.json" if bool(export_section15) else None),
            "growth_curves_count": len(section15_export_result.get("growth_curves", [])),
            "equipment_slot_templates_index": ("管理配置/装备栏模板/equipment_slot_templates_index.json" if bool(export_section15) else None),
            "equipment_slot_templates_count": len(section15_export_result.get("equipment_slot_templates", [])),
            "struct_definitions_count": int(struct_definitions_export_result.get("struct_definitions_count") or 0),
            "signals_index": ("管理配置/信号/signals_index.json" if bool(export_signals) else None),
            "signals_count": int(signals_export_result.get("signals_count") or 0),
            "section15_unclassified_index": ("原始解析/资源条目/section15_unclassified/section15_unclassified_index.json" if bool(export_section15) else None),
            "section15_unclassified_count": len(section15_export_result.get("unclassified", [])),
            "section15_unclassified_type_codes": sorted(
                {
                    int(item.get("type_code"))
                    for item in section15_export_result.get("unclassified", [])
                    if isinstance(item, dict) and isinstance(item.get("type_code"), int)
                }
            ),
            "referenced_graphs_index": str(section15_export_result.get("referenced_graphs_index", "")),
            "referenced_graph_id_ints_count": len(section15_export_result.get("referenced_graph_id_ints", [])),
            "placeholder_graphs_index": ("节点图/原始解析/placeholder_graphs_index.json" if bool(export_node_graphs) and bool(export_section15) else None),
            "placeholder_graphs_count": len(placeholder_graphs),
            "pyugc_graphs_index": str(pyugc_node_graph_export_result.get("pyugc_graphs_index", "")),
            "pyugc_graphs_count": int(pyugc_node_graph_export_result.get("pyugc_graphs_count", 0) or 0),
            "pyugc_node_defs_index": str(pyugc_node_graph_export_result.get("pyugc_node_defs_index", "")),
            "pyugc_node_defs_count": int(pyugc_node_graph_export_result.get("pyugc_node_defs_count", 0) or 0),
            "suspected_variable_names": ("原始解析/关卡变量/解析_疑似变量名.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
            "suspected_variable_groups": ("原始解析/关卡变量/解析_疑似变量名_按前缀.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
            "field501_named_records": ("原始解析/关卡变量/解析_field501_命名记录.json" if bool(export_data_blobs) and bool(export_decoded_generic) else None),
            "graphs_index": ("节点图/原始解析/graphs_index.json" if bool(export_node_graphs) else None),
            "ui_widget_templates_index": "管理配置/UI控件模板/ui_widget_templates_index.json"
            if enable_dll_dump
            else None,
            "ui_widget_templates_count": (
                len(exported_ui_widget_templates_index) if enable_dll_dump else 0
            ),
        },
    }

    validation_summary: Optional[Dict[str, Any]] = None
    if graph_generater_root is not None:
        validation_summary = _validate_graph_generater_single_package(
            graph_generater_root=graph_generater_root,
            package_id=output_package_root.name,
        )
    report_object["validation"] = validation_summary
    report_object["parse_status_doc"] = f"ugc_file_tools/parse_status/{output_package_root.name}/解析状态.md"

    _write_json_file(output_package_root / "原始解析" / "report.json", report_object)

    parse_status_markdown = _build_parse_status_markdown(
        output_package_root=output_package_root,
        report_object=report_object,
        validation_summary=validation_summary,
    )
    resolved_parse_status_root = parse_status_root if parse_status_root is not None else _resolve_parse_status_root_path()
    parse_status_package_root = resolved_parse_status_root / output_package_root.name
    _write_claude_if_missing(
        parse_status_package_root,
        purpose_lines=[
            f"集中存放 `{output_package_root.name}` 的解析状态报告（自动生成）。",
        ],
        state_lines=[
            "解析状态会随导出/解析脚本刷新；每个项目存档一份。",
        ],
        note_lines=[
            "该目录内容可重复生成；权威数据以对应项目存档目录为准。",
            "不在此文件中记录修改历史，仅保持用途/状态/注意事项的实时描述。",
        ],
    )
    _write_text_file(parse_status_package_root / "解析状态.md", parse_status_markdown)


def main(argv: Optional[Sequence[str]] = None) -> None:
    import argparse

    argument_parser = argparse.ArgumentParser(
        description=(
            "尽可能解析 .gil：导出原始 dump、拆分 data 块、并尝试二次解码后落盘为“项目存档”目录结构；"
            "解析状态文档统一输出到 ugc_file_tools/parse_status/，避免写入 Graph_Generater 资源库。"
        ),
    )
    argument_parser.add_argument(
        "--input-gil",
        dest="input_gil_file",
        required=True,
        help="输入 .gil 文件路径",
    )
    argument_parser.add_argument(
        "--output-package",
        dest="output_package_root",
        required=True,
        help="输出项目存档根目录（例如 Graph_Generater/assets/资源库/项目存档/test2）",
    )
    argument_parser.add_argument(
        "--parse-status-root",
        dest="parse_status_root",
        default=str(_resolve_parse_status_root_path()),
        help="解析状态输出根目录（默认 ugc_file_tools/parse_status；每个 package 写入 <root>/<package>/解析状态.md）",
    )
    argument_parser.add_argument(
        "--dtype",
        dest="dtype_path",
        default=str(_resolve_default_dtype_path()),
        help="dtype.json 路径（默认使用 ugc_file_tools/builtin_resources/dtype/dtype.json）",
    )
    argument_parser.add_argument(
        "--enable-dll-dump",
        dest="enable_dll_dump",
        action="store_true",
        help="额外执行一次 dump-json，并从中提取 UI 相关数据（用于导出 UI 控件模板）",
    )
    argument_parser.add_argument(
        "--data-min-bytes",
        dest="data_min_bytes",
        type=int,
        default=512,
        help="对 data blob 进行二次解码的最小字节阈值（默认 512）",
    )
    argument_parser.add_argument(
        "--generic-scan-min-bytes",
        dest="generic_scan_min_bytes",
        type=int,
        default=256,
        help="通用解码扫描的最小字节阈值（默认 256，会做 utf8 统计与关键字命中定位）",
    )
    argument_parser.add_argument(
        "--focus-graph-id",
        dest="focus_graph_id",
        type=int,
        help="可选：定向定位某个节点图/节点ID（例如 1073741832），会额外导出命中 @data 的通用解码结果到 节点图/原始解析/graph_id_<id>/。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    input_gil_file_path = Path(arguments.input_gil_file)
    output_package_root = Path(arguments.output_package_root)
    dtype_path = Path(arguments.dtype_path)
    parse_status_root = Path(arguments.parse_status_root)

    if not input_gil_file_path.is_file():
        raise FileNotFoundError(f"input gil file not found: {str(input_gil_file_path)!r}")

    export_gil_to_package(
        input_gil_file_path=input_gil_file_path,
        output_package_root=output_package_root,
        dtype_path=dtype_path,
        enable_dll_dump=bool(arguments.enable_dll_dump),
        data_blob_min_bytes_for_decode=int(arguments.data_min_bytes),
        generic_scan_min_bytes=int(arguments.generic_scan_min_bytes),
        focus_graph_id=(int(arguments.focus_graph_id) if arguments.focus_graph_id is not None else None),
        parse_status_root=parse_status_root,
    )


