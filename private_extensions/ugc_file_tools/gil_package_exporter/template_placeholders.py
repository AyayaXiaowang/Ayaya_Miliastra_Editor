from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from .file_io import _sanitize_filename, _write_json_file


def export_placeholder_templates_for_missing_instance_references(
    *,
    output_package_root: Path,
    exported_templates_index: List[Dict[str, Any]],
    exported_instances_index: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """为“实体摆放引用但未导出的模板”生成占位模板，保证引用闭包可被引擎索引与校验。

    背景：
    - 部分 .gil 仅在“实体摆放”条目中给出 template_id 引用，但并未在“元件库模板列表”中提供对应模板定义；
    - Graph_Generater 的综合校验会将这类引用判定为错误（instance 引用不存在模板）。
    - 占位模板的目标不是语义还原，而是让项目结构闭合、可加载、可继续逆向。
    """
    template_directory = output_package_root / "元件库"

    existing_template_ids: Set[str] = set()
    for template_index_entry in exported_templates_index:
        if not isinstance(template_index_entry, dict):
            continue
        template_id_value = template_index_entry.get("template_id")
        if isinstance(template_id_value, str) and template_id_value.strip() != "":
            existing_template_ids.add(template_id_value.strip())

    referenced_template_ids: Set[str] = set()
    referenced_by_instances: Dict[str, List[Dict[str, Any]]] = {}
    for instance_index_entry in exported_instances_index:
        if not isinstance(instance_index_entry, dict):
            continue
        template_id_value = instance_index_entry.get("template_id")
        if not isinstance(template_id_value, str) or template_id_value.strip() == "":
            continue
        template_id_text = template_id_value.strip()
        if template_id_text == "unknown_template":
            continue
        referenced_template_ids.add(template_id_text)
        referenced_by_instances.setdefault(template_id_text, []).append(instance_index_entry)

    missing_template_ids = sorted(
        [template_id for template_id in referenced_template_ids if template_id not in existing_template_ids],
        key=lambda text: text.casefold(),
    )
    if not missing_template_ids:
        return exported_templates_index

    updated_templates_index: List[Dict[str, Any]] = list(exported_templates_index)
    for template_id_text in missing_template_ids:
        placeholder_name = f"自动解析_模板_{template_id_text}"
        output_file_name = _sanitize_filename(placeholder_name) + ".json"
        output_path = template_directory / output_file_name
        if output_path.exists():
            # 文件已存在：不覆盖，只补充索引闭包
            updated_templates_index.append(
                {
                    "template_id": template_id_text,
                    "name": placeholder_name,
                    "entity_type": "物件",
                    "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
                }
            )
            continue

        sample_instances = referenced_by_instances.get(template_id_text, [])
        referenced_instance_ids: List[str] = []
        referenced_instance_names: List[str] = []
        for instance_entry in sample_instances[:20]:
            instance_id_value = instance_entry.get("instance_id")
            instance_name_value = instance_entry.get("name")
            if isinstance(instance_id_value, str) and instance_id_value.strip() != "":
                referenced_instance_ids.append(instance_id_value.strip())
            if isinstance(instance_name_value, str) and instance_name_value.strip() != "":
                referenced_instance_names.append(instance_name_value.strip())

        template_object: Dict[str, Any] = {
            "template_id": template_id_text,
            "name": placeholder_name,
            # 占位模板默认按“物件”处理，避免引擎侧 entity_type 校验失败
            "entity_type": "物件",
            "description": "自动生成占位模板：用于补齐实体摆放引用闭包（原存档未导出该模板定义）。",
            "default_graphs": [],
            "default_variables": [],
            "default_components": [],
            "entity_config": {},
            "metadata": {
                "ugc": {
                    "placeholder": True,
                    "placeholder_kind": "instance_missing_template",
                    "referenced_by_instance_ids": referenced_instance_ids,
                    "referenced_by_instance_names": referenced_instance_names,
                }
            },
            "graph_variable_overrides": {},
            "updated_at": "",
        }
        _write_json_file(output_path, template_object)

        updated_templates_index.append(
            {
                "template_id": template_id_text,
                "name": placeholder_name,
                "entity_type": "物件",
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    updated_templates_index_sorted = sorted(
        updated_templates_index,
        key=lambda item: str(item.get("template_id", "")),
    )
    _write_json_file(template_directory / "templates_index.json", updated_templates_index_sorted)
    return updated_templates_index_sorted


