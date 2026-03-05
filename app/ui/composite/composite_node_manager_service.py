"""复合节点库 service：提供 UI 侧的扁平行数据与 CRUD/加载/保存能力。

该模块不包含 Qt 依赖，供 `CompositeNodeManagerWidget` 与其它 UI 组件复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.nodes.advanced_node_features import CompositeNodeConfig
from engine.nodes.composite_node_manager import CompositeNodeManager, get_composite_node_manager
from engine.nodes.node_registry import get_node_registry
from app.codegen import CompositeCodeGenerator


@dataclass(frozen=True)
class CompositeNodeRow:
    """复合节点在左侧树/列表中的扁平行数据表示。"""

    composite_id: str
    node_name: str
    folder_path: str
    description: str


class CompositeNodeService:
    """复合节点库的应用服务层。

    封装 CompositeNodeManager，提供：
    - iter_rows(): 扁平行数据（名称、文件夹等），供左树/列表渲染；
    - CRUD：create/delete/move 文件夹与复合节点；
    - load/save：按需加载子图并写回 CompositeNodeConfig。
    """

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path
        registry = get_node_registry(workspace_path, include_composite=True)
        node_library = registry.get_library()
        code_generator = CompositeCodeGenerator(node_library)
        self._manager = get_composite_node_manager(
            workspace_path,
            base_node_library=node_library,
            composite_code_generator=code_generator,
        )

    @property
    def manager(self) -> CompositeNodeManager:
        return self._manager

    def iter_rows(self) -> list[CompositeNodeRow]:
        rows: list[CompositeNodeRow] = []
        for composite_config in self._manager.list_composite_nodes():
            rows.append(
                CompositeNodeRow(
                    composite_id=composite_config.composite_id,
                    node_name=composite_config.node_name,
                    folder_path=composite_config.folder_path or "",
                    description=composite_config.node_description or "",
                )
            )
        return rows

    def list_folders(self) -> list[str]:
        return list(self._manager.folder_manager.folders)

    def load_composite(
        self,
        composite_id: str,
        *,
        ensure_subgraph: bool = True,
    ) -> Optional[CompositeNodeConfig]:
        if ensure_subgraph:
            self._manager.load_subgraph_if_needed(composite_id)
        return self._manager.get_composite_node(composite_id)

    def create_composite(self, folder_path: str) -> str:
        """创建新的复合节点，返回 composite_id。"""
        return self._manager.create_composite_node(
            node_name=None,
            node_description="",
            sub_graph={"nodes": [], "edges": [], "graph_variables": []},
            virtual_pins=[],
            folder_path=folder_path or "",
        )

    def create_folder(self, folder_name: str, parent_folder_path: str) -> bool:
        return self._manager.create_folder(folder_name, parent_folder_path or "")

    def delete_composite(self, composite_id: str) -> Optional[CompositeNodeConfig]:
        composite_config = self._manager.get_composite_node(composite_id)
        if composite_config is None:
            return None
        self._manager.delete_composite_node(composite_id)
        return composite_config

    def delete_folder(self, folder_path: str) -> bool:
        return self._manager.delete_folder(folder_path, force=True)

    def move_composite(self, composite_id: str, target_folder_path: str) -> bool:
        return self._manager.move_to_folder(composite_id, target_folder_path or "")

    def analyze_update_impact(
        self,
        composite_id: str,
        composite_config: CompositeNodeConfig,
    ) -> dict:
        return self._manager.analyze_composite_update_impact(composite_id, composite_config)

    def persist_updated_composite(
        self,
        composite_id: str,
        composite_config: CompositeNodeConfig,
        *,
        skip_impact_check: bool,
    ) -> None:
        self._manager.update_composite_node(
            composite_id,
            composite_config,
            skip_impact_check=skip_impact_check,
        )


