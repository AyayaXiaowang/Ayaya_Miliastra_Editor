from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Tuple

from app.common.in_memory_graph_payload_cache import (
    clear_all_graph_data,
    drop_graph_data_for_graph,
    drop_graph_data_for_root,
    resolve_graph_data,
    store_graph_data,
)
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from engine.resources.graph_reference_tracker import GraphReferenceTracker
from engine.resources.package_index import PackageResources
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager, ResourceType

from .graph_model_cache import GraphModelCacheEntry, get_or_build_graph_model


@dataclass
class GraphLoadPayload:
    graph_config: Optional[GraphConfig] = None
    graph_data: Optional[dict] = None
    graph_model: Optional[GraphModel] = None
    references: List[Tuple[str, str, str, str]] = field(default_factory=list)
    error: Optional[str] = None


class GraphDataService:
    """图数据门面：统一加载 graph_config / graph_data / graph_model，并提供集中缓存与失效入口。

    设计目标：
    - 作为 UI/任务清单/预览/导航共用的稳定 service（无 PyQt6 依赖）；
    - 统一 GraphModel 缓存的签名失效，避免布局变更后复用旧模型；
    - 桥接进程内 graph_data payload 缓存（graph_data_key），减少“各处各自缓存一份图”的分叉风险。
    """

    def __init__(
        self,
        resource_manager: Optional[ResourceManager],
        package_index_manager: Optional[PackageIndexManager],
    ) -> None:
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self._lock = Lock()

        self._graph_config_cache: Dict[str, GraphConfig] = {}
        self._graph_model_cache: Dict[str, GraphModelCacheEntry] = {}
        self._reference_cache: Dict[str, List[Tuple[str, str, str, str]]] = {}
        self._graph_membership_cache: Dict[str, set[str]] = {}

        self._packages_cache: List[dict] = []
        self._package_map: Dict[str, dict] = {}
        self._package_resources_cache: Dict[str, PackageResources] = {}
        self._package_cache_token: str = ""

        self._reference_tracker = (
            GraphReferenceTracker(resource_manager, package_index_manager)
            if resource_manager and package_index_manager
            else None
        )

    # ------------------------------------------------------------------ Graph data (engine-backed)
    def load_graph_payload(self, graph_id: str) -> GraphLoadPayload:
        payload = GraphLoadPayload()
        if not graph_id:
            payload.error = "未指定节点图，无法加载。"
            return payload
        if not self.resource_manager:
            payload.error = "未配置资源管理器，无法加载节点图。"
            return payload

        graph_config = self.get_graph_config(graph_id)
        if not graph_config:
            payload.error = f"节点图 '{graph_id}' 不存在或已被删除。"
            return payload

        graph_data = graph_config.data
        payload.graph_config = graph_config
        payload.graph_data = graph_data
        payload.graph_model = self.get_graph_model(graph_id, graph_data=graph_data)
        payload.references = self.get_references(graph_id)
        return payload

    def get_graph_config(self, graph_id: str) -> Optional[GraphConfig]:
        return self._load_graph_config(graph_id)

    def load_graph_data(self, graph_id: str) -> Optional[dict]:
        graph_config = self._load_graph_config(graph_id)
        return graph_config.data if graph_config else None

    def get_graph_model(self, graph_id: str, *, graph_data: Optional[dict] = None) -> Optional[GraphModel]:
        if not graph_id:
            return None
        if graph_data is None:
            graph_data = self.load_graph_data(graph_id)
        if not isinstance(graph_data, dict):
            return None
        with self._lock:
            return get_or_build_graph_model(
                graph_id,
                graph_data=graph_data,
                cache=self._graph_model_cache,
            )

    def get_references(self, graph_id: str) -> List[Tuple[str, str, str, str]]:
        with self._lock:
            cached = self._reference_cache.get(graph_id)
        if cached is not None:
            return cached
        if not self._reference_tracker:
            return []
        references = self._reference_tracker.find_references(graph_id)
        with self._lock:
            self._reference_cache[graph_id] = references
        return references

    def invalidate_graph(self, graph_id: Optional[str] = None) -> None:
        """失效本 service 内部缓存（不包含进程内 payload 缓存）。"""
        with self._lock:
            if graph_id:
                self._graph_config_cache.pop(graph_id, None)
                self._graph_model_cache.pop(graph_id, None)
                self._reference_cache.pop(graph_id, None)
                self._graph_membership_cache.pop(graph_id, None)
            else:
                self._graph_config_cache.clear()
                self._graph_model_cache.clear()
                self._reference_cache.clear()
                self._graph_membership_cache.clear()

    def _load_graph_config(self, graph_id: str) -> Optional[GraphConfig]:
        with self._lock:
            cached = self._graph_config_cache.get(graph_id)
        if cached:
            return cached
        if not self.resource_manager:
            return None
        graph_resource = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_resource:
            return None
        graph_config = GraphConfig.deserialize(graph_resource)
        with self._lock:
            self._graph_config_cache[graph_id] = graph_config
        return graph_config

    # ------------------------------------------------------------------ Graph data (process in-memory payload cache)
    def resolve_payload_graph_data(self, detail_info: Dict[str, object]) -> Optional[dict]:
        data = resolve_graph_data(detail_info)
        if isinstance(data, dict):
            return data
        return None

    def store_payload_graph_data(self, graph_root_id: str, graph_id: str, graph_data: dict) -> str:
        return store_graph_data(graph_root_id, graph_id, graph_data)

    def drop_payload_for_root(self, graph_root_id: str) -> None:
        drop_graph_data_for_root(graph_root_id)

    def drop_payload_for_graph(self, graph_id: str) -> None:
        drop_graph_data_for_graph(graph_id)

    def clear_all_payload_graph_data(self) -> int:
        return clear_all_graph_data()

    # ------------------------------------------------------------------ Package cache (for graph membership & listing)
    def get_packages(self) -> List[dict]:
        self._ensure_package_cache()
        return list(self._packages_cache)

    def get_package_map(self) -> Dict[str, dict]:
        self._ensure_package_cache()
        return dict(self._package_map)

    def get_graph_membership(self, graph_id: str) -> set[str]:
        with self._lock:
            cached = self._graph_membership_cache.get(graph_id)
        if cached is not None:
            return set(cached)
        memberships = set()
        packages = self.get_packages()
        for pkg in packages:
            pkg_id = pkg.get("package_id", "")
            if not pkg_id:
                continue
            resources = self._get_package_resources(pkg_id)
            if resources and graph_id in resources.graphs:
                memberships.add(pkg_id)
        with self._lock:
            self._graph_membership_cache[graph_id] = memberships
        return set(memberships)

    def invalidate_package_cache(self) -> None:
        with self._lock:
            self._packages_cache.clear()
            self._package_map.clear()
            self._package_resources_cache.clear()
            self._package_cache_token = ""
            self._graph_membership_cache.clear()

    def _ensure_package_cache(self) -> None:
        if not self.package_index_manager:
            return
        packages = self.package_index_manager.list_packages()
        token = self._build_package_cache_token(packages)
        with self._lock:
            if token == self._package_cache_token:
                return
            self._package_cache_token = token
            self._packages_cache = list(packages)
            self._package_map = {
                pkg.get("package_id", ""): pkg for pkg in self._packages_cache if pkg.get("package_id")
            }
            self._package_resources_cache.clear()
            self._graph_membership_cache.clear()

    def _build_package_cache_token(self, packages: List[dict]) -> str:
        if not packages:
            return ""
        parts = [f"{pkg.get('package_id','')}:{pkg.get('updated_at','')}" for pkg in packages]
        return "|".join(parts)

    def _get_package_resources(self, package_id: str) -> Optional[PackageResources]:
        with self._lock:
            cached = self._package_resources_cache.get(package_id)
        if cached:
            return cached
        if not self.package_index_manager:
            return None
        resources = self.package_index_manager.get_package_resources(package_id)
        if resources:
            with self._lock:
                self._package_resources_cache[package_id] = resources
        return resources


_SHARED_SERVICE_LOCK = Lock()
_SHARED_SERVICES: Dict[Tuple[int, int], GraphDataService] = {}


def get_shared_graph_data_service(
    resource_manager: Optional[ResourceManager],
    package_index_manager: Optional[PackageIndexManager],
) -> GraphDataService:
    """按资源管理器维度缓存 GraphDataService，避免多处重复建立缓存。"""
    key = (id(resource_manager), id(package_index_manager))
    with _SHARED_SERVICE_LOCK:
        service = _SHARED_SERVICES.get(key)
        if service is None:
            service = GraphDataService(resource_manager, package_index_manager)
            _SHARED_SERVICES[key] = service
        return service


