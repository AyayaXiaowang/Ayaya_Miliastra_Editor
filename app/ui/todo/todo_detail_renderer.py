# -*- coding: utf-8 -*-
"""
Todo 详情文档构建器

职责：
- 将 TodoItem.detail_info 转换为结构化的 DetailDocument
- 不关心具体呈现方式，由视图层（Widget）负责渲染

说明：
- 依赖回调获取统计/汇总信息，避免直接耦合 UI 组件内部结构
"""

from __future__ import annotations

from typing import Callable, Dict, List

from app.models.todo_item import TodoItem
from engine.configs.rules import COMPONENT_DEFINITIONS
from ui.todo.todo_config import CombatTypeNames, ManagementTypeNames
from ui.todo.todo_detail_model import (
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    TableBlock,
    BulletListBlock,
)


class TodoDetailBuilder:
    def __init__(
        self,
        collect_categories_info: Callable[[object], Dict[str, list]],
        collect_category_items: Callable[[object], list],
        collect_template_summary: Callable[[object], Dict[str, int]],
        collect_instance_summary: Callable[[object], Dict[str, int]],
    ) -> None:
        self._collect_categories_info = collect_categories_info
        self._collect_category_items = collect_category_items
        self._collect_template_summary = collect_template_summary
        self._collect_instance_summary = collect_instance_summary

    # === 外部入口 ===

    def build_document(self, todo: TodoItem) -> DetailDocument:
        info = todo.detail_info
        detail_type = info.get("type", "")

        if detail_type == "root":
            return self._build_root_document(todo, info)
        if detail_type == "category":
            return self._build_category_document(todo, info)
        if detail_type == "template":
            return self._build_template_document(todo, info)
        if detail_type == "template_basic":
            return self._build_template_basic_document(todo, info)
        if detail_type == "template_variables_table":
            return self._build_template_variables_document(todo, info)
        if detail_type == "graph_variables_table":
            return self._build_graph_variables_document(todo, info)
        if detail_type == "template_components_table":
            return self._build_template_components_document(todo, info)
        if detail_type == "instance":
            return self._build_instance_document(todo, info)
        if detail_type == "instance_properties_table":
            return self._build_instance_properties_document(todo, info)
        if detail_type == "combat_projectile":
            return self._build_combat_projectile_document(todo, info)
        if isinstance(detail_type, str) and detail_type.startswith("combat_"):
            return self._build_combat_generic_document(info, detail_type)
        if isinstance(detail_type, str) and detail_type.startswith("management_"):
            return self._build_management_generic_document(info, detail_type)
        if detail_type in (
            "template_graph_root",
            "event_flow_root",
            "graph_create_node",
            "graph_create_and_connect",
            "graph_create_and_connect_reverse",
        ):
            return self._build_simple_title_and_description_document(todo)
        if detail_type == "graph_config_node_merged":
            return self._build_graph_config_node_document(todo, info)
        if detail_type == "graph_config_branch_outputs":
            return self._build_graph_config_branch_outputs_document(todo, info)
        if detail_type == "graph_connect_merged":
            return self._build_graph_connect_merged_document(todo, info)
        if detail_type == "graph_signals_overview":
            return self._build_graph_signals_overview_document(info)
        if detail_type == "graph_bind_signal":
            return self._build_graph_bind_signal_document(todo, info)

        return self._build_fallback_document(todo)

    # === 各 detail_type 分支的具体构建逻辑 ===

    def _build_root_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()

        package_name = info.get("package_name", "存档")
        title_section = DetailSection(title=str(package_name), level=3)
        if todo.description:
            title_section.blocks.append(
                ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL)
            )
        document.sections.append(title_section)

        categories_info = self._collect_categories_info(todo)
        if categories_info:
            overview_section = DetailSection(title="配置概览", level=4)
            for category_title, category_items in categories_info.items():
                item_count = len(category_items)
                overview_section.blocks.append(
                    ParagraphBlock(
                        text=f"{category_title}：{item_count} 项",
                        style=ParagraphStyle.EMPHASIS,
                    )
                )
                if not category_items:
                    continue
                headers = ["名称", "类型/说明"]
                table_rows: List[List[str]] = []
                for item_name, item_type in category_items[:10]:
                    table_rows.append(
                        [str(item_name), str(item_type)],
                    )
                overview_section.blocks.append(
                    TableBlock(headers=headers, rows=table_rows)
                )
                if len(category_items) > 10:
                    remaining_count = len(category_items) - 10
                    overview_section.blocks.append(
                        ParagraphBlock(
                            text=f"...还有 {remaining_count} 项",
                            style=ParagraphStyle.HINT,
                        )
                    )
            document.sections.append(overview_section)

        return document

    def _build_category_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)

        total_count = info.get("count", 0)
        section.blocks.append(
            ParagraphBlock(
                text=f"共 {total_count} 项配置任务",
                style=ParagraphStyle.NORMAL,
            )
        )

        category_key = info.get("category", "")
        category_items = self._collect_category_items(todo)
        if category_items:
            if category_key == "standalone_graphs":
                headers = ["节点图名称", "类型", "变量数", "节点数", "文件夹"]
                graph_rows: List[List[str]] = []
                for item_information in category_items:
                    name = str(item_information.get("name", "-"))
                    graph_type = str(item_information.get("graph_type", ""))
                    if graph_type == "server":
                        type_text = "服务器"
                    elif graph_type == "client":
                        type_text = "客户端"
                    else:
                        type_text = graph_type
                    variable_count = int(item_information.get("variable_count", 0))
                    node_count = int(item_information.get("node_count", 0))
                    folder_path = str(item_information.get("folder_path", "") or "-")
                    graph_rows.append(
                        [
                            name,
                            type_text,
                            str(variable_count),
                            str(node_count),
                            folder_path,
                        ]
                    )
                section.blocks.append(TableBlock(headers=headers, rows=graph_rows))
            else:
                headers: List[str] = []
                rows: List[List[str]] = []
                if category_key == "templates":
                    headers = ["元件名称", "实体类型", "配置项"]
                    for item_information in category_items:
                        configuration_summary = item_information.get(
                            "config_summary", ""
                        )
                        rows.append(
                            [
                                str(item_information.get("name", "")),
                                str(item_information.get("entity_type", "")),
                                str(configuration_summary),
                            ]
                        )
                elif category_key == "instances":
                    headers = ["实体名称", "基于元件", "配置项"]
                    for item_information in category_items:
                        configuration_summary = item_information.get(
                            "config_summary", ""
                        )
                        rows.append(
                            [
                                str(item_information.get("name", "")),
                                str(item_information.get("template_name", "-")),
                                str(configuration_summary),
                            ]
                        )
                elif category_key in ["combat", "management"]:
                    headers = ["名称", "类型"]
                    for item_information in category_items:
                        rows.append(
                            [
                                str(item_information.get("name", "")),
                                str(item_information.get("type", "")),
                            ]
                        )
                if headers and rows:
                    section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_template_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(info.get("name", "元件")), level=3)

        entity_type = str(info.get("entity_type", ""))
        if entity_type:
            section.blocks.append(
                ParagraphBlock(
                    text=f"实体类型：{entity_type}",
                    style=ParagraphStyle.EMPHASIS,
                )
            )

        description_text = str(info.get("description", "") or "")
        if description_text:
            section.blocks.append(
                ParagraphBlock(text=description_text, style=ParagraphStyle.NORMAL)
            )

        document.sections.append(section)

        summary = self._collect_template_summary(todo)
        if summary:
            summary_section = DetailSection(title="配置清单", level=4)
            headers = ["配置项", "数量"]
            rows: List[List[str]] = []
            for configuration_type, count in summary.items():
                rows.append([str(configuration_type), str(count)])
            summary_section.blocks.append(TableBlock(headers=headers, rows=rows))
            document.sections.append(summary_section)

        return document

    def _build_template_basic_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="基础属性配置", level=3)

        configuration_mapping = info.get("config", {})
        if configuration_mapping:
            headers = ["属性", "值"]
            rows: List[List[str]] = []
            for key, value in configuration_mapping.items():
                rows.append([str(key), str(value)])
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_template_variables_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="配置自定义变量", level=3)

        variable_list = info.get("variables", [])
        if variable_list:
            headers = ["变量名", "类型", "默认值", "说明"]
            rows: List[List[str]] = []
            for variable_information in variable_list:
                description_text = (
                    variable_information.get("description", "") or "-"
                )
                rows.append(
                    [
                        str(variable_information.get("name", "")),
                        str(variable_information.get("variable_type", "")),
                        str(variable_information.get("default_value", "")),
                        str(description_text),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_graph_variables_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(level=3)

        hint_paragraph = (
            "节点图变量是生命周期跟随节点图的局部变量，仅在当前节点图内可访问。"
        )
        section.blocks.append(
            ParagraphBlock(text=hint_paragraph, style=ParagraphStyle.HINT)
        )

        variable_list = info.get("variables", [])
        if variable_list:
            headers = ["变量名", "类型", "默认值", "对外暴露", "说明"]
            rows: List[List[str]] = []
            for variable_information in variable_list:
                description_text = (
                    variable_information.get("description", "") or "-"
                )
                is_exposed = bool(variable_information.get("is_exposed", False))
                exposed_text = "是" if is_exposed else "否"
                display_value = variable_information.get(
                    "display_value", variable_information.get("default_value", "")
                )
                rows.append(
                    [
                        str(variable_information.get("name", "")),
                        str(variable_information.get("variable_type", "")),
                        str(display_value),
                        exposed_text,
                        str(description_text),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_template_components_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="添加组件", level=3)

        components = info.get("components", [])
        if components:
            for component in components:
                component_type = str(component.get("component_type", ""))
                definition = COMPONENT_DEFINITIONS.get(component_type, {})
                description_source = (
                    component.get("description")
                    or definition.get("description")
                    or ""
                )
                description_text = str(description_source).strip() or "-"
                section.blocks.append(
                    ParagraphBlock(
                        text=f"{component_type}：{description_text}",
                        style=ParagraphStyle.EMPHASIS,
                    )
                )
                settings_mapping = component.get("settings", {})
                if settings_mapping:
                    bullet_items: List[str] = []
                    for key, value in settings_mapping.items():
                        bullet_items.append(f"{key}: {value}")
                    section.blocks.append(BulletListBlock(items=bullet_items))

        document.sections.append(section)
        return document

    def _build_instance_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(info.get("name", "实体")), level=3)

        template_name = str(info.get("template_name", ""))
        section.blocks.append(
            ParagraphBlock(
                text=f"基于元件：{template_name}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

        document.sections.append(section)

        summary = self._collect_instance_summary(todo)
        if summary:
            summary_section = DetailSection(title="配置清单", level=4)
            headers = ["配置项", "数量"]
            rows: List[List[str]] = []
            for configuration_type, count in summary.items():
                rows.append([str(configuration_type), str(count)])
            summary_section.blocks.append(TableBlock(headers=headers, rows=rows))
            document.sections.append(summary_section)

        return document

    def _build_instance_properties_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="配置实体属性", level=3)

        position_values = info.get("position", [0, 0, 0])
        section.blocks.append(
            ParagraphBlock(text="位置：", style=ParagraphStyle.EMPHASIS)
        )
        position_row = [
            f"{float(position_values[0]):.2f}",
            f"{float(position_values[1]):.2f}",
            f"{float(position_values[2]):.2f}",
        ]
        section.blocks.append(
            TableBlock(headers=["X", "Y", "Z"], rows=[position_row])
        )

        rotation_values = info.get("rotation", [0, 0, 0])
        section.blocks.append(
            ParagraphBlock(text="旋转：", style=ParagraphStyle.EMPHASIS)
        )
        rotation_row = [
            f"{float(rotation_values[0]):.2f}°",
            f"{float(rotation_values[1]):.2f}°",
            f"{float(rotation_values[2]):.2f}°",
        ]
        section.blocks.append(
            TableBlock(headers=["Pitch", "Yaw", "Roll"], rows=[rotation_row])
        )

        override_variables = info.get("override_variables", [])
        if override_variables:
            section.blocks.append(
                ParagraphBlock(text="覆盖变量：", style=ParagraphStyle.EMPHASIS)
            )
            headers = ["变量名", "值"]
            rows: List[List[str]] = []
            for variable_information in override_variables:
                rows.append(
                    [
                        str(variable_information.get("name", "")),
                        str(variable_information.get("value", "")),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_combat_projectile_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="投射物配置", level=3)

        data_mapping = info.get("data", {}) or {}
        projectile_name = (
            data_mapping.get("projectile_name")
            or data_mapping.get("name")
            or info.get("projectile_id")
            or ""
        )
        if projectile_name:
            section.blocks.append(
                ParagraphBlock(
                    text=f"名称：{projectile_name}",
                    style=ParagraphStyle.EMPHASIS,
                )
            )

        properties_section = DetailSection(title="属性标签页（图1）", level=4)
        properties_paragraph = (
            "在右侧“属性”标签页中，按分组完成本地投射物的基础与生命周期配置："
        )
        properties_section.blocks.append(
            ParagraphBlock(text=properties_paragraph, style=ParagraphStyle.NORMAL)
        )
        properties_section.blocks.append(
            BulletListBlock(
                items=[
                    "基础设置：选择投射物模型资产（例如：木箱），并根据需要调整 X / Y / Z 缩放比例。",
                    "原生碰撞：根据玩法勾选“初始生效”“是否可攀爬”等碰撞相关开关。",
                    "战斗参数：在“属性设置”中选择是继承创建者还是独立配置属性，并确认“后续是否受创建者影响”。",
                    "生命周期设置：决定是否永久持续；如非永久，则设置持续时长(s) 以及 XZ / Y 方向的销毁距离阈值。",
                    "生命周期结束行为：为生命周期结束时需要触发的效果预留能力单元入口（例如：爆炸、回收等）。",
                ]
            )
        )

        components_section = DetailSection(title="组件标签页（图2）", level=4)
        components_paragraph = "在“组件”标签页中，为投射物挂载和配置专用组件："
        components_section.blocks.append(
            ParagraphBlock(text=components_paragraph, style=ParagraphStyle.NORMAL)
        )
        components_section.blocks.append(
            BulletListBlock(
                items=[
                    "特效播放：维护投射物飞行或出现时需要播放的特效列表，通过“详细编辑”调整具体特效与触发时机。",
                    "投射运动器：选择运动类型（如直线投射），并在“详细编辑”中设置速度、重力系数等运动参数。",
                    "命中检测：配置命中检测触发区（例如“区域1”），在“详细编辑”里调整碰撞体积、层级过滤等检测规则。",
                ]
            )
        )

        abilities_section = DetailSection(title="能力标签页（图3）", level=4)
        abilities_paragraph = "在“能力”标签页中，集中维护投射物命中或销毁时要触发的能力逻辑："
        abilities_section.blocks.append(
            ParagraphBlock(text=abilities_paragraph, style=ParagraphStyle.NORMAL)
        )
        abilities_section.blocks.append(
            BulletListBlock(
                items=[
                    "能力单元：为命中、生命周期结束等事件添加能力单元条目；本页只负责建立引用与顺序，具体能力内容在能力库中维护。"
                ]
            )
        )

        document.sections.append(section)
        document.sections.append(properties_section)
        document.sections.append(components_section)
        document.sections.append(abilities_section)
        return document

    def _build_combat_generic_document(self, info: dict, detail_type: str) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(
            title=CombatTypeNames.get_name(detail_type),
            level=3,
        )

        data_mapping = info.get("data", {})
        if data_mapping:
            name_text = str(data_mapping.get("name", ""))
            if name_text:
                section.blocks.append(
                    ParagraphBlock(
                        text=name_text,
                        style=ParagraphStyle.EMPHASIS,
                    )
                )
            rows: List[List[str]] = []
            for key, value in data_mapping.items():
                if key == "name":
                    continue
                rows.append([str(key), str(value)])
            if rows:
                section.blocks.append(TableBlock(headers=["键", "值"], rows=rows))

        document.sections.append(section)
        return document

    def _build_management_generic_document(self, info: dict, detail_type: str) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(
            title=ManagementTypeNames.get_name(detail_type),
            level=3,
        )

        data_mapping = info.get("data", {})
        if data_mapping:
            name_text = str(data_mapping.get("name", ""))
            if name_text:
                section.blocks.append(
                    ParagraphBlock(
                        text=name_text,
                        style=ParagraphStyle.EMPHASIS,
                    )
                )
            rows: List[List[str]] = []
            for key, value in data_mapping.items():
                if key == "name":
                    continue
                rows.append([str(key), str(value)])
            if rows:
                section.blocks.append(TableBlock(headers=["键", "值"], rows=rows))

        document.sections.append(section)
        return document

    def _build_simple_title_and_description_document(self, todo: TodoItem) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)
        if todo.description:
            section.blocks.append(
                ParagraphBlock(
                    text=str(todo.description),
                    style=ParagraphStyle.NORMAL,
                )
            )
        document.sections.append(section)
        return document

    def _build_graph_config_node_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)

        node_title = str(info.get("node_title", ""))
        section.blocks.append(
            ParagraphBlock(
                text=f"节点：{node_title}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

        parameters = info.get("params", [])
        if parameters:
            headers = ["参数", "值"]
            rows: List[List[str]] = []
            for parameter_information in parameters:
                rows.append(
                    [
                        str(parameter_information.get("param_name", "")),
                        str(parameter_information.get("param_value", "")),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_graph_config_branch_outputs_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)

        node_title = str(info.get("node_title", ""))
        section.blocks.append(
            ParagraphBlock(
                text=f"节点：{node_title}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

        branch_list = info.get("branches", [])
        if branch_list:
            headers = ["分支端口", "匹配值"]
            rows: List[List[str]] = []
            for branch in branch_list:
                rows.append(
                    [
                        str(branch.get("port_name", "")),
                        str(branch.get("value", "")),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_graph_connect_merged_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)

        node_title_one = str(info.get("node1_title", ""))
        node_title_two = str(info.get("node2_title", ""))
        if node_title_one or node_title_two:
            section.blocks.append(
                ParagraphBlock(
                    text=f"{node_title_one} → {node_title_two}",
                    style=ParagraphStyle.EMPHASIS,
                )
            )

        edge_list = info.get("edges", [])
        if edge_list:
            headers = ["源端口", "目标端口"]
            rows: List[List[str]] = []
            for edge in edge_list:
                rows.append(
                    [
                        str(edge.get("src_port", "")),
                        str(edge.get("dst_port", "")),
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))

        document.sections.append(section)
        return document

    def _build_graph_signals_overview_document(self, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title="本图信号概览", level=3)

        graph_name = str(info.get("graph_name", "") or "")
        if graph_name:
            section.blocks.append(
                ParagraphBlock(
                    text=f"节点图：{graph_name}",
                    style=ParagraphStyle.EMPHASIS,
                )
            )

        signal_entries = info.get("signals", []) or []
        if signal_entries:
            headers = ["信号名", "信号ID", "使用节点数", "是否在当前存档定义"]
            rows: List[List[str]] = []
            for entry in signal_entries:
                signal_name = entry.get("signal_name") or "(未命名信号)"
                signal_identifier = entry.get("signal_id") or ""
                node_count = int(entry.get("node_count", 0))
                defined = bool(entry.get("defined_in_package", False))
                defined_text = "是" if defined else "否"
                rows.append(
                    [
                        str(signal_name),
                        str(signal_identifier),
                        str(node_count),
                        defined_text,
                    ]
                )
            section.blocks.append(TableBlock(headers=headers, rows=rows))
            section.blocks.append(
                ParagraphBlock(
                    text="双击任务或使用右上角按钮可在编辑器中查看并调整这些信号节点。",
                    style=ParagraphStyle.HINT,
                )
            )

        document.sections.append(section)
        return document

    def _build_graph_bind_signal_document(self, todo: TodoItem, info: dict) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)

        node_title = str(info.get("node_title", ""))
        node_identifier = str(info.get("node_id", ""))
        if node_title or node_identifier:
            target_text_parts: List[str] = []
            if node_title:
                target_text_parts.append(node_title)
            if node_identifier:
                target_text_parts.append(f"({node_identifier})")
            section.blocks.append(
                ParagraphBlock(
                    text="目标节点：" + " ".join(target_text_parts),
                    style=ParagraphStyle.EMPHASIS,
                )
            )

        signal_name = str(info.get("signal_name") or "")
        signal_identifier = str(info.get("signal_id") or "")
        if signal_name or signal_identifier:
            signal_text_parts: List[str] = []
            if signal_name:
                signal_text_parts.append(signal_name)
            if signal_identifier:
                signal_text_parts.append(f"({signal_identifier})")
            section.blocks.append(
                ParagraphBlock(
                    text="当前绑定信号：" + " ".join(signal_text_parts),
                    style=ParagraphStyle.NORMAL,
                )
            )
        else:
            section.blocks.append(
                ParagraphBlock(
                    text="当前绑定信号：未选择",
                    style=ParagraphStyle.HINT,
                )
            )

        section.blocks.append(
            ParagraphBlock(
                text=(
                    "在节点图中右键该节点，可通过“选择信号…”绑定信号，"
                    "或通过“打开信号管理器…”调整信号定义。"
                ),
                style=ParagraphStyle.HINT,
            )
        )

        document.sections.append(section)
        return document

    def _build_fallback_document(self, todo: TodoItem) -> DetailDocument:
        document = DetailDocument()
        section = DetailSection(title=str(todo.title), level=3)
        if todo.description:
            section.blocks.append(
                ParagraphBlock(
                    text=str(todo.description),
                    style=ParagraphStyle.NORMAL,
                )
            )
        document.sections.append(section)
        return document


# 兼容旧引用名（部分文档/注释仍使用 “Renderer” 表述）
TodoDetailRenderer = TodoDetailBuilder



