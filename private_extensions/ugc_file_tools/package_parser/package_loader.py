from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.console_encoding import configure_console_encoding

from .json_io import read_json_file
from .node_graphs import (
    ParsedNodeDefinition,
    ParsedNodeGraph,
    load_pyugc_node_definitions_for_package,
    load_pyugc_node_graphs_for_package,
)


def _find_repo_root_from_package_root(package_root: Path) -> Optional[Path]:
    """
    尝试从任意存档包目录反推仓库根目录（包含 Graph_Generater/ 与 ugc_file_tools/）。
    """
    for parent in [package_root, *package_root.parents]:
        if (parent / "ugc_file_tools").is_dir() and (parent / "Graph_Generater").is_dir():
            return parent
    return None


def _load_index_list(package_root: Path, relative_index_path: str) -> List[Dict[str, Any]]:
    index_file_path = package_root / Path(relative_index_path)
    if not index_file_path.is_file():
        return []
    index_object = read_json_file(index_file_path)
    if not isinstance(index_object, list):
        raise TypeError(f"索引文件格式错误：期望为 list[dict]，file={str(index_file_path)!r}")
    result: List[Dict[str, Any]] = []
    for item in index_object:
        if isinstance(item, dict):
            result.append(item)
    return result


def _load_resources_by_output_path(
    package_root: Path,
    index_entries: List[Dict[str, Any]],
    *,
    id_key: str,
    output_key: str = "output",
) -> Dict[str, Dict[str, Any]]:
    resources_by_id: Dict[str, Dict[str, Any]] = {}
    for index_entry in index_entries:
        resource_id_value = index_entry.get(id_key)
        output_value = index_entry.get(output_key)
        if not isinstance(resource_id_value, str) or resource_id_value.strip() == "":
            continue
        if not isinstance(output_value, str) or output_value.strip() == "":
            continue
        resource_id = resource_id_value.strip()
        output_path = package_root / Path(output_value)
        resource_object = read_json_file(output_path)
        if not isinstance(resource_object, dict):
            raise TypeError(f"资源文件格式错误：期望为 dict，file={str(output_path)!r}")
        resources_by_id[resource_id] = resource_object
    return resources_by_id


