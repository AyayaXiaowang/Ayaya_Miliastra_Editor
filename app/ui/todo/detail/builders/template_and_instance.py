from __future__ import annotations

from typing import List

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    register_detail_type,
)
from app.ui.todo.detail.builders.shared_builders import (
    BulletListBlock,
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    TableBlock,
    build_collapsible_raw_section,
    format_value_preview,
)


@register_detail_type("template")
def build_template_document(
    context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
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
        section.blocks.append(ParagraphBlock(text=description_text, style=ParagraphStyle.NORMAL))

    document.sections.append(section)

    summary = context.collect_template_summary(todo)
    if summary:
        summary_section = DetailSection(title="配置清单", level=4)
        headers = ["配置项", "数量"]
        rows: List[List[str]] = []
        for configuration_type, count in summary.items():
            rows.append([str(configuration_type), str(count)])
        summary_section.blocks.append(TableBlock(headers=headers, rows=rows))
        document.sections.append(summary_section)

    return document


@register_detail_type("template_basic")
def build_template_basic_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
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


@register_detail_type("template_variables_table")
def build_template_variables_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title="配置自定义变量", level=3)

    variable_list = info.get("variables", [])
    if variable_list:
        headers = ["变量名", "类型", "默认值", "说明"]
        rows: List[List[str]] = []
        for variable_information in variable_list:
            description_text = variable_information.get("description", "") or "-"
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


@register_detail_type("graph_variables_table")
def build_graph_variables_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title="配置节点图变量", level=3)

    hint_paragraph = "节点图变量是生命周期跟随节点图的局部变量，仅在当前节点图内可访问。"
    section.blocks.append(ParagraphBlock(text=hint_paragraph, style=ParagraphStyle.HINT))

    section.blocks.append(
        ParagraphBlock(
            text="已切换右侧面板：图属性 → 节点图变量。",
            style=ParagraphStyle.EMPHASIS,
        )
    )
    section.blocks.append(
        ParagraphBlock(
            text="说明：该步骤用于浏览变量清单；画布会保持显示，便于对照变量在节点图中的使用位置。",
            style=ParagraphStyle.HINT,
        )
    )

    document.sections.append(section)
    return document


@register_detail_type("template_components_table")
def build_template_components_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    from engine.configs.components.component_registry import COMPONENT_DEFINITIONS

    document = DetailDocument()
    section = DetailSection(title="添加组件", level=3)

    components = info.get("components", [])
    if components:
        for component in components:
            component_type = str(component.get("component_type", ""))
            definition = COMPONENT_DEFINITIONS.get(component_type, {})
            description_source = component.get("description") or definition.get("description") or ""
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
                    bullet_items.append(f"{key}: {format_value_preview(value)}")
                section.blocks.append(BulletListBlock(items=bullet_items))
        section.blocks.append(build_collapsible_raw_section(title="原始数据（components）", payload=components))

    document.sections.append(section)
    return document


@register_detail_type("instance")
def build_instance_document(
    context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
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

    summary = context.collect_instance_summary(todo)
    if summary:
        summary_section = DetailSection(title="配置清单", level=4)
        headers = ["配置项", "数量"]
        rows: List[List[str]] = []
        for configuration_type, count in summary.items():
            rows.append([str(configuration_type), str(count)])
        summary_section.blocks.append(TableBlock(headers=headers, rows=rows))
        document.sections.append(summary_section)

    return document


@register_detail_type("instance_properties_table")
def build_instance_properties_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title="配置实体属性", level=3)

    position_values = info.get("position", [0, 0, 0])
    section.blocks.append(ParagraphBlock(text="位置：", style=ParagraphStyle.EMPHASIS))
    position_row = [
        f"{float(position_values[0]):.2f}",
        f"{float(position_values[1]):.2f}",
        f"{float(position_values[2]):.2f}",
    ]
    section.blocks.append(TableBlock(headers=["X", "Y", "Z"], rows=[position_row]))

    rotation_values = info.get("rotation", [0, 0, 0])
    section.blocks.append(ParagraphBlock(text="旋转：", style=ParagraphStyle.EMPHASIS))
    rotation_row = [
        f"{float(rotation_values[0]):.2f}°",
        f"{float(rotation_values[1]):.2f}°",
        f"{float(rotation_values[2]):.2f}°",
    ]
    section.blocks.append(TableBlock(headers=["Pitch", "Yaw", "Roll"], rows=[rotation_row]))

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


