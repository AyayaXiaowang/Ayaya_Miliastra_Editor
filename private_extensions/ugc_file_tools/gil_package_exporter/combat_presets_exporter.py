from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .claude_files import _ensure_claude_for_directory
from .combat_presets_focus_graph import _scan_focus_graph_hits_in_template_entry
from .combat_presets_variables import (
    _build_level_variable_file_text,
    _extract_player_template_variables_from_template_entry,
)
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file, _write_text_file
from .pyugc_extractors import (
    _extract_section15_entry_id_int,
    _extract_section15_entry_type_code,
    _extract_template_entry_name,
)


def _extract_player_template_default_class_id_int(template_entry: Dict[str, Any]) -> Optional[int]:
    meta_list = template_entry.get("6")
    if not isinstance(meta_list, list):
        return None
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 3:
            continue
        container = meta_item.get("12 id3")
        if not isinstance(container, dict):
            continue
        class_id_value = container.get("5@int")
        if isinstance(class_id_value, int):
            return class_id_value
    return None


def _extract_player_class_name_from_class_entry(class_entry: Dict[str, Any]) -> str:
    meta_list = class_entry.get("4")
    if not isinstance(meta_list, list):
        return ""
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 1:
            continue
        container = meta_item.get("11 id1")
        if not isinstance(container, dict):
            continue
        name_value = container.get("1@string")
        if isinstance(name_value, str):
            return name_value
    return ""


def _try_extract_player_class_base_stats_from_class_entry(class_entry: Dict[str, Any]) -> Dict[str, Any]:
    """尝试从职业条目中提取基础属性与成长曲线引用等信息。"""
    meta_list = class_entry.get("4")
    if not isinstance(meta_list, list):
        return {}

    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 10:
            continue
        container = meta_item.get("18")
        if not isinstance(container, dict):
            continue
        stats_object = container.get("1")
        if not isinstance(stats_object, dict):
            continue

        result: Dict[str, Any] = {}
        if isinstance(stats_object.get("1@float"), float):
            result["base_health"] = float(stats_object["1@float"])
        if isinstance(stats_object.get("2@float"), float):
            result["base_attack"] = float(stats_object["2@float"])
        if isinstance(stats_object.get("3@float"), float):
            result["base_defense"] = float(stats_object["3@float"])
        if isinstance(stats_object.get("5@float"), float):
            result["base_speed"] = float(stats_object["5@float"])

        if isinstance(stats_object.get("4@int"), int):
            result["ugc_field_4_int"] = int(stats_object["4@int"])
        if isinstance(stats_object.get("501@int"), int):
            result["growth_curve_entry_id_int"] = int(stats_object["501@int"])
        return result

    return {}


