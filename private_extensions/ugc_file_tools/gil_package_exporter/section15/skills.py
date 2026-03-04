from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python

from ..file_io import _sanitize_filename, _write_json_file
from .context import Section15ExportContext


def _infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    """
    根据 graph_id 的高位前缀推断节点图类型：
    - 0x40000000: server
    - 0x40800000: client

    说明：
    - 这是经验规则，用于“占位图生成/引用归类”；若遇到未知前缀则返回 unknown。
    """
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    return "unknown"


def export_skill_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_index: int,
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    skill_id = f"skill_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_skill_{entry_id_int}.pyugc.json"
    raw_file_path = context.skill_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    # 解析技能挂载的节点图引用（若存在）
    #
    # 已知来源：
    # - meta id=35（45 id35）下的：
    #   - 1/7: 直接挂载的 graph_id（常见为 server）
    #   - 1/6: (client_graph_id, server_graph_id) 对（常用于“动画/连击阶段→触发节点图”）
    # - meta id=21（30 id21）下的：
    #   - 1/5: (client_graph_id, server_graph_id) 对（常用于“切换界面”等简单技能）
    skill_graph_ids: List[str] = []
    graph_mounts_raw: List[Dict[str, Any]] = []
    referenced_graph_id_ints: List[int] = []
    seen_graph_ids: set[int] = set()

    def add_graph_reference(graph_id_int: int, mount_record: Dict[str, Any], source_hint: str) -> None:
        graph_scope = _infer_graph_scope_from_id_int(graph_id_int)
        mount_record["graph_id_int"] = int(graph_id_int)
        mount_record["graph_scope"] = graph_scope
        mount_record["source_hint"] = source_hint
        graph_mounts_raw.append(mount_record)

        if int(graph_id_int) not in seen_graph_ids:
            seen_graph_ids.add(int(graph_id_int))
            referenced_graph_id_ints.append(int(graph_id_int))

        if graph_scope == "client":
            graph_id_text = f"client_graph_{int(graph_id_int)}__{context.package_namespace}"
            if graph_id_text not in skill_graph_ids:
                skill_graph_ids.append(graph_id_text)

        # 当前占位图生成只面向 server graph；client graph 通常能在 pyugc_graphs 中定位到。
        if graph_scope == "server":
            context.referenced_graph_sources.setdefault(int(graph_id_int), []).append(
                {
                    "source_kind": "skill",
                    "skill_entry_id_int": entry_id_int,
                    "skill_id": skill_id,
                    "skill_name": entry_name,
                    "source_pyugc_path": source_path_text,
                    "source_hint": source_hint,
                }
            )

    meta_list = section15_entry.get("4")
    if isinstance(meta_list, list):
        for meta_item in meta_list:
            if not isinstance(meta_item, dict):
                continue

            meta_id_value = meta_item.get("1 id@int")
            if meta_id_value == 35:
                container = meta_item.get("45 id35")
                if not isinstance(container, dict):
                    continue
                container_root = container.get("1")
                if not isinstance(container_root, dict):
                    continue

                direct_mounts = container_root.get("7")
                if isinstance(direct_mounts, list):
                    for mount in direct_mounts:
                        if not isinstance(mount, dict):
                            continue
                        graph_id_value = mount.get("6@int")
                        if not isinstance(graph_id_value, int):
                            continue
                        add_graph_reference(
                            int(graph_id_value),
                            dict(mount),
                            source_hint="skill/meta35/45/1/7/6@int",
                        )

                paired_mounts = container_root.get("6")
                if isinstance(paired_mounts, list):
                    for mount in paired_mounts:
                        if not isinstance(mount, dict):
                            continue
                        client_graph_id_value = mount.get("1@int")
                        server_graph_id_value = mount.get("5@int")

                        if isinstance(client_graph_id_value, int):
                            client_record = dict(mount)
                            if isinstance(server_graph_id_value, int):
                                client_record["paired_server_graph_id_int"] = int(server_graph_id_value)
                            add_graph_reference(
                                int(client_graph_id_value),
                                client_record,
                                source_hint="skill/meta35/45/1/6/1@int",
                            )

                        if isinstance(server_graph_id_value, int):
                            server_record = dict(mount)
                            if isinstance(client_graph_id_value, int):
                                server_record["paired_client_graph_id_int"] = int(client_graph_id_value)
                            add_graph_reference(
                                int(server_graph_id_value),
                                server_record,
                                source_hint="skill/meta35/45/1/6/5@int",
                            )

            if meta_id_value == 21:
                container = meta_item.get("30 id21")
                if not isinstance(container, dict):
                    continue
                core_object = container.get("1")
                if not isinstance(core_object, dict):
                    continue
                paired_graphs = core_object.get("5")
                if not isinstance(paired_graphs, list):
                    continue
                for pair_record in paired_graphs:
                    if not isinstance(pair_record, dict):
                        continue
                    client_graph_id_value = pair_record.get("1@int")
                    server_graph_id_value = pair_record.get("2@int")

                    if isinstance(client_graph_id_value, int):
                        client_record = dict(pair_record)
                        if isinstance(server_graph_id_value, int):
                            client_record["paired_server_graph_id_int"] = int(server_graph_id_value)
                        add_graph_reference(
                            int(client_graph_id_value),
                            client_record,
                            source_hint="skill/meta21/30/1/5/1@int",
                        )

                    if isinstance(server_graph_id_value, int):
                        server_record = dict(pair_record)
                        if isinstance(client_graph_id_value, int):
                            server_record["paired_client_graph_id_int"] = int(client_graph_id_value)
                        add_graph_reference(
                            int(server_graph_id_value),
                            server_record,
                            source_hint="skill/meta21/30/1/5/2@int",
                        )

    # 解码技能条目中常见的主数据块（meta id=21 下的 6@data）
    decoded_primary_data_rel_path: Optional[str] = None
    primary_data_text: Optional[str] = None
    if isinstance(meta_list, list):
        for meta_item in meta_list:
            if not isinstance(meta_item, dict):
                continue
            if meta_item.get("1 id@int") != 21:
                continue
            container = meta_item.get("30 id21")
            if not isinstance(container, dict):
                continue
            core_object = container.get("1")
            if not isinstance(core_object, dict):
                continue
            data_text = core_object.get("6@data")
            if isinstance(data_text, str) and data_text:
                primary_data_text = data_text
                break
    if isinstance(primary_data_text, str) and primary_data_text:
        decoded_bytes = base64.b64decode(primary_data_text)
        decoded_primary_data = {
            "base64": primary_data_text,
            "byte_size": len(decoded_bytes),
            "decoded": decode_bytes_to_python(decoded_bytes),
        }
        decoded_file_path = context.skill_raw_directory / f"ugc_skill_{entry_id_int}.primary_data.decoded.json"
        _write_json_file(decoded_file_path, decoded_primary_data)
        decoded_primary_data_rel_path = (
            str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")
        )

    # 尝试解析技能冷却（meta id=21 下的数值段）。当前使用启发式：
    # - 若字段值 >= 100：视为毫秒（ms），换算为秒
    # - 否则：视为秒
    cooldown_seconds_value = 0.0
    cooldown_raw_int: Optional[int] = None
    meta21_numeric_candidate: Optional[Dict[str, Any]] = None
    if isinstance(meta_list, list):
        for meta_item in meta_list:
            if not isinstance(meta_item, dict):
                continue
            if meta_item.get("1 id@int") != 21:
                continue
            container = meta_item.get("30 id21")
            if not isinstance(container, dict):
                continue
            core_object = container.get("1")
            if not isinstance(core_object, dict):
                continue
            numeric_object = core_object.get("3")
            if isinstance(numeric_object, dict):
                meta21_numeric_candidate = numeric_object
                raw_value = numeric_object.get("3@int")
                if isinstance(raw_value, int):
                    cooldown_raw_int = int(raw_value)
                    cooldown_seconds_value = (
                        float(cooldown_raw_int) / 1000.0 if cooldown_raw_int >= 100 else float(cooldown_raw_int)
                    )
                break

    # 消耗字段：目前仅做保守推断。
    # - 优先使用 meta21 数值段中的 15@float（在 test2 中 UI 切换技能为 1.0，武器技能为 10.0），
    #   仅当其 > 1.0 时才写入到 cost_value，避免把默认占位值误当作真实消耗。
    cost_value_value = 0.0
    if isinstance(meta21_numeric_candidate, dict):
        cost_candidate = meta21_numeric_candidate.get("15@float")
        if isinstance(cost_candidate, (int, float)) and float(cost_candidate) > 1.0:
            cost_value_value = float(cost_candidate)

    skill_object: Dict[str, Any] = {
        "id": skill_id,
        "skill_id": skill_id,
        "skill_name": entry_name,
        "name": entry_name,
        "description": "",
        "cooldown": float(cooldown_seconds_value),
        "cost_type": "mana",
        "cost_value": float(cost_value_value),
        "damage": 0.0,
        "damage_type": "physical",
        "range_value": 0.0,
        "cast_time": 0.0,
        "animation": "",
        "effects": [],
        "ability_units": [],
        "metadata": {
            "skill_editor": {
                "basic": {},
                "combo": {},
                "numeric": {},
                "lifecycle": {},
                # 技能节点图挂载：必须为 graph_id 字符串列表（供编辑器 GraphsTab 直接加载）
                "graphs": list(skill_graph_ids),
                "graph_variable_overrides": {},
            },
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded_primary_data": decoded_primary_data_rel_path,
                "referenced_graph_id_ints": referenced_graph_id_ints,
                "skill_graph_mounts_raw": graph_mounts_raw,
                "meta21_cooldown_raw_int": cooldown_raw_int,
                "meta21_numeric_candidate": meta21_numeric_candidate,
            },
        },
        "updated_at": "",
        "last_modified": "",
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.skill_directory / output_file_name
    _write_json_file(output_path, skill_object)
    result["skills"].append(
        {
            "skill_id": skill_id,
            "skill_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


