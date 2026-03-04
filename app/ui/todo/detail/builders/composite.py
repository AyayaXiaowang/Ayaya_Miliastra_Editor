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
    build_collapsible_raw_section,
    format_value_preview,
)


def _append_context_table(section: DetailSection, info: dict) -> None:
    rows: List[List[str]] = []
    composite_id = str(info.get("composite_id") or "")
    if composite_id:
        rows.append(["复合节点ID", composite_id])
    composite_name = str(info.get("composite_name") or "")
    if composite_name:
        rows.append(["复合节点名", composite_name])
    graph_id = str(info.get("graph_id") or "")
    if graph_id:
        rows.append(["关联节点图ID", graph_id])
    graph_name = str(info.get("graph_name") or "")
    if graph_name:
        rows.append(["关联节点图名", graph_name])
    template_id = str(info.get("template_id") or "")
    if template_id:
        rows.append(["模板上下文", template_id])
    instance_id = str(info.get("instance_id") or "")
    if instance_id:
        rows.append(["实例上下文", instance_id])
    if rows:
        section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))


@register_detail_type("composite_root")
def build_composite_root_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))
    _append_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("composite_create_new")
def build_composite_create_new_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    section.blocks.append(
        ParagraphBlock(
            text="在复合节点库中新建该复合节点，确保其 ID 与名称与清单一致。",
            style=ParagraphStyle.NORMAL,
        )
    )
    _append_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("composite_set_meta")
def build_composite_set_meta_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    name_text = str(info.get("name") or "")
    desc_text = str(info.get("description") or "")
    folder_path = str(info.get("folder_path") or "")

    rows: List[List[str]] = []
    if name_text:
        rows.append(["名称", name_text])
    rows.append(["描述", desc_text if desc_text.strip() else "-"])
    rows.append(["文件夹", folder_path if folder_path.strip() else "-"])
    section.blocks.append(TableBlock(headers=["属性", "值"], rows=rows))

    _append_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("composite_set_pins")
def build_composite_set_pins_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    input_count = int(info.get("input_count", 0) or 0)
    output_count = int(info.get("output_count", 0) or 0)
    section.blocks.append(
        ParagraphBlock(
            text=f"输入：{input_count} 个，引出：{output_count} 个",
            style=ParagraphStyle.EMPHASIS,
        )
    )

    inputs = info.get("inputs") or []
    if isinstance(inputs, list) and inputs:
        rows: List[List[str]] = []
        for pin in inputs:
            if isinstance(pin, dict):
                pin_name = str(pin.get("name") or "")
                is_flow = bool(pin.get("is_flow", False))
                pin_type = "流程" if is_flow else "数据"
                rows.append([pin_name, pin_type])
            else:
                rows.append([format_value_preview(pin), "-"])
        section.blocks.append(TableBlock(headers=["输入引脚", "类型"], rows=rows))

    outputs = info.get("outputs") or []
    if isinstance(outputs, list) and outputs:
        rows = []
        for pin in outputs:
            if isinstance(pin, dict):
                pin_name = str(pin.get("name") or "")
                is_flow = bool(pin.get("is_flow", False))
                pin_type = "流程" if is_flow else "数据"
                rows.append([pin_name, pin_type])
            else:
                rows.append([format_value_preview(pin), "-"])
        section.blocks.append(TableBlock(headers=["输出引脚", "类型"], rows=rows))

    section.blocks.append(
        ParagraphBlock(
            text="提示：流程引脚（流）与数据引脚需要分别创建；名称必须与任务清单一致。",
            style=ParagraphStyle.HINT,
        )
    )
    section.blocks.append(build_collapsible_raw_section(title="原始数据（pins）", payload={"inputs": inputs, "outputs": outputs}))

    _append_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("composite_save")
def build_composite_save_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    section.blocks.append(
        ParagraphBlock(
            text="保存后建议刷新节点库/重新打开节点图，确保复合节点已可被正常搜索与使用。",
            style=ParagraphStyle.NORMAL,
        )
    )
    _append_context_table(section, info)
    document.sections.append(section)
    return document

