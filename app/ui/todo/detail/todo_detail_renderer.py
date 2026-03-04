# -*- coding: utf-8 -*-
"""
Todo 详情文档构建器（registry 分发）

职责：
- 将 TodoItem.detail_info 转换为结构化的 DetailDocument
- 不关心具体呈现方式，由视图层（Widget）负责渲染

扩展方式：
- 新增 detail_type 的构建逻辑请在 `app/ui/todo/detail/builders/` 下新增模块并注册，
  不要在本文件里堆叠 if/elif 分发。
"""

from __future__ import annotations

from typing import Callable, Dict

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_model import DetailDocument
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    build_detail_document,
)


class TodoDetailBuilder:
    def __init__(
        self,
        collect_categories_info: Callable[[object], Dict[str, list]],
        collect_category_items: Callable[[object], list],
        collect_template_summary: Callable[[object], Dict[str, int]],
        collect_instance_summary: Callable[[object], Dict[str, int]],
    ) -> None:
        self._context = TodoDetailBuildContext(
            collect_categories_info=collect_categories_info,
            collect_category_items=collect_category_items,
            collect_template_summary=collect_template_summary,
            collect_instance_summary=collect_instance_summary,
        )

    def build_document(self, todo: TodoItem) -> DetailDocument:
        info = todo.detail_info or {}
        detail_type = str(info.get("type", "") or "")
        return build_detail_document(self._context, todo, info, detail_type)

