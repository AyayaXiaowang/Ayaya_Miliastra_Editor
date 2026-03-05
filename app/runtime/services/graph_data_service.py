from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor
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


_GRAPH_RESOURCE_LOAD_EXECUTOR: ThreadPoolExecutor | None = None
_GRAPH_RESOURCE_LOAD_EXECUTOR_LOCK = Lock()


def _get_graph_resource_load_executor() -> ThreadPoolExecutor:
    """延迟初始化线程池：用于将“图资源解析异常”隔离为可读错误，不让异常炸穿 UI 主线程。

    注意：本模块属于 runtime service（无 UI 依赖），但会被 UI 同步调用；
    当资源库中存在非法节点图源码时，`ResourceManager.load_resource(ResourceType.GRAPH, ...)`
    可能抛出解析异常。这里用 Future.exception() 获取异常文本，避免上层被直接打断。
    """
    global _GRAPH_RESOURCE_LOAD_EXECUTOR
    with _GRAPH_RESOURCE_LOAD_EXECUTOR_LOCK:
        if _GRAPH_RESOURCE_LOAD_EXECUTOR is None:
            _GRAPH_RESOURCE_LOAD_EXECUTOR = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="graph-resource-loader",
            )
            atexit.register(_GRAPH_RESOURCE_LOAD_EXECUTOR.shutdown, False)
        return _GRAPH_RESOURCE_LOAD_EXECUTOR


def shutdown_graph_resource_load_executor() -> None:
    """退出阶段显式关闭图资源加载线程池。

    设计目标：
    - 避免窗口关闭阶段残留 ThreadPoolExecutor worker 线程；
    - 若有未执行的任务，使用 cancel_futures=True 直接取消。
    """
    global _GRAPH_RESOURCE_LOAD_EXECUTOR
    with _GRAPH_RESOURCE_LOAD_EXECUTOR_LOCK:
        executor = _GRAPH_RESOURCE_LOAD_EXECUTOR
        _GRAPH_RESOURCE_LOAD_EXECUTOR = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


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
        # graph_id -> 最近一次“加载/解析节点图资源”失败原因（用于 UI 友好提示）
        self._graph_load_error_cache: Dict[str, str] = {}

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
            error_text = self.get_graph_load_error(graph_id)
            payload.error = error_text or f"节点图 '{graph_id}' 不存在或已被删除。"
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
        """失效图相关的所有内存缓存（GraphConfig/GraphModel/引用缓存 + 进程内 payload 缓存）。

        设计目标：提供“一句就能清干净”的集中失效入口，避免 UI/后台重载/预览/执行各自清一段缓存链条而分叉。
        """
        with self._lock:
            if graph_id:
                self._graph_config_cache.pop(graph_id, None)
                self._graph_model_cache.pop(graph_id, None)
                self._reference_cache.pop(graph_id, None)
                self._graph_membership_cache.pop(graph_id, None)
                self._graph_load_error_cache.pop(graph_id, None)
            else:
                self._graph_config_cache.clear()
                self._graph_model_cache.clear()
                self._reference_cache.clear()
                self._graph_membership_cache.clear()
                self._graph_load_error_cache.clear()

        # payload 缓存为进程级共享（模块全局），因此这里必须一起失效，
        # 否则会出现“某入口清了 GraphModel/GraphConfig，但预览/执行仍复用旧 payload”的回退。
        if graph_id:
            drop_graph_data_for_graph(graph_id)
        else:
            clear_all_graph_data()

    def get_graph_load_error(self, graph_id: str) -> Optional[str]:
        """返回节点图最近一次加载失败原因（若存在）。"""
        if not graph_id:
            return None
        with self._lock:
            return self._graph_load_error_cache.get(graph_id)

    def _load_graph_config(self, graph_id: str) -> Optional[GraphConfig]:
        with self._lock:
            cached = self._graph_config_cache.get(graph_id)
        if cached:
            return cached
        if not self.resource_manager:
            return None
        executor = _get_graph_resource_load_executor()
        future = executor.submit(self.resource_manager.load_resource, ResourceType.GRAPH, graph_id)
        if future.cancelled():
            with self._lock:
                self._graph_load_error_cache[graph_id] = f"节点图 '{graph_id}' 加载已取消。"
            return None

        error = future.exception()
        if error is not None:
            with self._lock:
                self._graph_load_error_cache[graph_id] = (
                    f"节点图 '{graph_id}' 加载失败：{error}"
                )
            return None

        graph_resource = future.result()
        if not isinstance(graph_resource, dict):
            with self._lock:
                self._graph_load_error_cache.pop(graph_id, None)
            return None
        if (not graph_resource.get("graph_id")) or ("name" not in graph_resource):
            with self._lock:
                self._graph_load_error_cache[graph_id] = (
                    f"节点图 '{graph_id}' 加载失败：缺少必要字段 graph_id/name。"
                )
            return None

        graph_config = GraphConfig.deserialize(graph_resource)
        with self._lock:
            self._graph_config_cache[graph_id] = graph_config
            self._graph_load_error_cache.pop(graph_id, None)
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
        """返回节点图的“归属根目录”集合（单选语义）。

        目录即存档模式下，节点图归属由其物理文件所在的资源根目录决定：
        - {"shared"}：位于 `assets/资源库/共享/节点图/`
        - {"<package_id>"}：位于 `assets/资源库/项目存档/<package_id>/节点图/`
        """
        with self._lock:
            cached = self._graph_membership_cache.get(graph_id)
        if cached is not None:
            return set(cached)

        manager = self.package_index_manager
        if manager is None:
            return set()

        owner_id = manager.get_resource_owner_root_id(resource_type="graph", resource_id=graph_id)
        memberships: set[str] = set()
        if owner_id:
            memberships.add(owner_id)

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


