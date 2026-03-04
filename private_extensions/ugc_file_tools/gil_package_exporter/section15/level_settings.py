from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import (
    _try_extract_environment_level_from_env_config_entry,
    _try_extract_level_settings_env_payload,
)
from .context import Section15ExportContext


def export_level_settings_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    config_id = f"level_settings_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_level_settings_{entry_id_int}.pyugc.json"
    raw_file_path = context.level_settings_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)
    environment_level_value = _try_extract_environment_level_from_env_config_entry(section15_entry) or 0
    decoded_env_payload = _try_extract_level_settings_env_payload(section15_entry)
    decoded_env_rel_path: Optional[str] = None
    if decoded_env_payload is not None:
        decoded_file_path = context.level_settings_raw_directory / f"ugc_level_settings_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_env_payload)
        decoded_env_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")

    # 关卡设置字段补全：尽量对齐 Graph_Generater 的 LevelSettings schema。
    # 缺失字段用可编辑的默认值占位，推断结果与来源保存在 metadata.ugc 中。
    initial_time_hour_value = 0
    time_flow_ratio_value = 1.0
    load_optimization_value = True
    out_of_range_disabled_value = False

    factions: List[Dict[str, Any]] = []
    spawn_points: List[Dict[str, Any]] = []
    respawn_points: List[Dict[str, Any]] = []
    player_groups: List[Dict[str, Any]] = []
    spawn_shared_value = False

    derived_spawn_point_id: Optional[str] = None
    derived_spawn_point_output_rel_path: Optional[str] = None

    if isinstance(decoded_env_payload, dict):
        env_object = decoded_env_payload.get("env_object")
        if isinstance(env_object, dict):
            possible_initial_hour = env_object.get("2@int")
            if isinstance(possible_initial_hour, int) and 0 <= int(possible_initial_hour) <= 23:
                initial_time_hour_value = int(possible_initial_hour)

            possible_time_flow_ratio = env_object.get("9@float")
            if isinstance(possible_time_flow_ratio, (int, float)):
                time_flow_ratio_value = float(possible_time_flow_ratio)

            possible_load_optimization_flag = env_object.get("21@int")
            if isinstance(possible_load_optimization_flag, int):
                load_optimization_value = bool(int(possible_load_optimization_flag) != 0)

            possible_out_of_range_flag = env_object.get("22@int")
            if isinstance(possible_out_of_range_flag, int):
                out_of_range_disabled_value = bool(int(possible_out_of_range_flag) != 0)

        decoded_spawn_payload = decoded_env_payload.get("decoded_8@data")
        if isinstance(decoded_spawn_payload, dict):
            decoded_spawn_root = decoded_spawn_payload.get("decoded")
            if isinstance(decoded_spawn_root, dict):
                x_field = decoded_spawn_root.get("field_1")
                z_field = decoded_spawn_root.get("field_2")
                yaw_field = decoded_spawn_root.get("field_3")

                x_value = x_field.get("fixed32_float") if isinstance(x_field, dict) else None
                z_value = z_field.get("fixed32_float") if isinstance(z_field, dict) else None
                yaw_value = yaw_field.get("fixed32_float") if isinstance(yaw_field, dict) else None

                if (
                    isinstance(x_value, (int, float))
                    and isinstance(z_value, (int, float))
                    and isinstance(yaw_value, (int, float))
                ):
                    derived_spawn_point_id = f"point_spawn_{entry_id_int}__{context.package_namespace}"
                    derived_spawn_point_name = f"{entry_name}_出生点"
                    preset_point_object: Dict[str, Any] = {
                        "point_id": derived_spawn_point_id,
                        "point_name": derived_spawn_point_name,
                        "name": derived_spawn_point_name,
                        "position": [float(x_value), 0.0, float(z_value)],
                        "rotation": [0.0, float(yaw_value), 0.0],
                        "point_type": "spawn",
                        "tags": ["自动解析", "出生点"],
                        "description": "从关卡设置条目中抽取的出生点（由 decoded_8@data 推断坐标/朝向）。",
                        "metadata": {
                            "ugc": {
                                "source_level_settings_entry_id_int": entry_id_int,
                                "source_level_settings_config_id": config_id,
                                "source_pyugc_path": source_path_text,
                            }
                        },
                        "lock_transform": True,
                        "visible_in_scene": False,
                        "updated_at": "",
                    }
                    preset_point_file_name = _sanitize_filename(f"{derived_spawn_point_name}_{entry_id_int}") + ".json"
                    preset_point_output_path = context.preset_point_directory / preset_point_file_name
                    _write_json_file(preset_point_output_path, preset_point_object)
                    derived_spawn_point_output_rel_path = (
                        str(preset_point_output_path.relative_to(context.output_package_root)).replace("\\", "/")
                    )

                    result["preset_points"].append(
                        {
                            "point_id": derived_spawn_point_id,
                            "point_name": derived_spawn_point_name,
                            "output": derived_spawn_point_output_rel_path,
                        }
                    )

                    spawn_points.append(
                        {
                            "spawn_id": f"spawn_{entry_id_int}__{context.package_namespace}",
                            "spawn_name": derived_spawn_point_name,
                            "preset_point_id": derived_spawn_point_id,
                            "character_templates": [],
                            "shared": True,
                        }
                    )
                    respawn_points.append(
                        {
                            "respawn_id": f"respawn_{entry_id_int}__{context.package_namespace}",
                            "priority": 10,
                            "preset_point_id": derived_spawn_point_id,
                        }
                    )
                    spawn_shared_value = True

    level_settings_object: Dict[str, Any] = {
        "scene_range": "",
        "environment_level": environment_level_value,
        "initial_time_hour": int(initial_time_hour_value),
        "time_flow_ratio": float(time_flow_ratio_value),
        "load_optimization": bool(load_optimization_value),
        "out_of_range_disabled": bool(out_of_range_disabled_value),
        "hatred_type": "默认",
        "shield_calc_mode": "统一计算",
        "factions": factions,
        "spawn_shared": bool(spawn_shared_value),
        "spawn_points": spawn_points,
        "respawn_points": respawn_points,
        "player_groups": player_groups,
        "loading_bg_image": "",
        "loading_title": entry_name,
        "loading_description": "",
        "settlement_type": "",
        "enable_ranking": False,
        "level_name": entry_name,
        "level_description": "",
        "max_players": 0,
        "min_players": 0,
        "time_limit": 0.0,
        "victory_conditions": [],
        "defeat_conditions": [],
        "difficulty": "normal",
        "recommended_level": int(environment_level_value) if isinstance(environment_level_value, int) else 0,
        "config_id": config_id,
        "name": entry_name,
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_env_rel_path,
                "derived_spawn_point_id": derived_spawn_point_id,
                "derived_spawn_point_output": derived_spawn_point_output_rel_path,
            }
        },
        "updated_at": "",
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.level_settings_directory / output_file_name
    _write_json_file(output_path, level_settings_object)
    result["level_settings"].append(
        {
            "config_id": config_id,
            "level_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


