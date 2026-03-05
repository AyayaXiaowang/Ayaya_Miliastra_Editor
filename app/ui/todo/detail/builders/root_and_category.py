from __future__ import annotations

from typing import List

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    register_detail_type,
)
from app.ui.todo.detail.builders.shared_builders import (
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    TableBlock,
)


@register_detail_type("root")
def build_root_document(
    context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()

    package_name = info.get("package_name", "存档")
    title_section = DetailSection(title=str(package_name), level=3)
    if todo.description:
        title_section.blocks.append(
            ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL)
        )
    document.sections.append(title_section)

    categories_info = context.collect_categories_info(todo)
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
                table_rows.append([str(item_name), str(item_type)])
            overview_section.blocks.append(TableBlock(headers=headers, rows=table_rows))
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


@register_detail_type("category")
def build_category_document(
    context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
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
    category_items = context.collect_category_items(todo)
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
                    configuration_summary = item_information.get("config_summary", "")
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
                    configuration_summary = item_information.get("config_summary", "")
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