@dataclass(frozen=True, slots=True)
class ParsedPackage:
    package_root: Path
    package_name: str

    overview: Dict[str, Any]
    report: Dict[str, Any]
    parse_status_markdown_path: Path

    templates: Dict[str, Dict[str, Any]]
    instances: Dict[str, Dict[str, Any]]

    player_templates: Dict[str, Dict[str, Any]]
    player_classes: Dict[str, Dict[str, Any]]
    skills: Dict[str, Dict[str, Any]]
    items: Dict[str, Dict[str, Any]]
    unit_statuses: Dict[str, Dict[str, Any]]

    currency_backpacks: Dict[str, Dict[str, Any]]
    level_settings: Dict[str, Dict[str, Any]]
    shields: Dict[str, Dict[str, Any]]
    unit_tags: Dict[str, Dict[str, Any]]
    equipment_data: Dict[str, Dict[str, Any]]
    growth_curves: Dict[str, Dict[str, Any]]
    equipment_slot_templates: Dict[str, Dict[str, Any]]

    node_definitions: Dict[int, ParsedNodeDefinition]
    pyugc_node_graphs: Dict[int, ParsedNodeGraph]

    def to_dict(self) -> Dict[str, Any]:
        def serialize_node_defs(definitions: Dict[int, ParsedNodeDefinition]) -> List[Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            for node_def_id_int, node_def in sorted(definitions.items(), key=lambda item: item[0]):
                rows.append(
                    {
                        "node_def_id_int": node_def_id_int,
                        "node_name": node_def.node_name,
                        "source_pyugc_path": node_def.source_pyugc_path,
                        "ports": [
                            {
                                "port_index_int": port.port_index_int,
                                "port_name": port.port_name,
                                "source_path": port.source_path,
                            }
                            for port in sorted(
                                node_def.ports_by_index.values(),
                                key=lambda port_item: port_item.port_index_int,
                            )
                        ],
                    }
                )
            return rows

        def serialize_graphs(graphs: Dict[int, ParsedNodeGraph]) -> List[Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            for graph_id_int, graph in sorted(graphs.items(), key=lambda item: item[0]):
                rows.append(
                    {
                        "graph_id_int": graph_id_int,
                        "graph_name": graph.graph_name,
                        "source_pyugc_path": graph.source_pyugc_path,
                        "nodes": [
                            {
                                "node_id_int": node.node_id_int,
                                "pos": {"x": node.pos_x, "y": node.pos_y},
                                "node_def_id_int": node.node_def_id_int,
                                "node_def_name": node.node_def_name,
                                "node_palette_id_int": node.node_palette_id_int,
                                "port_bindings": [
                                    {
                                        "port_index_int": binding.port_index_int,
                                        "port_name": binding.port_name,
                                        "utf8_values": list(binding.utf8_values),
                                    }
                                    for binding in node.port_bindings
                                ],
                            }
                            for node in graph.nodes
                        ],
                        "edges": [
                            {
                                "edge_kind": edge.edge_kind,
                                "src_node_id_int": edge.src_node_id_int,
                                "dst_node_id_int": edge.dst_node_id_int,
                                "src_port": (
                                    {"kind": "data", "port_index_int": edge.src_port.port_index_int}
                                    if hasattr(edge.src_port, "port_index_int")
                                    else {
                                        "kind": "flow",
                                        "group_int": edge.src_port.group_int,
                                        "branch_int": edge.src_port.branch_int,
                                    }
                                ),
                                "dst_port": (
                                    {"kind": "data", "port_index_int": edge.dst_port.port_index_int}
                                    if hasattr(edge.dst_port, "port_index_int")
                                    else {
                                        "kind": "flow",
                                        "group_int": edge.dst_port.group_int,
                                        "branch_int": edge.dst_port.branch_int,
                                    }
                                ),
                                "record_index": edge.record_index,
                            }
                            for edge in graph.edges
                        ],
                    }
                )
            return rows

        return {
            "package_name": self.package_name,
            "package_root": str(self.package_root),
            "overview": self.overview,
            "report": self.report,
            "parse_status_markdown": str(self.parse_status_markdown_path),
            "resources": {
                "templates_count": len(self.templates),
                "instances_count": len(self.instances),
                "player_templates_count": len(self.player_templates),
                "player_classes_count": len(self.player_classes),
                "skills_count": len(self.skills),
                "items_count": len(self.items),
                "unit_statuses_count": len(self.unit_statuses),
                "currency_backpacks_count": len(self.currency_backpacks),
                "level_settings_count": len(self.level_settings),
                "shields_count": len(self.shields),
                "unit_tags_count": len(self.unit_tags),
                "equipment_data_count": len(self.equipment_data),
                "growth_curves_count": len(self.growth_curves),
                "equipment_slot_templates_count": len(self.equipment_slot_templates),
            },
            "node_graphs": {
                "node_defs": serialize_node_defs(self.node_definitions),
                "pyugc_graphs": serialize_graphs(self.pyugc_node_graphs),
            },
        }


def load_parsed_package(package_root: Path) -> ParsedPackage:
    configure_console_encoding()

    package_root_path = Path(package_root).resolve()
    if not package_root_path.is_dir():
        raise FileNotFoundError(f"package root not found: {str(package_root_path)!r}")

    package_name = package_root_path.name

    overview_file_path = package_root_path / f"{package_name}总览.json"
    overview_object: Dict[str, Any] = {}
    if overview_file_path.is_file():
        overview_payload = read_json_file(overview_file_path)
        if isinstance(overview_payload, dict):
            overview_object = overview_payload

    report_file_path = package_root_path / "原始解析" / "report.json"
    report_payload = read_json_file(report_file_path)
    report_object = report_payload if isinstance(report_payload, dict) else {}

    # 解析状态文档已迁移到 ugc_file_tools/parse_status/；保留旧路径作为 fallback（兼容历史产物）。
    parse_status_markdown_path = package_root_path / "解析状态.md"

    from ugc_file_tools.repo_paths import ugc_file_tools_root

    migrated_parse_status_path = ugc_file_tools_root() / "parse_status" / package_name / "解析状态.md"
    if migrated_parse_status_path.is_file():
        parse_status_markdown_path = migrated_parse_status_path

    templates_index = _load_index_list(package_root_path, "元件库/templates_index.json")
    instances_index = _load_index_list(package_root_path, "实体摆放/instances_index.json")
    player_templates_index = _load_index_list(package_root_path, "战斗预设/玩家模板/player_templates_index.json")
    player_classes_index = _load_index_list(package_root_path, "战斗预设/职业/player_classes_index.json")
    skills_index = _load_index_list(package_root_path, "战斗预设/技能/skills_index.json")
    items_index = _load_index_list(package_root_path, "战斗预设/道具/items_index.json")
    unit_statuses_index = _load_index_list(package_root_path, "战斗预设/单位状态/unit_statuses_index.json")

    currency_backpacks_index = _load_index_list(package_root_path, "管理配置/货币背包/currency_backpacks_index.json")
    level_settings_index = _load_index_list(package_root_path, "管理配置/关卡设置/level_settings_index.json")
    shields_index = _load_index_list(package_root_path, "管理配置/护盾/shields_index.json")
    unit_tags_index = _load_index_list(package_root_path, "管理配置/单位标签/unit_tags_index.json")
    equipment_data_index = _load_index_list(package_root_path, "管理配置/装备数据/equipment_data_index.json")
    growth_curves_index = _load_index_list(package_root_path, "管理配置/成长曲线/growth_curves_index.json")
    equipment_slot_templates_index = _load_index_list(
        package_root_path,
        "管理配置/装备栏模板/equipment_slot_templates_index.json",
    )

    templates = _load_resources_by_output_path(package_root_path, templates_index, id_key="template_id")
    instances = _load_resources_by_output_path(package_root_path, instances_index, id_key="instance_id")

    player_templates = _load_resources_by_output_path(
        package_root_path,
        player_templates_index,
        id_key="template_id",
    )
    player_classes = _load_resources_by_output_path(
        package_root_path,
        player_classes_index,
        id_key="class_id",
    )
    skills = _load_resources_by_output_path(package_root_path, skills_index, id_key="skill_id")
    items = _load_resources_by_output_path(package_root_path, items_index, id_key="item_id")
    unit_statuses = _load_resources_by_output_path(
        package_root_path,
        unit_statuses_index,
        id_key="status_id",
    )

    currency_backpacks = _load_resources_by_output_path(
        package_root_path,
        currency_backpacks_index,
        id_key="config_id",
    )
    level_settings = _load_resources_by_output_path(
        package_root_path,
        level_settings_index,
        id_key="config_id",
    )
    shields = _load_resources_by_output_path(package_root_path, shields_index, id_key="shield_id")
    unit_tags = _load_resources_by_output_path(package_root_path, unit_tags_index, id_key="tag_id")
    equipment_data = _load_resources_by_output_path(
        package_root_path,
        equipment_data_index,
        id_key="equipment_id",
    )
    growth_curves = _load_resources_by_output_path(
        package_root_path,
        growth_curves_index,
        id_key="curve_id",
    )
    equipment_slot_templates = _load_resources_by_output_path(
        package_root_path,
        equipment_slot_templates_index,
        id_key="template_id",
    )

    node_definitions = load_pyugc_node_definitions_for_package(package_root_path)
    pyugc_node_graphs = load_pyugc_node_graphs_for_package(
        package_root_path,
        node_definitions=node_definitions,
    )

    return ParsedPackage(
        package_root=package_root_path,
        package_name=package_name,
        overview=overview_object,
        report=report_object,
        parse_status_markdown_path=parse_status_markdown_path,
        templates=templates,
        instances=instances,
        player_templates=player_templates,
        player_classes=player_classes,
        skills=skills,
        items=items,
        unit_statuses=unit_statuses,
        currency_backpacks=currency_backpacks,
        level_settings=level_settings,
        shields=shields,
        unit_tags=unit_tags,
        equipment_data=equipment_data,
        growth_curves=growth_curves,
        equipment_slot_templates=equipment_slot_templates,
        node_definitions=node_definitions,
        pyugc_node_graphs=pyugc_node_graphs,
    )




