from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Tuple

from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from engine.resources.graph_reference_tracker import GraphReferenceTracker
from engine.resources.package_index import PackageResources
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager, ResourceType


@dataclass
class GraphLoadPayload:
    graph_config: Optional[GraphConfig] = None
    graph_model: Optional[GraphModel] = None
    references: List[Tuple[str, str, str, str]] = field(default_factory=list)
    error: Optional[str] = None


class GraphDataProvider:
    """集中维护节点图/引用/存档缓存，供多个面板复用。"""

    def __init__(
        self,
        resource_manager: Optional[ResourceManager],
        package_index_manager: Optional[PackageIndexManager],
    ) -> None:
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self._lock = Lock()

        self._graph_config_cache: Dict[str, GraphConfig] = {}
        self._graph_model_cache: Dict[str, GraphModel] = {}
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

    # ------------------------------------------------------------------ Graph data
    def load_graph_payload(self, graph_id: str) -> GraphLoadPayload:
        payload = GraphLoadPayload()
        if not graph_id:
            payload.error = "未指定节点图，无法加载。"
            return payload
        if not self.resource_manager:
            payload.error = "未配置资源管理器，无法加载节点图。"
            return payload

        graph_config = self._load_graph_config(graph_id)
        if not graph_config:
            payload.error = f"节点图 '{graph_id}' 不存在或已被删除。"
            return payload

        payload.graph_config = graph_config
        payload.graph_model = self._load_graph_model(graph_id, graph_config)
        payload.references = self._load_references(graph_id)
        return payload

    def get_graph_config(self, graph_id: str) -> Optional[GraphConfig]:
        return self._load_graph_config(graph_id)

    def invalidate_graph(self, graph_id: Optional[str] = None) -> None:
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
        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            return None
        graph_config = GraphConfig.deserialize(graph_data)
        with self._lock:
            self._graph_config_cache[graph_id] = graph_config
        return graph_config

    def _load_graph_model(self, graph_id: str, graph_config: GraphConfig) -> Optional[GraphModel]:
        with self._lock:
            cached = self._graph_model_cache.get(graph_id)
        if cached:
            return cached
        graph_model = GraphModel.deserialize(graph_config.data)
        with self._lock:
            self._graph_model_cache[graph_id] = graph_model
        return graph_model

    def _load_references(self, graph_id: str) -> List[Tuple[str, str, str, str]]:
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

    # ------------------------------------------------------------------ Package cache
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
        parts = [
            f"{pkg.get('package_id','')}:{pkg.get('updated_at','')}"
            for pkg in packages
        ]
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


_SHARED_PROVIDER_LOCK = Lock()
_SHARED_PROVIDERS: Dict[Tuple[int, int], GraphDataProvider] = {}


def get_shared_graph_data_provider(
    resource_manager: Optional[ResourceManager],
    package_index_manager: Optional[PackageIndexManager],
) -> GraphDataProvider:
    """按资源管理器维度缓存 GraphDataProvider，避免多处重复建立缓存。"""
    key = (id(resource_manager), id(package_index_manager))
    with _SHARED_PROVIDER_LOCK:
        provider = _SHARED_PROVIDERS.get(key)
        if provider is None:
            provider = GraphDataProvider(resource_manager, package_index_manager)
            _SHARED_PROVIDERS[key] = provider
        return provider
