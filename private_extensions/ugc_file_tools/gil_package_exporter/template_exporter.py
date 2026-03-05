from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .claude_files import _ensure_claude_for_directory
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file
from .pyugc_extractors import _extract_template_entry_name


def _export_templates_from_pyugc_dump(
    pyugc_object: Any,
    output_package_root: Path,
) -> List[Dict[str, Any]]:
    """从 root4['4']['1'] 导出元件库模板（TemplateConfig-like JSON）。"""
    exported_templates: List[Dict[str, Any]] = []

    if not isinstance(pyugc_object, dict):
        return exported_templates
    root4_object = pyugc_object.get("4")
    if not isinstance(root4_object, dict):
        return exported_templates
    templates_section = root4_object.get("4")
    if not isinstance(templates_section, dict):
        return exported_templates
    template_entries = templates_section.get("1")
    if not isinstance(template_entries, list):
        return exported_templates

    template_directory = output_package_root / "元件库"
    template_raw_directory = template_directory / "原始解析"
    _ensure_directory(template_raw_directory)
    _ensure_claude_for_directory(
        template_raw_directory,
        purpose="存放从 .gil 中解析得到的元件库模板原始结构（pyugc 条目），用于对照与继续逆向。",
    )

    for entry_index, template_entry in enumerate(template_entries):
        if not isinstance(template_entry, dict):
            continue

        entry_id_list = template_entry.get("1")
        if (
            not isinstance(entry_id_list, list)
            or not entry_id_list
            or not isinstance(entry_id_list[0], int)
        ):
            continue
        template_entry_id_int = int(entry_id_list[0])

        type_list = template_entry.get("2")
        template_type_code_int: Optional[int] = None
        if isinstance(type_list, list) and type_list and isinstance(type_list[0], int):
            template_type_code_int = int(type_list[0])

        # 跳过战斗预设（玩家模板/职业编辑）条目，避免混入元件库
        if template_type_code_int in (1000000, 1000001):
            continue

        template_name = _extract_template_entry_name(template_entry)
        if template_name == "":
            template_name = f"template_{template_entry_id_int}"

        # Graph_Generater 侧允许的实体类型来自 engine.configs.rules.entity_rules，
        # 不包含 “怪物” 这一细分概念；此处将怪物类模板映射为“角色”，以保证可被引擎识别与校验。
        entity_type = "物件"
        if isinstance(template_type_code_int, int) and 30000000 <= template_type_code_int < 40000000:
            entity_type = "角色"

        raw_file_path = template_raw_directory / f"ugc_template_{template_entry_id_int}.pyugc.json"
        _write_json_file(raw_file_path, template_entry)

        template_id_text = str(template_entry_id_int)
        template_object: Dict[str, Any] = {
            "template_id": template_id_text,
            "name": template_name,
            "entity_type": entity_type,
            "description": "",
            "default_graphs": [],
            "default_variables": [],
            "default_components": [],
            "entity_config": {},
            "metadata": {
                "ugc": {
                    "source_template_entry_id_int": template_entry_id_int,
                    "source_template_type_code_int": template_type_code_int,
                    "source_pyugc_path": f"4/4/1/[{entry_index}]",
                    "raw_pyugc_entry": str(raw_file_path.relative_to(output_package_root)).replace("\\", "/"),
                }
            },
            "graph_variable_overrides": {},
            "updated_at": "",
        }

        output_file_name = _sanitize_filename(f"{template_name}_{template_entry_id_int}") + ".json"
        output_path = template_directory / output_file_name
        _write_json_file(output_path, template_object)

        exported_templates.append(
            {
                "template_id": template_id_text,
                "name": template_name,
                "entity_type": entity_type,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    exported_templates_sorted = sorted(
        exported_templates,
        key=lambda item: str(item.get("template_id", "")),
    )
    _write_json_file(template_directory / "templates_index.json", exported_templates_sorted)
    return exported_templates_sorted


