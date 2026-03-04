# -*- coding: utf-8 -*-
"""
EditorExecutor Node Library Mixin

负责节点定义库的懒加载、按 NodeModel 查找 NodeDef（含复合节点）等逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.graph.models.graph_model import NodeModel

from app.automation.editor.node_library_provider import get_node_library


_CATEGORY_EQUIVALENCE_MAP = {
    "流程控制节点": {"流程控制节点", "执行节点"},
    "执行节点": {"执行节点", "流程控制节点"},
}


def _normalize_category_text(category_text: object) -> str:
    text = str(category_text or "").strip()
    if text == "":
        return ""
    return text if text.endswith("节点") else f"{text}节点"


def _get_equivalent_categories(category_text: str) -> set[str]:
    normalized = _normalize_category_text(category_text)
    equivalents = set(_CATEGORY_EQUIVALENCE_MAP.get(normalized, set()))
    if normalized:
        equivalents.add(normalized)
    return equivalents


class EditorExecutorNodeLibraryMixin:
    _node_library: Dict[str, Any] | None
    _node_defs_by_name: Dict[str, List[Any]]
    _composite_defs_by_id: Dict[str, Any]
    workspace_path: object

    def _ensure_node_library(self) -> None:
        if self._node_library is not None:
            return
        library = get_node_library(self.workspace_path)
        self._node_library = library
        self._node_defs_by_name = {}
        self._composite_defs_by_id = {}
        for node_def in library.values():
            node_name = getattr(node_def, "name", "")
            if isinstance(node_name, str) and node_name:
                self._node_defs_by_name.setdefault(node_name, []).append(node_def)
            if bool(getattr(node_def, "is_composite", False)):
                composite_id = str(getattr(node_def, "composite_id", "") or "").strip()
                if composite_id and composite_id not in self._composite_defs_by_id:
                    self._composite_defs_by_id[composite_id] = node_def

    def _resolve_node_def_by_name(self, node_name: str, preferred_category: str):
        if not isinstance(node_name, str) or node_name == "":
            return None
        if not self._node_defs_by_name:
            return None
        candidates = self._node_defs_by_name.get(node_name, [])
        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            return candidates[0]
        allowed_categories = _get_equivalent_categories(preferred_category)
        filtered = [
            candidate
            for candidate in candidates
            if _normalize_category_text(getattr(candidate, "category", "")) in allowed_categories
        ]
        if len(filtered) == 1:
            return filtered[0]
        return None

    def _get_node_def_for_model(self, node: NodeModel):
        """根据 NodeModel 获取 NodeDef（支持复合节点）。找不到则返回 None。"""
        self._ensure_node_library()
        if self._node_library is None:
            return None
        node_def_ref = getattr(node, "node_def_ref", None)
        if node_def_ref is None:
            raise ValueError(
                f"NodeModel 缺少 node_def_ref：{getattr(node, 'category', '')}/{getattr(node, 'title', '')}"
            )
        kind = str(getattr(node_def_ref, "kind", "") or "").strip()
        key = str(getattr(node_def_ref, "key", "") or "").strip()
        if kind == "builtin":
            return self._node_library.get(key)
        if kind == "composite":
            return self._composite_defs_by_id.get(key)
        if kind == "event":
            # event 的 key 通常为事件实例标识；需要按 (category/title) 映射回 builtin key。
            category = str(getattr(node, "category", "") or "").strip()
            title = str(getattr(node, "title", "") or "").strip()
            builtin_key = f"{category}/{title}" if (category and title) else ""
            return self._node_library.get(builtin_key) if builtin_key else None
        raise ValueError(f"非法 node_def_ref.kind：{kind!r}")

    def get_node_def_for_model(self, node: NodeModel):
        """
        公开节点定义查询接口：语义与 `_get_node_def_for_model` 一致。
        """
        return self._get_node_def_for_model(node)


