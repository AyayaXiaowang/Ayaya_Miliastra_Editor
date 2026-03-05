from __future__ import annotations

from typing import Dict, List

from engine.resources.level_variable_schema_service import LevelVariableSchemaService
from engine.resources.level_variable_schema_types import (
    CATEGORY_CUSTOM,
    CATEGORY_INGAME_SAVE,
    VariableFileInfo,
)


class LevelVariableSchemaView:
    """关卡变量聚合视图（只读缓存）。"""

    def __init__(self, schema_service: LevelVariableSchemaService | None = None) -> None:
        self._schema_service = schema_service or LevelVariableSchemaService()
        self._active_package_id: str | None = None
        self._variables: Dict[str, Dict] | None = None
        self._variable_files: Dict[str, VariableFileInfo] | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        normalized = str(package_id or "").strip()
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""
        normalized_or_none: str | None = normalized or None
        if normalized_or_none == self._active_package_id:
            return
        self._active_package_id = normalized_or_none
        self.invalidate_cache()

    def _ensure_loaded(self) -> None:
        if self._variable_files is not None:
            return
        self._variable_files = self._schema_service.load_all_variable_files(active_package_id=self._active_package_id)
        self._variables = {}
        for file_info in self._variable_files.values():
            for var_payload in file_info.variables:
                variable_id = var_payload["variable_id"]
                self._variables[variable_id] = var_payload

    def get_all_variables(self) -> Dict[str, Dict]:
        self._ensure_loaded()
        return self._variables or {}

    def get_all_variable_files(self) -> Dict[str, VariableFileInfo]:
        self._ensure_loaded()
        return self._variable_files or {}

    def get_variable_file(self, file_id: str) -> VariableFileInfo | None:
        self._ensure_loaded()
        if self._variable_files is None:
            return None
        return self._variable_files.get(file_id)

    def get_variables_by_file_id(self, file_id: str) -> List[Dict]:
        file_info = self.get_variable_file(file_id)
        if file_info is None:
            return []
        return list(file_info.variables)

    def get_custom_variable_files(self) -> Dict[str, VariableFileInfo]:
        self._ensure_loaded()
        if self._variable_files is None:
            return {}
        return {
            file_id: info
            for file_id, info in self._variable_files.items()
            if info.category == CATEGORY_CUSTOM
        }

    def get_ingame_save_variable_files(self) -> Dict[str, VariableFileInfo]:
        self._ensure_loaded()
        if self._variable_files is None:
            return {}
        return {
            file_id: info
            for file_id, info in self._variable_files.items()
            if info.category == CATEGORY_INGAME_SAVE
        }

    def invalidate_cache(self) -> None:
        self._variables = None
        self._variable_files = None


_default_level_variable_schema_view: LevelVariableSchemaView | None = None


def get_default_level_variable_schema_view() -> LevelVariableSchemaView:
    global _default_level_variable_schema_view
    if _default_level_variable_schema_view is None:
        _default_level_variable_schema_view = LevelVariableSchemaView()
    return _default_level_variable_schema_view


def set_default_level_variable_schema_view_active_package_id(package_id: str | None) -> None:
    schema_view = get_default_level_variable_schema_view()
    set_active = getattr(schema_view, "set_active_package_id", None)
    if callable(set_active):
        set_active(package_id)


def invalidate_default_level_variable_cache() -> None:
    global _default_level_variable_schema_view
    if _default_level_variable_schema_view is not None:
        _default_level_variable_schema_view.invalidate_cache()


__all__ = [
    "CATEGORY_CUSTOM",
    "CATEGORY_INGAME_SAVE",
    "LevelVariableSchemaService",
    "LevelVariableSchemaView",
    "VariableFileInfo",
    "get_default_level_variable_schema_view",
    "invalidate_default_level_variable_cache",
    "set_default_level_variable_schema_view_active_package_id",
]