def _try_extract_skill_bindings_from_player_class_entry(class_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从职业条目提取疑似技能绑定的 base64 并做通用解码（用于进一步提取 skill_id）。"""
    meta_list = class_entry.get("4")
    if not isinstance(meta_list, list):
        return []

    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 25:
            continue
        container = meta_item.get("34")
        if not isinstance(container, dict):
            continue
        binding_object = container.get("1")
        if not isinstance(binding_object, dict):
            continue

        base64_candidates: List[str] = []
        data_text = binding_object.get("2@data")
        if isinstance(data_text, str) and data_text:
            base64_candidates.append(data_text)

        list_texts = binding_object.get("6")
        if isinstance(list_texts, list):
            for item in list_texts:
                if isinstance(item, str) and item:
                    base64_candidates.append(item)

        decoded_records: List[Dict[str, Any]] = []
        for base64_text in base64_candidates:
            decoded_bytes = base64.b64decode(base64_text)
            decoded_object = decode_bytes_to_python(decoded_bytes)
            decoded_records.append(
                {
                    "base64": base64_text,
                    "byte_size": len(decoded_bytes),
                    "decoded": decoded_object,
                }
            )
        return decoded_records

    return []


def _export_player_templates_and_classes_from_pyugc_dump(
    *,
    pyugc_object: Any,
    output_package_root: Path,
    focus_graph_id: Optional[int],
) -> Dict[str, Any]:
    """
    从 root4['4']['1']（模板配置表）中导出：
    - 战斗预设/玩家模板（type=1000000）
    - 战斗预设/职业（通过玩家模板的默认职业 id 反查 root4['15']['1']）

    同时若提供 focus_graph_id，会在玩家模板中尝试定位与该 id 关联的 @data，并做通用解码落盘。
    """
    result: Dict[str, Any] = {
        "player_templates": [],
        "player_classes": [],
        "focus_graph_id": focus_graph_id,
        "focus_graph_hits": [],
    }

    if not isinstance(pyugc_object, dict):
        return result
    root4_object = pyugc_object.get("4")
    if not isinstance(root4_object, dict):
        return result

    templates_section = root4_object.get("4")
    if not isinstance(templates_section, dict):
        return result
    template_entries = templates_section.get("1")
    if not isinstance(template_entries, list):
        return result

    classes_section = root4_object.get("15")
    class_entries: Optional[List[Any]] = None
    if isinstance(classes_section, dict) and isinstance(classes_section.get("1"), list):
        class_entries = classes_section.get("1")

    package_namespace = output_package_root.name

    player_template_directory = output_package_root / "战斗预设" / "玩家模板"
    player_template_raw_directory = player_template_directory / "原始解析"
    _ensure_directory(player_template_raw_directory)
    _ensure_claude_for_directory(
        player_template_raw_directory,
        purpose="存放从 .gil 中解析得到的“玩家模板”原始结构与二次解码结果，用于对照与继续逆向。",
    )

    player_class_directory = output_package_root / "战斗预设" / "职业"
    player_class_raw_directory = player_class_directory / "原始解析"
    _ensure_directory(player_class_raw_directory)
    _ensure_claude_for_directory(
        player_class_raw_directory,
        purpose="存放从 .gil 中解析得到的“职业/玩家职业”原始结构，用于对照与继续逆向。",
    )

    node_graph_focus_directory: Optional[Path] = None
    if isinstance(focus_graph_id, int):
        node_graph_focus_directory = output_package_root / "节点图" / "原始解析" / f"graph_id_{focus_graph_id}"
        _ensure_directory(node_graph_focus_directory)
        _ensure_claude_for_directory(
            node_graph_focus_directory,
            purpose=f"存放针对节点图/节点ID={focus_graph_id} 的定向定位结果与通用解码输出。",
        )

    # root4['15']['1'] 实际包含 section15 的全部条目，这里我们仅筛出：
    # - 职业条目（type_code=4）
    # - 技能条目（type_code=6）：用于过滤技能绑定时的“已知 skill_id”
    class_entry_map: Dict[int, Tuple[int, Dict[str, Any]]] = {}
    skill_entry_id_set: set[int] = set()
    if isinstance(class_entries, list):
        for entry_index, section15_entry in enumerate(class_entries):
            if not isinstance(section15_entry, dict):
                continue
            entry_id_int = _extract_section15_entry_id_int(section15_entry)
            type_code_int = _extract_section15_entry_type_code(section15_entry)
            if entry_id_int is None or type_code_int is None:
                continue

            if type_code_int == 6:
                skill_entry_id_set.add(entry_id_int)

            if type_code_int != 4:
                continue
            class_entry_map[entry_id_int] = (entry_index, section15_entry)

    for template_entry_index, template_entry in enumerate(template_entries):
        if not isinstance(template_entry, dict):
            continue
        type_list = template_entry.get("2")
        if not isinstance(type_list, list) or not type_list:
            continue
        type_value = type_list[0]
        if type_value != 1000000:
            continue

        template_id_list = template_entry.get("1")
        if not isinstance(template_id_list, list) or not template_id_list:
            continue
        template_id_int = template_id_list[0]
        if not isinstance(template_id_int, int):
            continue

        template_name = _extract_template_entry_name(template_entry)
        if template_name == "":
            template_name = f"player_template_{template_id_int}"

        extracted_variables = _extract_player_template_variables_from_template_entry(template_entry)

        default_class_id_int = _extract_player_template_default_class_id_int(template_entry)
        default_class_id = (
            f"player_class_{default_class_id_int}__{package_namespace}"
            if isinstance(default_class_id_int, int)
            else ""
        )

        player_template_id = f"player_template_{template_id_int}__{package_namespace}"

        raw_template_file_name = f"ugc_player_template_{template_id_int}.pyugc.json"
        raw_template_rel_path = (player_template_raw_directory / raw_template_file_name).relative_to(
            output_package_root
        )
        _write_json_file(player_template_raw_directory / raw_template_file_name, template_entry)

        variables_file_name = f"ugc_player_template_{template_id_int}.variables.json"
        variables_rel_path = (player_template_raw_directory / variables_file_name).relative_to(
            output_package_root
        )
        _write_json_file(player_template_raw_directory / variables_file_name, extracted_variables)

        variable_file_id = f"player_template_{template_id_int}_variables__{package_namespace}"
        variable_file_name = f"{template_name}_变量"

        level_variable_directory = output_package_root / "管理配置" / "关卡变量" / "自定义变量"
        _ensure_directory(level_variable_directory)
        variable_python_file_name = _sanitize_filename(f"{template_name}_变量_{template_id_int}") + ".py"
        variable_python_file_path = level_variable_directory / variable_python_file_name
        level_variable_file_text = _build_level_variable_file_text(
            variable_file_id=variable_file_id,
            variable_file_name=variable_file_name,
            variables=extracted_variables,
            package_namespace=package_namespace,
            template_id_int=template_id_int,
        )
        _write_text_file(variable_python_file_path, level_variable_file_text)

        decoded_focus_hits: List[Dict[str, Any]] = []
        if isinstance(focus_graph_id, int) and node_graph_focus_directory is not None:
            decoded_focus_hits = _scan_focus_graph_hits_in_template_entry(
                template_entry=template_entry,
                template_entry_path=f"4/4/1/[{template_entry_index}]",
                template_id_int=template_id_int,
                template_name=template_name,
                focus_graph_id=focus_graph_id,
                node_graph_focus_directory=node_graph_focus_directory,
                output_package_root=output_package_root,
            )

        player_template_object: Dict[str, Any] = {
            "id": player_template_id,
            "template_id": player_template_id,
            "template_name": template_name,
            "name": template_name,
            "description": "",
            "level": 1,
            "default_profession_id": default_class_id,
            "metadata": {
                "custom_variable_file": variable_file_id,
                "ugc": {
                    "source_template_id_int": template_id_int,
                    "source_pyugc_path": f"4/4/1/[{template_entry_index}]",
                    "raw_pyugc_entry": str(raw_template_rel_path).replace("\\", "/"),
                    "extracted_variables": str(variables_rel_path).replace("\\", "/"),
                    "exported_level_variable_file": str(
                        variable_python_file_path.relative_to(output_package_root)
                    ).replace("\\", "/"),
                    "default_class_id_int": default_class_id_int,
                    "focus_graph_id_hits": decoded_focus_hits,
                },
            },
        }

        output_file_name = _sanitize_filename(f"{template_name}_{template_id_int}") + ".json"
        output_path = player_template_directory / output_file_name
        _write_json_file(output_path, player_template_object)

        result["player_templates"].append(
            {
                "template_id": player_template_id,
                "template_name": template_name,
                "default_profession_id": default_class_id,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

        for hit in decoded_focus_hits:
            result["focus_graph_hits"].append(hit)

    # 全量导出职业（type_code=4）
    for class_id_int, (class_entry_index, class_entry) in sorted(
        class_entry_map.items(),
        key=lambda item: item[0],
    ):
        class_name = _extract_player_class_name_from_class_entry(class_entry)
        if class_name == "":
            class_name = f"player_class_{class_id_int}"

        player_class_id = f"player_class_{class_id_int}__{package_namespace}"

        raw_class_file_name = f"ugc_player_class_{class_id_int}.pyugc.json"
        raw_class_path = player_class_raw_directory / raw_class_file_name
        raw_class_rel_path = raw_class_path.relative_to(output_package_root)
        _write_json_file(raw_class_path, class_entry)

        base_stats = _try_extract_player_class_base_stats_from_class_entry(class_entry)
        decoded_skill_bindings = _try_extract_skill_bindings_from_player_class_entry(class_entry)
        decoded_skill_bindings_rel_path: Optional[str] = None
        if decoded_skill_bindings:
            decoded_file_path = player_class_raw_directory / f"ugc_player_class_{class_id_int}.skills.decoded.json"
            _write_json_file(decoded_file_path, decoded_skill_bindings)
            decoded_skill_bindings_rel_path = (
                str(decoded_file_path.relative_to(output_package_root)).replace("\\", "/")
            )

        skill_binding_details: List[Dict[str, Any]] = []
        skill_binding_pairs: List[Tuple[int, int]] = []
        for record in decoded_skill_bindings:
            decoded_object = record.get("decoded")
            if not isinstance(decoded_object, dict):
                continue

            order_value = 0
            field_1 = decoded_object.get("field_1")
            if isinstance(field_1, dict) and isinstance(field_1.get("int"), int):
                order_value = int(field_1.get("int"))

            skill_entry_id_int: Optional[int] = None
            field_2 = decoded_object.get("field_2")
            if isinstance(field_2, dict) and isinstance(field_2.get("int"), int):
                skill_entry_id_int = int(field_2.get("int"))

            if skill_entry_id_int is None:
                continue

            is_known_skill = skill_entry_id_int in skill_entry_id_set
            skill_binding_details.append(
                {
                    "order": order_value,
                    "skill_entry_id_int": skill_entry_id_int,
                    "is_known_skill": is_known_skill,
                    "base64": str(record.get("base64", "")),
                }
            )
            if is_known_skill:
                skill_binding_pairs.append((order_value, skill_entry_id_int))

        sorted_pairs = sorted(skill_binding_pairs, key=lambda pair: (pair[0], pair[1]))
        unique_skill_ids: List[int] = []
        seen_skill_ids: set[int] = set()
        for _order_value, skill_entry_id_int in sorted_pairs:
            if skill_entry_id_int in seen_skill_ids:
                continue
            seen_skill_ids.add(skill_entry_id_int)
            unique_skill_ids.append(skill_entry_id_int)

        skill_id_list = [
            f"skill_{skill_entry_id_int}__{package_namespace}"
            for skill_entry_id_int in unique_skill_ids
        ]

        growth_curve_entry_id_int = base_stats.get("growth_curve_entry_id_int")
        growth_curve_id = (
            f"growth_curve_{growth_curve_entry_id_int}__{package_namespace}"
            if isinstance(growth_curve_entry_id_int, int)
            else ""
        )

        player_class_object: Dict[str, Any] = {
            "id": player_class_id,
            "class_id": player_class_id,
            "class_name": class_name,
            "name": class_name,
            "description": "",
            "base_health": float(base_stats.get("base_health", 100.0)),
            "base_attack": float(base_stats.get("base_attack", 10.0)),
            "base_defense": float(base_stats.get("base_defense", 5.0)),
            "base_speed": float(base_stats.get("base_speed", 5.0)),
            "skill_list": skill_id_list,
            "metadata": {
                "ugc": {
                    "source_class_id_int": class_id_int,
                    "source_pyugc_path": f"4/15/1/[{class_entry_index}]",
                    "raw_pyugc_entry": str(raw_class_rel_path).replace("\\", "/"),
                    "base_stats": base_stats,
                    "growth_curve_entry_id_int": growth_curve_entry_id_int,
                    "growth_curve_id": growth_curve_id,
                    "decoded_skill_bindings": decoded_skill_bindings_rel_path,
                    "skill_bindings": skill_binding_details,
                }
            },
        }

        class_output_file_name = _sanitize_filename(f"{class_name}_{class_id_int}") + ".json"
        class_output_path = player_class_directory / class_output_file_name
        _write_json_file(class_output_path, player_class_object)

        result["player_classes"].append(
            {
                "class_id": player_class_id,
                "class_name": class_name,
                "output": str(class_output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    _write_json_file(
        player_template_directory / "player_templates_index.json",
        sorted(result["player_templates"], key=lambda item: str(item.get("template_id", ""))),
    )
    _write_json_file(
        player_class_directory / "player_classes_index.json",
        sorted(result["player_classes"], key=lambda item: str(item.get("class_id", ""))),
    )
    if node_graph_focus_directory is not None:
        _write_json_file(
            node_graph_focus_directory / "hits_index.json",
            sorted(
                result["focus_graph_hits"],
                key=lambda item: (str(item.get("template_entry_id_int", "")), str(item.get("path", ""))),
            ),
        )

    return result


