"""GraphEditorController 的 GraphScene 运行期 LRU 缓存 mixin。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from engine.graph.models.graph_model import GraphModel
from engine.resources.graph_cache_facade import GraphCacheFacade
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.controllers.graph_editor_flow import GraphEditorLoadRequest
from app.ui.graph.graph_scene import GraphScene


@dataclass(slots=True)
class _GraphSceneCacheEntry:
    """运行期 GraphScene 缓存项（同一次进程内复用 QGraphicsItem）。"""

    graph_id: str
    model: GraphModel
    scene: GraphScene
    baseline_content_hash: str
    edit_session_capabilities: EditSessionCapabilities
    node_defs_fp: str
    layout_settings: dict
    build_settings_signature: tuple[tuple[str, object], ...]
    graph_file_path: str
    graph_file_mtime_ms: int


class GraphEditorSceneCacheMixin:
    # === GraphScene 运行期 LRU 缓存（QGraphicsItem 复用；同进程 A→B→A 秒切回）===

    def _get_graph_scene_lru_cache_capacity(self) -> int:
        from engine.configs.settings import settings as _settings_ui

        capacity = int(getattr(_settings_ui, "GRAPH_SCENE_LRU_CACHE_SIZE", 2) or 2)
        return int(capacity) if int(capacity) > 0 else 0

    def _is_graph_scene_lru_cache_enabled(self) -> bool:
        return self._get_graph_scene_lru_cache_capacity() > 0

    def _current_graph_scene_build_settings_signature(self) -> tuple[tuple[str, object], ...]:
        """影响 GraphScene/图元装配的设置签名（用于缓存失效判定）。"""
        from engine.configs.settings import settings as _settings_ui

        keys = [
            # 行内常量控件虚拟化：节点图元是否常驻创建 QGraphicsProxyWidget
            "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED",
            # 大图快速预览：是否创建端口/常量控件等重图元
            "GRAPH_FAST_PREVIEW_ENABLED",
            "GRAPH_FAST_PREVIEW_NODE_THRESHOLD",
            "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD",
            # 批量边层：是否创建 BatchedFastPreviewEdgeLayer（替代 per-edge item）
            "GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED",
            "GRAPH_READONLY_BATCHED_EDGES_ENABLED",
            "GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_CELL_SIZE",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_STROKE_WIDTH",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_BOUNDS_MARGIN",
            # YDebug 会强制关闭批量边层（依赖逐边图元）
            "SHOW_LAYOUT_Y_DEBUG",
            # basic blocks 可能在 GraphScene 初始化阶段被补算（开关变化需失效缓存）
            "SHOW_BASIC_BLOCKS",
        ]
        return tuple((k, getattr(_settings_ui, k, None)) for k in keys)

    def _get_graph_file_fingerprint(self, graph_id: str) -> tuple[str, int]:
        """返回 (resolved_path_posix, mtime_ms)；无法定位则返回 ("", 0)。"""
        file_path = self.resource_manager.get_graph_file_path(str(graph_id))
        if file_path is None:
            return "", 0
        if not file_path.exists():
            return "", 0
        resolved_path = file_path.resolve().as_posix()
        mtime_ms = int(file_path.stat().st_mtime * 1000)
        return str(resolved_path), int(mtime_ms)

    def _dispose_scene_cache_entry(self, entry: _GraphSceneCacheEntry) -> None:
        scene = getattr(entry, "scene", None)
        if scene is None:
            return
        scene.clear()
        if hasattr(scene, "node_items"):
            scene.node_items.clear()
        if hasattr(scene, "edge_items"):
            scene.edge_items.clear()
        if hasattr(scene, "undo_manager") and getattr(scene, "undo_manager", None) is not None:
            scene.undo_manager.clear()
        # GraphScene/QGraphicsScene 为 QObject：尽量让 Qt 侧也及时释放
        if hasattr(scene, "deleteLater"):
            scene.deleteLater()

    def _clear_scene_lru_cache(self) -> None:
        cache = getattr(self, "_scene_lru_cache", None)
        if not isinstance(cache, OrderedDict) or not cache:
            return
        for entry in list(cache.values()):
            self._dispose_scene_cache_entry(entry)
        cache.clear()

    def _trim_scene_lru_cache(self) -> None:
        capacity = int(self._get_graph_scene_lru_cache_capacity())
        if capacity <= 0:
            self._clear_scene_lru_cache()
            return
        while len(self._scene_lru_cache) > capacity:
            _graph_id, evicted = self._scene_lru_cache.popitem(last=False)
            self._dispose_scene_cache_entry(evicted)

    def _is_scene_cache_entry_compatible(
        self,
        entry: _GraphSceneCacheEntry,
        *,
        expected_capabilities: EditSessionCapabilities,
    ) -> bool:
        if not isinstance(entry, _GraphSceneCacheEntry):
            return False
        if not entry.graph_id:
            return False
        if entry.scene is None or entry.model is None:
            return False
        if bool(getattr(entry.scene, "is_composite_editor", False)):
            return False

        # 能力不一致：fast_preview_mode / read_only 等图元结构可能不一致，禁止复用
        if entry.edit_session_capabilities != expected_capabilities:
            return False

        # 节点实现/解析器变更：必须失效（避免复用旧端口规则/标题等）
        current_node_defs_fp = compute_node_defs_fingerprint(self.resource_manager.workspace_path)
        if str(entry.node_defs_fp or "") != str(current_node_defs_fp or ""):
            return False

        # 布局设置快照：切换布局语义后不应复用旧场景（避免结构增强/副本等差异）
        current_layout_settings = GraphCacheFacade.current_layout_settings_snapshot()
        if entry.layout_settings != current_layout_settings:
            return False

        # 画布装配开关：影响图元结构/边层，必须一致
        if entry.build_settings_signature != self._current_graph_scene_build_settings_signature():
            return False

        # 图文件变更：必须失效（避免显示旧模型）
        current_path, current_mtime_ms = self._get_graph_file_fingerprint(entry.graph_id)
        if not current_path or int(current_mtime_ms) <= 0:
            return False
        if str(entry.graph_file_path or "") != str(current_path):
            return False
        if int(entry.graph_file_mtime_ms) != int(current_mtime_ms):
            return False

        return True

    def _pop_scene_from_cache_if_compatible(
        self,
        *,
        graph_id: str,
        expected_capabilities: EditSessionCapabilities,
    ) -> _GraphSceneCacheEntry | None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return None
        entry = self._scene_lru_cache.get(graph_id_text)
        if entry is None:
            return None
        if not self._is_scene_cache_entry_compatible(entry, expected_capabilities=expected_capabilities):
            self._scene_lru_cache.pop(graph_id_text, None)
            self._dispose_scene_cache_entry(entry)
            return None
        return self._scene_lru_cache.pop(graph_id_text)

    def _cache_current_scene_as_inactive(self, *, next_graph_id: str) -> bool:
        """将当前 graph 的 scene 作为“非激活缓存”存入 LRU（用于 A→B→A 秒切回）。"""
        if not self._is_graph_scene_lru_cache_enabled():
            return False

        current_graph_id = str(self.current_graph_id or "").strip()
        if not current_graph_id:
            return False
        if str(next_graph_id or "").strip() == current_graph_id:
            return False
        if self.scene is None or self.model is None:
            return False
        if bool(getattr(self.scene, "is_composite_editor", False)):
            return False
        # 若仍在“非阻塞分帧装配”中：避免缓存半成品场景
        if self._async_populate_job is not None:
            return False

        file_path, file_mtime_ms = self._get_graph_file_fingerprint(current_graph_id)
        if not file_path or int(file_mtime_ms) <= 0:
            return False

        baseline_hash = str(self._session_state_machine.baseline_content_hash or "").strip()
        if not baseline_hash:
            baseline_hash = self.model.get_content_hash()

        entry = _GraphSceneCacheEntry(
            graph_id=str(current_graph_id),
            model=self.model,
            scene=self.scene,
            baseline_content_hash=str(baseline_hash),
            edit_session_capabilities=self._session_state_machine.capabilities,
            node_defs_fp=compute_node_defs_fingerprint(self.resource_manager.workspace_path),
            layout_settings=GraphCacheFacade.current_layout_settings_snapshot(),
            build_settings_signature=self._current_graph_scene_build_settings_signature(),
            graph_file_path=str(file_path),
            graph_file_mtime_ms=int(file_mtime_ms),
        )

        existing = self._scene_lru_cache.pop(str(current_graph_id), None)
        if existing is not None:
            # 兜底：理论上 active graph 不应同时在 cache 中；若存在且不是同一个 scene，则释放旧缓存项
            if getattr(existing, "scene", None) is not self.scene:
                self._dispose_scene_cache_entry(existing)

        self._scene_lru_cache[str(current_graph_id)] = entry
        self._scene_lru_cache.move_to_end(str(current_graph_id))
        self._trim_scene_lru_cache()
        return True

    def _restore_graph_from_scene_cache_entry(
        self,
        *,
        entry: _GraphSceneCacheEntry,
        request: GraphEditorLoadRequest,
    ) -> None:
        """将缓存的 GraphScene 重新挂回 view，并走统一收尾（graph_loaded/save_status/camera）。"""
        graph_id = str(entry.graph_id)
        scene = entry.scene
        model = entry.model

        # 复用场景时将 node_library 指向当前库（避免引用旧 dict）
        if hasattr(scene, "node_library"):
            scene.node_library = self.node_library

        self._load_service.attach_scene_to_view_for_load(
            scene=scene,
            view=self.view,
            node_library=self.node_library,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = model
        self.scene = scene
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 加载后按需同步信号节点端口（保持与正常加载口径一致）
        self._load_service.sync_signals_after_load_if_needed(
            scene=self.scene,
            model=self.model,
            get_current_package=self.get_current_package,
        )

        baseline_hash = self.model.get_content_hash()
        self._finalize_after_graph_loaded(
            graph_id=str(graph_id),
            container=request.container,
            baseline_hash=str(baseline_hash),
        )

