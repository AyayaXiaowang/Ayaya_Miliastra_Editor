from __future__ import annotations

import json
from typing import List

from app.models.todo_item import TodoItem
from app.ui.todo.todo_detail_model import (
    BulletListBlock,
    CollapsibleBlock,
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    PreformattedBlock,
    TableBlock,
)


def build_simple_title_and_description_document(todo: TodoItem) -> DetailDocument:
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


def append_key_value_table_if_present(
    section: DetailSection,
    mapping: dict,
    *,
    headers: List[str],
) -> None:
    if not isinstance(mapping, dict) or not mapping:
        return
    rows: List[List[str]] = []
    for key, value in mapping.items():
        rows.append([str(key), str(value)])
    section.blocks.append(TableBlock(headers=list(headers), rows=rows))


def format_value_preview(value: object, *, max_len: int = 160) -> str:
    """将任意值格式化为“适合人类阅读”的短预览字符串。

    目标：避免把大 dict/list 直接 str() 变成“垃圾信息”，同时保留足够线索便于用户操作。
    """

    if value is None:
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "-"
        if max_len > 0 and len(text) > max_len:
            return text[:max_len] + "…"
        return text
    if isinstance(value, dict):
        key_count = len(value)
        # 优先尝试从常见字段提取“名字”
        for key in ("name", "title", "id", "key"):
            if key in value and isinstance(value.get(key), str) and str(value.get(key) or "").strip():
                label = str(value.get(key)).strip()
                label = label if len(label) <= max_len else label[:max_len] + "…"
                return f"{label}（对象，{key_count}项）"
        return f"（对象，{key_count}项）"
    if isinstance(value, list):
        return f"（列表，{len(value)}项）"
    # 兜底：保证一定可显示
    text = str(value)
    if max_len > 0 and len(text) > max_len:
        return text[:max_len] + "…"
    return text


def build_collapsible_raw_section(
    *,
    title: str,
    payload: object,
    max_chars: int = 6000,
) -> CollapsibleBlock:
    """构建“原始数据（折叠）”分节内容块。"""

    normalized_title = str(title or "原始数据")
    text = ""
    if payload is None:
        text = "（无）"
    elif isinstance(payload, (str, int, float, bool)):
        text = str(payload)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\n...（已截断）"
    return CollapsibleBlock(
        title=normalized_title,
        blocks=[PreformattedBlock(text=text, max_chars=max_chars)],
        default_collapsed=True,
    )


__all__ = [
    "build_simple_title_and_description_document",
    "append_key_value_table_if_present",
    "format_value_preview",
    "build_collapsible_raw_section",
    "BulletListBlock",
    "CollapsibleBlock",
    "DetailDocument",
    "DetailSection",
    "ParagraphBlock",
    "ParagraphStyle",
    "PreformattedBlock",
    "TableBlock",
]


