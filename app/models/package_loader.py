"""封装 ResourceManager / PackageIndexManager 交互，统一资源读取入口"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager

if TYPE_CHECKING:
    from engine.resources.package_interfaces import PackageLike


class PackageLoader:
    """集中管理与资源管理器的交互，供 Todo 生成流程复用。

    约定：
    - `package` 为任意实现了 `PackageLike` 协议的对象（通常为 `PackageView`）；
    - 本类仅读取包的只读字段（package_id/level_entity 等），索引读写交给 `PackageIndexManager`。
    """

    def __init__(
        self,
        package: "PackageLike",
        resource_manager: Optional[ResourceManager],
        *,
        package_index_manager: Optional[PackageIndexManager] = None,
    ) -> None:
        self.package = package
        self.resource_manager = resource_manager
        self._graph_name_cache: Dict[str, str] = {}
        # 优先使用调用方注入的单例，避免在模型层重复 new PackageIndexManager 导致索引/清单状态分叉
        self._package_index_manager: Optional[PackageIndexManager] = package_index_manager

    def resolve_graph_name(self, graph_id: str) -> str:
        if not graph_id:
            return ""
        if graph_id in self._graph_name_cache:
            return self._graph_name_cache[graph_id]
        graph_name = graph_id
        if self.resource_manager:
            metadata = self.resource_manager.load_graph_metadata(graph_id)
            metadata_name = metadata.get("name") if isinstance(metadata, dict) else None
            if isinstance(metadata_name, str) and metadata_name:
                graph_name = metadata_name
        self._graph_name_cache[graph_id] = graph_name
        return graph_name

    def reset_cache(self) -> None:
        self._graph_name_cache.clear()

    def get_preview_instance_id(self) -> str:
        level_entity = getattr(self.package, "level_entity", None)
        if level_entity:
            return level_entity.instance_id
        return ""

    def list_standalone_graph_ids(self, used_graph_ids: Set[str]) -> List[str]:
        if not self.resource_manager:
            return []
        package_id = getattr(self.package, "package_id", "")
        if package_id == "global_view":
            all_graph_ids = self.resource_manager.list_resources(ResourceType.GRAPH)
            return [graph_id for graph_id in all_graph_ids if graph_id not in used_graph_ids]
        if package_id == "unclassified_view":
            if hasattr(self.package, "get_unclassified_graph_ids"):
                unclassified_ids = self.package.get_unclassified_graph_ids()
                return [graph_id for graph_id in unclassified_ids if graph_id not in used_graph_ids]
            return []
        package_index_manager = self._get_package_index_manager()
        if not package_index_manager:
            return []
        package_index = package_index_manager.load_package_index(self.package.package_id)
        if not package_index or not package_index.resources.graphs:
            return []
        return [graph_id for graph_id in package_index.resources.graphs if graph_id not in used_graph_ids]

    def _get_package_index_manager(self) -> Optional[PackageIndexManager]:
        if self._package_index_manager:
            return self._package_index_manager
        if not self.resource_manager:
            return None
        workspace_path = getattr(self.resource_manager, "workspace_path", "")
        if not workspace_path:
            return None
        self._package_index_manager = PackageIndexManager(workspace_path, self.resource_manager)
        return self._package_index_manager


