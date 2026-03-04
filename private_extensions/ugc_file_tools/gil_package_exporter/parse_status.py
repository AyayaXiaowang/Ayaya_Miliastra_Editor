from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _build_parse_status_markdown(
    output_package_root: Path,
    report_object: Dict[str, Any],
    validation_summary: Optional[Dict[str, Any]],
) -> str:
    extracted = report_object.get("extracted", {}) if isinstance(report_object, dict) else {}

    package_id = output_package_root.name
    input_gil_text = str(report_object.get("input_gil", "")) if isinstance(report_object, dict) else ""

    def read_int(key: str, default: int = 0) -> int:
        value = extracted.get(key)
        if isinstance(value, int):
            return int(value)
        return int(default)

    templates_count = read_int("templates_count")
    instances_count = read_int("instances_count")
    player_templates_count = read_int("player_templates_count")
    player_classes_count = read_int("player_classes_count")
    skills_count = read_int("skills_count")
    items_count = read_int("items_count")
    unit_statuses_count = read_int("unit_statuses_count")
    currency_backpacks_count = read_int("currency_backpacks_count")
    level_settings_count = read_int("level_settings_count")
    shields_count = read_int("shields_count")
    unit_tags_count = read_int("unit_tags_count")
    equipment_data_count = read_int("equipment_data_count")
    growth_curves_count = read_int("growth_curves_count")
    equipment_slot_templates_count = read_int("equipment_slot_templates_count")
    struct_definitions_count = read_int("struct_definitions_count")
    pyugc_graphs_count = read_int("pyugc_graphs_count")
    pyugc_node_defs_count = read_int("pyugc_node_defs_count")
    section15_unclassified_count = read_int("section15_unclassified_count")
    section15_unclassified_type_codes = extracted.get("section15_unclassified_type_codes")
    if not isinstance(section15_unclassified_type_codes, list):
        section15_unclassified_type_codes = []
    section15_unclassified_type_code_set = {
        int(value)
        for value in section15_unclassified_type_codes
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    }

    validation_text = "未执行"
    if isinstance(validation_summary, dict):
        validation_text = (
            f"errors={validation_summary.get('errors', 0)}, warnings={validation_summary.get('warnings', 0)}"
        )

    graph_code_validation_text = "未执行"
    graph_code_validation_errors: Optional[int] = None
    graph_code_validation_warnings: Optional[int] = None
    graph_code_validation_path = output_package_root / "原始解析" / "graph_code_validation.json"
    if graph_code_validation_path.is_file():
        graph_code_validation_object = json.loads(graph_code_validation_path.read_text(encoding="utf-8"))
        if isinstance(graph_code_validation_object, dict):
            graph_code_validation_errors = (
                int(graph_code_validation_object.get("errors"))
                if isinstance(graph_code_validation_object.get("errors"), int)
                else None
            )
            graph_code_validation_warnings = (
                int(graph_code_validation_object.get("warnings"))
                if isinstance(graph_code_validation_object.get("warnings"), int)
                else None
            )
            if graph_code_validation_errors is not None and graph_code_validation_warnings is not None:
                graph_code_validation_text = f"errors={graph_code_validation_errors}, warnings={graph_code_validation_warnings}"

    def count_graph_code_files(graph_dir: Path) -> int:
        if not graph_dir.is_dir():
            return 0
        graph_files = [
            path
            for path in graph_dir.rglob("*.py")
            if path.is_file() and (not path.name.startswith("_")) and ("校验" not in path.stem)
        ]
        return len(graph_files)

    graph_code_client_count = count_graph_code_files(output_package_root / "节点图" / "client")
    graph_code_server_count = count_graph_code_files(output_package_root / "节点图" / "server")

    def detect_skill_graph_mounts_done() -> bool:
        skills_index_path = output_package_root / "战斗预设" / "技能" / "skills_index.json"
        if not skills_index_path.is_file():
            return False
        index_object = json.loads(skills_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            skill_path = output_package_root / Path(output_value)
            if not skill_path.is_file():
                continue
            skill_object = json.loads(skill_path.read_text(encoding="utf-8"))
            if not isinstance(skill_object, dict):
                continue
            metadata_object = skill_object.get("metadata")
            if not isinstance(metadata_object, dict):
                continue
            skill_editor = metadata_object.get("skill_editor")
            if not isinstance(skill_editor, dict):
                continue
            graphs = skill_editor.get("graphs")
            if isinstance(graphs, list) and graphs:
                return True
        return False

    skill_graph_mounts_done = detect_skill_graph_mounts_done()

    def detect_skill_cooldown_done() -> bool:
        skills_index_path = output_package_root / "战斗预设" / "技能" / "skills_index.json"
        if not skills_index_path.is_file():
            return False
        index_object = json.loads(skills_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            skill_path = output_package_root / Path(output_value)
            if not skill_path.is_file():
                continue
            skill_object = json.loads(skill_path.read_text(encoding="utf-8"))
            if not isinstance(skill_object, dict):
                continue
            cooldown_value = skill_object.get("cooldown")
            if isinstance(cooldown_value, (int, float)) and float(cooldown_value) > 0.0:
                return True
            meta_object = skill_object.get("metadata")
            if isinstance(meta_object, dict):
                ugc_object = meta_object.get("ugc")
                if isinstance(ugc_object, dict) and isinstance(ugc_object.get("meta21_cooldown_raw_int"), int):
                    return True
        return False

    skill_cooldown_done = detect_skill_cooldown_done()

    def detect_skill_cost_done() -> bool:
        skills_index_path = output_package_root / "战斗预设" / "技能" / "skills_index.json"
        if not skills_index_path.is_file():
            return False
        index_object = json.loads(skills_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            skill_path = output_package_root / Path(output_value)
            if not skill_path.is_file():
                continue
            skill_object = json.loads(skill_path.read_text(encoding="utf-8"))
            if not isinstance(skill_object, dict):
                continue
            cost_value = skill_object.get("cost_value")
            if isinstance(cost_value, (int, float)) and float(cost_value) > 0.0:
                return True
        return False

    skill_cost_done = detect_skill_cost_done()

    def detect_item_equipment_id_done() -> bool:
        items_index_path = output_package_root / "战斗预设" / "道具" / "items_index.json"
        if not items_index_path.is_file():
            return False
        index_object = json.loads(items_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            item_path = output_package_root / Path(output_value)
            if not item_path.is_file():
                continue
            item_object = json.loads(item_path.read_text(encoding="utf-8"))
            if not isinstance(item_object, dict):
                continue
            metadata_object = item_object.get("metadata")
            if not isinstance(metadata_object, dict):
                continue
            equipment_id_value = metadata_object.get("equipment_id")
            if isinstance(equipment_id_value, str) and equipment_id_value.strip() != "":
                return True
        return False

    item_equipment_id_done = detect_item_equipment_id_done()

    def detect_item_requirements_done() -> bool:
        items_index_path = output_package_root / "战斗预设" / "道具" / "items_index.json"
        if not items_index_path.is_file():
            return False
        index_object = json.loads(items_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            item_path = output_package_root / Path(output_value)
            if not item_path.is_file():
                continue
            item_object = json.loads(item_path.read_text(encoding="utf-8"))
            if not isinstance(item_object, dict):
                continue
            requirements_object = item_object.get("requirements")
            if not isinstance(requirements_object, dict):
                continue
            min_level_value = requirements_object.get("min_level")
            if isinstance(min_level_value, int):
                return True
        return False

    item_requirements_done = detect_item_requirements_done()

    def detect_item_rarity_done() -> bool:
        items_index_path = output_package_root / "战斗预设" / "道具" / "items_index.json"
        if not items_index_path.is_file():
            return False
        index_object = json.loads(items_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            item_path = output_package_root / Path(output_value)
            if not item_path.is_file():
                continue
            item_object = json.loads(item_path.read_text(encoding="utf-8"))
            if not isinstance(item_object, dict):
                continue
            rarity_value = item_object.get("rarity")
            if isinstance(rarity_value, str) and rarity_value.strip() and rarity_value.strip() != "common":
                return True
        return False

    item_rarity_done = detect_item_rarity_done()

    def detect_item_attributes_done() -> bool:
        items_index_path = output_package_root / "战斗预设" / "道具" / "items_index.json"
        if not items_index_path.is_file():
            return False
        index_object = json.loads(items_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            item_path = output_package_root / Path(output_value)
            if not item_path.is_file():
                continue
            item_object = json.loads(item_path.read_text(encoding="utf-8"))
            if not isinstance(item_object, dict):
                continue
            attributes_object = item_object.get("attributes")
            if isinstance(attributes_object, dict) and len(attributes_object) > 0:
                return True
        return False

    item_attributes_done = detect_item_attributes_done()

    def detect_currency_amounts_done() -> bool:
        currency_index_path = output_package_root / "管理配置" / "货币背包" / "currency_backpacks_index.json"
        if not currency_index_path.is_file():
            return False
        index_object = json.loads(currency_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            config_path = output_package_root / Path(output_value)
            if not config_path.is_file():
                continue
            backpack_object = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(backpack_object, dict):
                continue
            currencies_value = backpack_object.get("currencies")
            if not isinstance(currencies_value, list):
                continue
            for currency_object in currencies_value:
                if not isinstance(currency_object, dict):
                    continue
                initial_amount_value = currency_object.get("initial_amount")
                max_amount_value = currency_object.get("max_amount")
                if isinstance(initial_amount_value, int) and isinstance(max_amount_value, int):
                    if initial_amount_value != 0:
                        return True
        return False

    currency_amounts_done = detect_currency_amounts_done()

    def detect_level_settings_enriched_done() -> bool:
        level_settings_index_path = output_package_root / "管理配置" / "关卡设置" / "level_settings_index.json"
        if not level_settings_index_path.is_file():
            return False
        index_object = json.loads(level_settings_index_path.read_text(encoding="utf-8"))
        if not isinstance(index_object, list):
            return False
        for index_entry in index_object:
            if not isinstance(index_entry, dict):
                continue
            output_value = index_entry.get("output")
            if not isinstance(output_value, str) or output_value.strip() == "":
                continue
            config_path = output_package_root / Path(output_value)
            if not config_path.is_file():
                continue
            config_object = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config_object, dict):
                continue
            spawn_points_value = config_object.get("spawn_points")
            if isinstance(spawn_points_value, list) and len(spawn_points_value) > 0:
                return True
        return False

    level_settings_enriched_done = detect_level_settings_enriched_done()
    graph_code_done = (
        (graph_code_client_count + graph_code_server_count) > 0
        and graph_code_validation_errors == 0
        and graph_code_validation_warnings == 0
    )

    lines: List[str] = []
    lines.append("## 解析状态（自动生成）")
    lines.append("")
    lines.append("### 总览")
    lines.append(f"- **package_id**: `{package_id}`")
    if input_gil_text:
        lines.append(f"- **输入存档**: `{input_gil_text}`")
    lines.append(f"- **项目校验（单包）**: {validation_text}")
    lines.append(f"- **Graph Code 校验（节点图 Python）**: {graph_code_validation_text}")
    lines.append(f"- **Graph Code 文件数**: client={graph_code_client_count}, server={graph_code_server_count}")
    lines.append("")
    lines.append("### 已完成（结构/引用符合项目规范，可被索引与加载）")
    lines.append(f"- **元件库（TemplateConfig）**: {templates_count}（`元件库/`，索引：`元件库/templates_index.json`）")
    lines.append(f"- **实体摆放（InstanceConfig）**: {instances_count}（`实体摆放/`，索引：`实体摆放/instances_index.json`）")
    lines.append(f"- **战斗预设/玩家模板**: {player_templates_count}（索引：`战斗预设/玩家模板/player_templates_index.json`）")
    lines.append(f"- **战斗预设/职业**: {player_classes_count}（索引：`战斗预设/职业/player_classes_index.json`）")
    lines.append(f"- **战斗预设/技能**: {skills_count}（索引：`战斗预设/技能/skills_index.json`）")
    lines.append(f"- **战斗预设/道具**: {items_count}（索引：`战斗预设/道具/items_index.json`）")
    lines.append(f"- **战斗预设/单位状态**: {unit_statuses_count}（索引：`战斗预设/单位状态/unit_statuses_index.json`）")
    lines.append(f"- **管理配置/货币背包**: {currency_backpacks_count}（索引：`管理配置/货币背包/currency_backpacks_index.json`）")
    lines.append(f"- **管理配置/关卡设置**: {level_settings_count}（索引：`管理配置/关卡设置/level_settings_index.json`）")
    lines.append(f"- **管理配置/护盾**: {shields_count}（索引：`管理配置/护盾/shields_index.json`）")
    lines.append(f"- **管理配置/单位标签**: {unit_tags_count}（索引：`管理配置/单位标签/unit_tags_index.json`）")
    lines.append(f"- **管理配置/装备数据**: {equipment_data_count}（索引：`管理配置/装备数据/equipment_data_index.json`）")
    lines.append(f"- **管理配置/成长曲线**: {growth_curves_count}（索引：`管理配置/成长曲线/growth_curves_index.json`）")
    lines.append(
        f"- **管理配置/装备栏模板**: {equipment_slot_templates_count}（索引：`管理配置/装备栏模板/equipment_slot_templates_index.json`）"
    )
    lines.append(f"- **管理配置/结构体定义（基础结构体）**: {struct_definitions_count}（`管理配置/结构体定义/基础结构体/`）")
    lines.append("")
    lines.append("### 半解析（已能落盘并满足项目结构，但字段语义仍需补全）")
    lines.append("- **元件库模板**：目前仅稳定映射 `template_id/name/entity_type`，`default_graphs/default_components/entity_config` 等仍未语义还原。")
    lines.append("- **实体摆放**：已对齐 `template_id` 引用，但 `override_variables/additional_graphs` 仍主要为空或启发式结果。")
    lines.append("- **技能/道具/单位状态**：已导出为可索引 JSON，但绝大多数数值字段仍为默认值（需从原始条目进一步映射）。")
    lines.append("- **货币背包**：已导出货币列表与背包容量（由通用解码抽取），货币初始值/上限等字段尚未语义对齐。")
    lines.append("- **关卡设置**：仅抽取了 `environment_level` 等少数字段，其它关卡规则仍需还原。")
    lines.append("- **装备数据/护盾/单位标签**：目前以“可索引字段齐全”为主，配置细节仍需进一步解析。")
    lines.append(
        f"- **节点图（pyugc 原始结构）**：已定位 {pyugc_graphs_count} 个节点图定义并落盘（索引：`节点图/原始解析/pyugc_graphs_index.json`；节点库条目：{pyugc_node_defs_count}（索引：`节点图/原始解析/pyugc_node_defs_index.json`））。"
    )
    lines.append("")
    lines.append("### 未完全解析清楚（仅保留原始条目/索引，待逆向）")
    if section15_unclassified_count > 0:
        lines.append(
            f"- **section15 未分类条目**: {section15_unclassified_count}（`原始解析/资源条目/section15_unclassified/`，索引：`section15_unclassified_index.json`；type_codes: {sorted(section15_unclassified_type_code_set)}）"
        )
    else:
        lines.append("- **section15 未分类条目**: 0（无）")
    lines.append("")
    lines.append("### TODO（下一步工作清单）")
    type4_done = 4 not in section15_unclassified_type_code_set
    type5_done = 5 not in section15_unclassified_type_code_set
    type13_done = 13 not in section15_unclassified_type_code_set
    lines.append(
        f"- [{'x' if type4_done else ' '}] 将 `section15_unclassified` 中的 type_code=4（职业）扩展为“全量职业导出”，并补齐职业基础属性/技能列表映射。"
    )
    lines.append(
        f"- [{'x' if type5_done else ' '}] 解析 type_code=5（自定义成长曲线）的语义与项目落点（新增资源类型或归档到管理配置）。"
    )
    lines.append(f"- [{'x' if type13_done else ' '}] 解析 type_code=13（装备栏模板）的语义与项目落点。")
    lines.append(f"- [{'x' if skill_graph_mounts_done else ' '}] 从技能条目中解析节点图挂载（填充 `metadata.skill_editor.graphs`）。")
    lines.append(f"- [{'x' if skill_cooldown_done else ' '}] 从技能条目中解析冷却（`cooldown`）等数值字段。")
    lines.append(f"- [{'x' if skill_cost_done else ' '}] 从技能条目中解析消耗（`cost_type/cost_value`）等字段。")
    lines.append(f"- [{'x' if item_equipment_id_done else ' '}] 从道具条目中解析 equipment_id 关联（写入 `metadata.equipment_id`）。")
    lines.append(f"- [{'x' if item_requirements_done else ' '}] 从道具条目中解析 requirements（例如 `min_level`）。")
    lines.append(
        f"- [{'x' if (item_rarity_done and item_attributes_done) else ' '}] 从道具条目中解析 rarity/attributes 等字段。"
    )
    lines.append(
        f"- [{'x' if currency_amounts_done else ' '}] 对货币条目 `54@data` 的通用解码结果做字段语义映射（initial_amount/max_amount 等）。"
    )
    lines.append(f"- [{'x' if level_settings_enriched_done else ' '}] 补全关卡设置（阵营/出生点/结算/胜负条件等字段）。")
    lines.append(
        f"- [{'x' if graph_code_done else ' '}] 为 pyugc 节点图生成 Graph Code（无法语义映射则占位），并通过引擎校验。"
    )
    lines.append("")
    lines.append("### 可复现命令")
    lines.append("```powershell")

    def to_windows_path_text(path_text: str) -> str:
        return path_text.replace("/", "\\")

    cli_object = report_object.get("cli") if isinstance(report_object, dict) else None
    if not isinstance(cli_object, dict):
        cli_object = {}

    enable_dll_dump_value = cli_object.get("enable_dll_dump")
    if not isinstance(enable_dll_dump_value, bool):
        dll_dump_object = report_object.get("dll_dump") if isinstance(report_object, dict) else None
        enable_dll_dump_value = (
            bool(dll_dump_object.get("enabled")) if isinstance(dll_dump_object, dict) else False
        )

    data_min_bytes_value = cli_object.get("data_min_bytes")
    if not isinstance(data_min_bytes_value, int):
        dtype_type3_object = report_object.get("decoded_dtype_type3") if isinstance(report_object, dict) else None
        data_min_bytes_value = (
            int(dtype_type3_object.get("min_bytes"))
            if isinstance(dtype_type3_object, dict) and isinstance(dtype_type3_object.get("min_bytes"), int)
            else 512
        )

    generic_scan_min_bytes_value = cli_object.get("generic_scan_min_bytes")
    if not isinstance(generic_scan_min_bytes_value, int):
        decoded_generic_object = report_object.get("decoded_generic") if isinstance(report_object, dict) else None
        generic_scan_min_bytes_value = (
            int(decoded_generic_object.get("scan_min_bytes"))
            if isinstance(decoded_generic_object, dict) and isinstance(decoded_generic_object.get("scan_min_bytes"), int)
            else 256
        )

    focus_graph_id_value = cli_object.get("focus_graph_id")
    if not isinstance(focus_graph_id_value, int):
        focus_graph_id_value = None

    dtype_path_text = cli_object.get("dtype_path")
    if not isinstance(dtype_path_text, str) or dtype_path_text.strip() == "":
        dtype_path_text = ""

    from ugc_file_tools.repo_paths import try_find_graph_generater_root

    graph_generater_root = try_find_graph_generater_root(output_package_root)

    def to_repo_relative_text(path: Path) -> str:
        if graph_generater_root is None:
            return str(path)
        repo_parts = graph_generater_root.resolve().parts
        path_parts = path.resolve().parts
        if len(path_parts) >= len(repo_parts) and path_parts[: len(repo_parts)] == repo_parts:
            relative_parts = path_parts[len(repo_parts) :]
            if len(relative_parts) == 0:
                return "."
            return str(Path(*relative_parts))
        return str(path)

    output_package_root_text = to_windows_path_text(to_repo_relative_text(output_package_root))

    input_gil_cmd_text = input_gil_text
    if input_gil_cmd_text:
        input_gil_path = Path(input_gil_cmd_text)
        if input_gil_path.is_absolute():
            input_gil_cmd_text = to_repo_relative_text(input_gil_path)
    input_gil_cmd_text = to_windows_path_text(input_gil_cmd_text)

    dtype_cmd_text = dtype_path_text
    if dtype_cmd_text:
        dtype_path = Path(dtype_cmd_text)
        if dtype_path.is_absolute():
            dtype_cmd_text = to_repo_relative_text(dtype_path)
    dtype_cmd_text = to_windows_path_text(dtype_cmd_text)

    command_parts: List[str] = []
    runner_rel = Path("private_extensions") / "run_ugc_file_tools.py"
    if graph_generater_root is not None and (graph_generater_root / runner_rel).is_file():
        command_parts.append(f'python -X utf8 "{to_windows_path_text(str(runner_rel))}" tool extract_gil_to_package')
    else:
        # fallback：作为独立工具仓库运行时，通常可直接 `python -m ugc_file_tools ...`
        command_parts.append("python -X utf8 -m ugc_file_tools tool extract_gil_to_package")
    if input_gil_cmd_text:
        command_parts.append(f'--input-gil "{input_gil_cmd_text}"')
    command_parts.append(f'--output-package "{output_package_root_text}"')
    if dtype_cmd_text:
        command_parts.append(f'--dtype "{dtype_cmd_text}"')
    if enable_dll_dump_value:
        command_parts.append("--enable-dll-dump")
    command_parts.append(f"--data-min-bytes {int(data_min_bytes_value)}")
    command_parts.append(f"--generic-scan-min-bytes {int(generic_scan_min_bytes_value)}")
    if focus_graph_id_value is not None:
        command_parts.append(f"--focus-graph-id {int(focus_graph_id_value)}")

    lines.append(" ".join(command_parts))
    lines.append("```")
    lines.append("")
    lines.append("### 说明")
    lines.append("- 业务侧无法完全语义映射的字段，统一保存在各目录的 `原始解析/` 与资源 JSON 的 `metadata.ugc` 中，确保可追溯。")
    lines.append("")
    return "\n".join(lines)




def build_parse_status_markdown(
    output_package_root: Path,
    report_object: Dict[str, Any],
    validation_summary: Optional[Dict[str, Any]],
) -> str:
    return _build_parse_status_markdown(
        output_package_root=Path(output_package_root),
        report_object=report_object,
        validation_summary=validation_summary,
    )

