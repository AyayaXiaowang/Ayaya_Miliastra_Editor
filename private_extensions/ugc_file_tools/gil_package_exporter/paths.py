from __future__ import annotations

from pathlib import Path


def _resolve_ugc_file_tools_root_path() -> Path:
    from ugc_file_tools.repo_paths import ugc_file_tools_root

    return ugc_file_tools_root()


def _resolve_default_dtype_path() -> Path:
    ugc_file_tools_root_path = _resolve_ugc_file_tools_root_path()
    return ugc_file_tools_root_path / "builtin_resources" / "dtype" / "dtype.json"


def _resolve_parse_status_root_path() -> Path:
    """
    解析状态统一输出目录（不写入 Graph_Generater 资源库，避免与编辑器工程耦合）。
    """
    ugc_file_tools_root_path = _resolve_ugc_file_tools_root_path()
    return ugc_file_tools_root_path / "parse_status"


def resolve_ugc_file_tools_root_path() -> Path:
    """对外 API：返回 `ugc_file_tools/` 目录绝对路径。"""
    return _resolve_ugc_file_tools_root_path()


def resolve_default_dtype_path() -> Path:
    """对外 API：返回默认 dtype.json 路径。"""
    return _resolve_default_dtype_path()


def resolve_parse_status_root_path() -> Path:
    """对外 API：返回解析状态输出根目录（ugc_file_tools/parse_status）。"""
    return _resolve_parse_status_root_path()


