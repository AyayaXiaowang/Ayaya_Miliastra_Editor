from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..claude_files import _ensure_claude_for_directory
from ..file_io import _ensure_directory, _write_json_file
from ..pyugc_extractors import (
    _extract_section15_entry_id_int,
    _extract_section15_entry_name,
    _extract_section15_entry_type_code,
)
from ..section15_currency_exporter import _export_currency_backpacks_from_section15_scan
from .context import Section15ExportContext
from .equipment_data import export_equipment_data_entry
from .equipment_slot_templates import export_equipment_slot_template_entry
from .growth_curves import export_growth_curve_entry
from .items import export_item_entry
from .level_settings import export_level_settings_entry
from .shields import export_shield_entry
from .skills import export_skill_entry
from .unclassified import export_unclassified_entry
from .unit_statuses import export_unit_status_entry
from .unit_tags import export_unit_tag_entry


def _export_section15_resources_from_pyugc_dump(
    *,
    pyugc_object: Any,
    output_package_root: Path,
) -> Dict[str, Any]:
    """
    导出 root4['15']['1'] 中可识别的资源到 Graph_Generater 目录：
    - 战斗预设：技能/道具/单位状态
    - 管理配置：护盾/单位标签/装备数据/货币背包/关卡设置

    目标：结构尽量贴近 Graph_Generater 现有示例文件；无法语义映射的字段全部保存在 metadata.ugc 与 原始解析 文件中。
    """
    result: Dict[str, Any] = {
        "skills": [],
        "items": [],
        "unit_statuses": [],
        "currency_backpacks": [],
        "level_settings": [],
        "preset_points": [],
        "shields": [],
        "unit_tags": [],
        "equipment_data": [],
        "growth_curves": [],
        "equipment_slot_templates": [],
        "referenced_graph_id_ints": [],
        "referenced_graphs_index": "",
        "referenced_graph_sources": {},
        "unclassified": [],
    }

    if not isinstance(pyugc_object, dict):
        return result
    root4_object = pyugc_object.get("4")
    if not isinstance(root4_object, dict):
        return result

    section15_object = root4_object.get("15")
    if not isinstance(section15_object, dict):
        return result
    section15_entries = section15_object.get("1")
    if not isinstance(section15_entries, list):
        return result

    package_namespace = output_package_root.name

    skill_directory = output_package_root / "战斗预设" / "技能"
    item_directory = output_package_root / "战斗预设" / "道具"
    unit_status_directory = output_package_root / "战斗预设" / "单位状态"

    currency_backpack_directory = output_package_root / "管理配置" / "货币背包"
    level_settings_directory = output_package_root / "管理配置" / "关卡设置"
    shield_directory = output_package_root / "管理配置" / "护盾"
    unit_tag_directory = output_package_root / "管理配置" / "单位标签"
    equipment_data_directory = output_package_root / "管理配置" / "装备数据"
    growth_curve_directory = output_package_root / "管理配置" / "成长曲线"
    equipment_slot_template_directory = output_package_root / "管理配置" / "装备栏模板"
    preset_point_directory = output_package_root / "管理配置" / "预设点"

    unclassified_directory = output_package_root / "原始解析" / "资源条目" / "section15_unclassified"

    _ensure_directory(skill_directory)
    _ensure_directory(item_directory)
    _ensure_directory(unit_status_directory)
    _ensure_directory(currency_backpack_directory)
    _ensure_directory(level_settings_directory)
    _ensure_directory(shield_directory)
    _ensure_directory(unit_tag_directory)
    _ensure_directory(equipment_data_directory)
    _ensure_directory(growth_curve_directory)
    _ensure_directory(equipment_slot_template_directory)
    _ensure_directory(preset_point_directory)
    _ensure_directory(unclassified_directory)

    skill_raw_directory = skill_directory / "原始解析"
    item_raw_directory = item_directory / "原始解析"
    unit_status_raw_directory = unit_status_directory / "原始解析"
    currency_backpack_raw_directory = currency_backpack_directory / "原始解析"
    level_settings_raw_directory = level_settings_directory / "原始解析"
    shield_raw_directory = shield_directory / "原始解析"
    unit_tag_raw_directory = unit_tag_directory / "原始解析"
    equipment_data_raw_directory = equipment_data_directory / "原始解析"
    growth_curve_raw_directory = growth_curve_directory / "原始解析"
    equipment_slot_template_raw_directory = equipment_slot_template_directory / "原始解析"

    _ensure_directory(skill_raw_directory)
    _ensure_directory(item_raw_directory)
    _ensure_directory(unit_status_raw_directory)
    _ensure_directory(currency_backpack_raw_directory)
    _ensure_directory(level_settings_raw_directory)
    _ensure_directory(shield_raw_directory)
    _ensure_directory(unit_tag_raw_directory)
    _ensure_directory(equipment_data_raw_directory)
    _ensure_directory(growth_curve_raw_directory)
    _ensure_directory(equipment_slot_template_raw_directory)

    _ensure_claude_for_directory(skill_raw_directory, purpose="存放从 .gil 中解析得到的技能条目原始结构，用于对照与继续逆向。")
    _ensure_claude_for_directory(item_raw_directory, purpose="存放从 .gil 中解析得到的道具条目原始结构，用于对照与继续逆向。")
    _ensure_claude_for_directory(unit_status_raw_directory, purpose="存放从 .gil 中解析得到的单位状态条目原始结构，用于对照与继续逆向。")
    _ensure_claude_for_directory(currency_backpack_raw_directory, purpose="存放从 .gil 中解析得到的货币背包相关条目原始结构与通用解码结果。")
    _ensure_claude_for_directory(level_settings_raw_directory, purpose="存放从 .gil 中解析得到的环境/关卡设置相关条目原始结构。")
    _ensure_claude_for_directory(shield_raw_directory, purpose="存放从 .gil 中解析得到的护盾条目原始结构。")
    _ensure_claude_for_directory(unit_tag_raw_directory, purpose="存放从 .gil 中解析得到的单位标签条目原始结构。")
    _ensure_claude_for_directory(equipment_data_raw_directory, purpose="存放从 .gil 中解析得到的装备数据条目原始结构。")
    _ensure_claude_for_directory(growth_curve_raw_directory, purpose="存放从 .gil 中解析得到的成长曲线条目原始结构。")
    _ensure_claude_for_directory(
        equipment_slot_template_raw_directory,
        purpose="存放从 .gil 中解析得到的装备栏模板条目原始结构与通用解码结果。",
    )

    currency_entries: List[Dict[str, Any]] = []
    backpack_entry: Optional[Tuple[int, Dict[str, Any]]] = None
    referenced_graph_sources: Dict[int, List[Dict[str, Any]]] = {}

    for entry_index, section15_entry in enumerate(section15_entries):
        if not isinstance(section15_entry, dict):
            continue
        entry_id_int = _extract_section15_entry_id_int(section15_entry)
        type_code_int = _extract_section15_entry_type_code(section15_entry)
        entry_name = _extract_section15_entry_name(section15_entry)
        if entry_id_int is None or type_code_int is None:
            continue

        if type_code_int == 11:
            currency_entries.append(
                {
                    "entry_index": entry_index,
                    "entry_id_int": entry_id_int,
                    "entry_name": entry_name,
                    "entry": section15_entry,
                }
            )
            continue

        if type_code_int == 12 and backpack_entry is None:
            backpack_entry = (entry_index, section15_entry)
            continue

    context = Section15ExportContext(
        output_package_root=output_package_root,
        package_namespace=package_namespace,
        skill_directory=skill_directory,
        item_directory=item_directory,
        unit_status_directory=unit_status_directory,
        currency_backpack_directory=currency_backpack_directory,
        level_settings_directory=level_settings_directory,
        preset_point_directory=preset_point_directory,
        shield_directory=shield_directory,
        unit_tag_directory=unit_tag_directory,
        equipment_data_directory=equipment_data_directory,
        growth_curve_directory=growth_curve_directory,
        equipment_slot_template_directory=equipment_slot_template_directory,
        unclassified_directory=unclassified_directory,
        skill_raw_directory=skill_raw_directory,
        item_raw_directory=item_raw_directory,
        unit_status_raw_directory=unit_status_raw_directory,
        currency_backpack_raw_directory=currency_backpack_raw_directory,
        level_settings_raw_directory=level_settings_raw_directory,
        shield_raw_directory=shield_raw_directory,
        unit_tag_raw_directory=unit_tag_raw_directory,
        equipment_data_raw_directory=equipment_data_raw_directory,
        growth_curve_raw_directory=growth_curve_raw_directory,
        equipment_slot_template_raw_directory=equipment_slot_template_raw_directory,
        referenced_graph_sources=referenced_graph_sources,
        currency_entries=currency_entries,
        backpack_entry=backpack_entry,
    )

    for entry_index, section15_entry in enumerate(section15_entries):
        if not isinstance(section15_entry, dict):
            continue
        entry_id_int = _extract_section15_entry_id_int(section15_entry)
        type_code_int = _extract_section15_entry_type_code(section15_entry)
        entry_name = _extract_section15_entry_name(section15_entry)
        if entry_id_int is None or type_code_int is None:
            continue
        if entry_name == "":
            entry_name = f"section15_{type_code_int}_{entry_id_int}"

        source_path_text = f"4/15/1/[{entry_index}]"

        if type_code_int == 6:
            export_skill_entry(
                section15_entry=section15_entry,
                entry_index=entry_index,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        # 职业（type_code=4）由 combat_presets_exporter 全量导出
        if type_code_int == 4:
            continue

        if type_code_int == 5:
            export_growth_curve_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 13:
            export_equipment_slot_template_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int in (9, 10):
            export_item_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 1:
            export_unit_status_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 22:
            export_shield_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 15:
            export_unit_tag_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 16:
            export_equipment_data_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int == 26:
            export_level_settings_entry(
                section15_entry=section15_entry,
                entry_id_int=entry_id_int,
                type_code_int=type_code_int,
                entry_name=entry_name,
                source_path_text=source_path_text,
                context=context,
                result=result,
            )
            continue

        if type_code_int in (11, 12):
            continue

        export_unclassified_entry(
            section15_entry=section15_entry,
            entry_id_int=entry_id_int,
            type_code_int=type_code_int,
            entry_name=entry_name,
            source_path_text=source_path_text,
            context=context,
            result=result,
        )

    result["currency_backpacks"].extend(
        _export_currency_backpacks_from_section15_scan(
            currency_entries=context.currency_entries,
            backpack_entry=context.backpack_entry,
            output_package_root=context.output_package_root,
            package_namespace=context.package_namespace,
            currency_backpack_directory=context.currency_backpack_directory,
            currency_backpack_raw_directory=context.currency_backpack_raw_directory,
        )
    )

    _write_json_file(
        skill_directory / "skills_index.json",
        sorted(result["skills"], key=lambda item: str(item.get("skill_id", ""))),
    )
    _write_json_file(
        item_directory / "items_index.json",
        sorted(result["items"], key=lambda item: str(item.get("item_id", ""))),
    )
    _write_json_file(
        unit_status_directory / "unit_statuses_index.json",
        sorted(result["unit_statuses"], key=lambda item: str(item.get("status_id", ""))),
    )
    _write_json_file(
        currency_backpack_directory / "currency_backpacks_index.json",
        sorted(result["currency_backpacks"], key=lambda item: str(item.get("config_id", ""))),
    )
    _write_json_file(
        level_settings_directory / "level_settings_index.json",
        sorted(result["level_settings"], key=lambda item: str(item.get("config_id", ""))),
    )
    _write_json_file(
        shield_directory / "shields_index.json",
        sorted(result["shields"], key=lambda item: str(item.get("shield_id", ""))),
    )
    _write_json_file(
        unit_tag_directory / "unit_tags_index.json",
        sorted(result["unit_tags"], key=lambda item: str(item.get("tag_id", ""))),
    )
    _write_json_file(
        equipment_data_directory / "equipment_data_index.json",
        sorted(result["equipment_data"], key=lambda item: str(item.get("equipment_id", ""))),
    )
    _write_json_file(
        growth_curve_directory / "growth_curves_index.json",
        sorted(result["growth_curves"], key=lambda item: str(item.get("curve_id", ""))),
    )
    _write_json_file(
        equipment_slot_template_directory / "equipment_slot_templates_index.json",
        sorted(result["equipment_slot_templates"], key=lambda item: str(item.get("template_id", ""))),
    )
    _write_json_file(
        preset_point_directory / "preset_points_index.json",
        sorted(result["preset_points"], key=lambda item: str(item.get("point_id", ""))),
    )
    _write_json_file(
        unclassified_directory / "section15_unclassified_index.json",
        sorted(
            result["unclassified"],
            key=lambda item: (int(item.get("type_code", 0)), str(item.get("entry_id_int", ""))),
        ),
    )

    referenced_graph_index_records: List[Dict[str, Any]] = []
    for graph_id_int, sources in sorted(referenced_graph_sources.items(), key=lambda item: item[0]):
        referenced_graph_index_records.append(
            {
                "graph_id_int": int(graph_id_int),
                "sources": sources,
            }
        )
    referenced_graph_index_path = output_package_root / "节点图" / "原始解析" / "referenced_graphs_index.json"
    _write_json_file(referenced_graph_index_path, referenced_graph_index_records)
    result["referenced_graph_id_ints"] = [record["graph_id_int"] for record in referenced_graph_index_records]
    result["referenced_graphs_index"] = str(referenced_graph_index_path.relative_to(output_package_root)).replace("\\", "/")
    result["referenced_graph_sources"] = referenced_graph_sources

    return result


