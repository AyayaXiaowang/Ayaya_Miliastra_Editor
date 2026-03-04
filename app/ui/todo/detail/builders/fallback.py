from __future__ import annotations

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    register_fallback_detail_builder,
)
from app.ui.todo.detail.builders.shared_builders import (
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
)


@register_fallback_detail_builder
def build_fallback_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    _info: dict,
    _detail_type: str,
) -> DetailDocument:
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


