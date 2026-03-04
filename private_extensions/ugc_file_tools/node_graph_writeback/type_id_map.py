from __future__ import annotations

"""
ugc_file_tools.node_graph_writeback.type_id_map

兼容薄 wrapper（保持旧 import 路径稳定）：
- 单一真源实现已上移到 `ugc_file_tools.node_graph_semantics.type_id_map`；
- 写回侧与 pipelines 仍可继续从本模块导入公开 helper，但不要跨域复制实现。
"""

from pathlib import Path
from typing import Dict

from ugc_file_tools.node_graph_semantics.type_id_map import (
    build_node_def_key_to_type_id as _sem_build_node_def_key_to_type_id,
    build_node_name_to_type_id as _sem_build_node_name_to_type_id,
)


def _build_node_name_to_type_id(*, mapping_path: Path, scope: str) -> Dict[str, int]:
    """兼容旧私有入口：转发到共享语义层。"""
    return _sem_build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope))


def _build_node_def_key_to_type_id(
    *,
    mapping_path: Path,
    scope: str,
    graph_generater_root: Path,
) -> Dict[str, int]:
    """兼容旧私有入口：转发到共享语义层。"""
    return _sem_build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )


def _build_server_node_name_to_type_id(mapping_path: Path) -> Dict[str, int]:
    return _sem_build_node_name_to_type_id(mapping_path=Path(mapping_path), scope="server")


def _build_client_node_name_to_type_id(mapping_path: Path) -> Dict[str, int]:
    return _sem_build_node_name_to_type_id(mapping_path=Path(mapping_path), scope="client")


__all__ = [
    "build_node_name_to_type_id",
    "build_node_def_key_to_type_id",
]


def build_node_name_to_type_id(*, mapping_path: Path, scope: str) -> Dict[str, int]:
    return _sem_build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope))


def build_node_def_key_to_type_id(*, mapping_path: Path, scope: str, graph_generater_root: Path) -> Dict[str, int]:
    return _sem_build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )

