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
    workspace_path: object

    def _ensure_node_library(self) -> None:
        if self._node_library is not None:
            return
        library = get_node_library(self.workspace_path)
        self._node_library = library
        self._node_defs_by_name = {}
        for node_def in library.values():
            node_name = getattr(node_def, "name", "")
            if isinstance(node_name, str) and node_name:
                self._node_defs_by_name.setdefault(node_name, []).append(node_def)

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
        from engine.nodes.node_definition_loader import find_composite_node_def

        # 复合节点优先按 composite_id 精确匹配
        if getattr(node, "composite_id", ""):
            found = find_composite_node_def(
                self._node_library,
                composite_id=node.composite_id,
                node_name=node.title,
            )
            if found:
                return found[1]

        # 常规节点：标准键/别名映射（类别统一为“...节点”）
        category_standard = _normalize_category_text(getattr(node, "category", ""))
        candidate_key = f"{category_standard}/{node.title}"
        # 直接命中标准键或别名键（impl_definition_loader 已将别名键注入库）
        direct = self._node_library.get(candidate_key)
        if direct is not None:
            return direct
        # 尝试作用域变体（当仅注册了 #{scope} 变体时）
        for scope_suffix in ("#client", "#server"):
            scoped_key = f"{candidate_key}{scope_suffix}"
            scoped = self._node_library.get(scoped_key)
            if scoped is not None:
                return scoped
        fallback = self._resolve_node_def_by_name(node.title, category_standard)
        if fallback is not None:
            return fallback
        return None

    def get_node_def_for_model(self, node: NodeModel):
        """
        公开节点定义查询接口：语义与 `_get_node_def_for_model` 一致。
        """
        return self._get_node_def_for_model(node)


