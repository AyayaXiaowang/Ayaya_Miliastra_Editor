"""节点图加载器（解析 + 增强布局）。

职责：
- 解析 `.py` 节点图为 GraphModel + metadata
- 执行与编辑器一致的增强布局流程（克隆就地布局 + 差分合并）
- 组装 `load_graph()` 对外返回结构，并与 GraphCacheFacade 协作做缓存命中/回退
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.graph.models.graph_model import GraphModel
from engine.layout import LayoutService
from engine.nodes.node_registry import get_node_registry
from engine.utils.logging.logger import log_error, log_info

from .graph_cache_facade import GraphCacheFacade
from .graph_fingerprints_service import GraphFingerprintsService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState

if TYPE_CHECKING:
    from engine.graph import GraphCodeParser


class GraphLoader:
    """负责节点图加载（解析 + 增强布局）与缓存协商。"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        file_ops: ResourceFileOps,
        index_state: ResourceIndexState,
        cache_facade: GraphCacheFacade,
        fingerprints_service: GraphFingerprintsService,
    ) -> None:
        self._workspace_path = workspace_path
        self._file_ops = file_ops
        self._index_state = index_state
        self._cache_facade = cache_facade
        self._fingerprints_service = fingerprints_service

        self._graph_parser: Optional["GraphCodeParser"] = None

    def load_graph(self, graph_id: str) -> Optional[dict]:
        """加载节点图，带持久化与内存缓存。"""
        resource_file = self._resolve_graph_file_path(graph_id)
        if not resource_file or not resource_file.exists():
            return None

        if resource_file.suffix != ".py":
            log_error(
                "  [ERROR] 节点图必须是类结构 Python 文件(.py)，当前文件: {}",
                resource_file,
            )
            return None

        current_mtime = resource_file.stat().st_mtime

        cached = self._cache_facade.get_graph_from_memory_cache(graph_id, current_mtime)
        if cached is not None:
            return cached

        persisted = self._cache_facade.load_persistent_graph_cache_if_compatible(graph_id, resource_file)
        if persisted:
            log_info("[缓存][图] 命中持久化缓存：{}", graph_id)
            # 为内存缓存补齐 node_defs_fp，便于后续命中时做实现变更失效判定
            meta = persisted.get("metadata")
            if isinstance(meta, dict):
                meta.setdefault("node_defs_fp", self._cache_facade.get_current_node_defs_fingerprint())
            self._cache_facade.store_graph_in_memory_cache(graph_id, persisted, current_mtime)
            return persisted

        log_info("[缓存][图] 未命中持久化缓存，开始解析与自动布局：{}", graph_id)
        parser = self._get_graph_parser()
        graph_model, metadata = parser.parse_file(resource_file)

        if (not getattr(graph_model, "graph_variables", None)) and metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]

        self._index_state.set_file_path(ResourceType.GRAPH, graph_id, resource_file)

        # 首次加载或缓存失效时：执行与编辑器“自动排版”完全等价的增强布局流程
        self._apply_enhanced_layout_to_model(graph_model)

        graph_data = graph_model.serialize()
        result_data: Dict[str, Any] = {
            "graph_id": metadata.get("graph_id", graph_id),
            "name": metadata.get("graph_name", graph_data.get("graph_name", "")),
            "graph_type": metadata.get("graph_type", "server"),
            "folder_path": metadata.get("folder_path", ""),
            "description": metadata.get("description", ""),
            "data": graph_data,
            "metadata": {},
        }

        # 写入节点定义/解析器指纹，用于内存缓存的失效判定
        result_data["metadata"]["node_defs_fp"] = self._cache_facade.get_current_node_defs_fingerprint()

        fingerprints = self._fingerprints_service.build_fingerprints_from_graph_model(graph_model)
        if fingerprints:
            result_data["metadata"]["fingerprints"] = fingerprints

        # 记录当前布局相关设置快照（用于判断持久化缓存是否与当前布局语义兼容）
        result_data["metadata"]["layout_settings"] = self._cache_facade.current_layout_settings_snapshot()

        self._cache_facade.save_persistent_graph_cache(graph_id, resource_file, result_data)
        self._cache_facade.store_graph_in_memory_cache(graph_id, result_data, current_mtime)
        return result_data

    # ===== 内部：文件路径解析 =====

    def _resolve_graph_file_path(self, graph_id: str) -> Optional[Path]:
        resource_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                ResourceType.GRAPH, graph_id, self._index_state.filename_cache
            )
        return resource_file

    # ===== 内部：解析器惰性初始化 =====

    def _get_graph_parser(self) -> "GraphCodeParser":
        if self._graph_parser is None:
            from engine.graph import GraphCodeParser

            registry = get_node_registry(self._workspace_path, include_composite=True)
            node_library = registry.get_library()
            self._graph_parser = GraphCodeParser(self._workspace_path, node_library=node_library)
        return self._graph_parser

    # ===== 内部：增强布局差分合并 =====

    def _apply_enhanced_layout_to_model(self, model: GraphModel) -> None:
        """
        使用 LayoutService 的增强布局结果更新传入模型（仅模型层，不涉及场景）。

        设计目标：
        - 与 UI 层 AutoLayoutController 使用的“克隆就地布局 + 差分合并”流程保持语义一致；
        - 在不修改 .py 源文件的前提下，为 GraphModel 注入数据副本节点、更新连线并回填坐标；
        - 仅删除在增强结果中已被清理、且标记为数据副本的节点，避免误删用户节点。
        """
        registry = get_node_registry(self._workspace_path, include_composite=True)
        node_library = registry.get_library()

        result = LayoutService.compute_layout(
            model,
            node_library=node_library,
            include_augmented_model=True,
            workspace_path=self._workspace_path,
        )
        augmented = getattr(result, "augmented_model", None)

        # 纯数据图或布局服务未返回增强模型时，退化为只回填坐标/基本块/调试信息。
        if augmented is None:
            positions = result.positions or {}
            for node_id, pos in positions.items():
                node_obj = model.nodes.get(node_id)
                if not node_obj:
                    continue
                x_pos = float(pos[0]) if len(pos) > 0 else 0.0
                y_pos = float(pos[1]) if len(pos) > 1 else 0.0
                node_obj.pos = (x_pos, y_pos)
            model.basic_blocks = list(result.basic_blocks or [])
            debug_map = result.y_debug_info or {}
            if debug_map:
                setattr(model, "_layout_y_debug_info", dict(debug_map))
            return

        original = model
        model_node_ids_before = set(original.nodes.keys())
        model_edge_ids_before = set(original.edges.keys())
        augmented_node_ids = set(augmented.nodes.keys())
        augmented_edge_ids = set(augmented.edges.keys())

        # 合并增强模型中新出现的节点（例如跨块复制产生的数据副本）。
        nodes_to_add = augmented_node_ids - model_node_ids_before
        for node_id in nodes_to_add:
            original.nodes[node_id] = augmented.nodes[node_id]

        # 合并增强模型中新出现的连线。
        edges_to_add = augmented_edge_ids - model_edge_ids_before
        for edge_id in edges_to_add:
            original.edges[edge_id] = augmented.edges[edge_id]

        # 删除在增强结果中被移除的旧连线（例如被副本间连线替换的跨块旧边）。
        edges_to_remove = model_edge_ids_before - augmented_edge_ids
        if edges_to_remove:
            for edge_id in list(edges_to_remove):
                original.edges.pop(edge_id, None)

        # 删除在增强结果中被清理掉的孤立副本节点，仅针对数据副本节点生效，避免误删用户节点。
        nodes_to_remove = model_node_ids_before - augmented_node_ids
        if nodes_to_remove:
            for node_id in list(nodes_to_remove):
                node_obj = original.nodes.get(node_id)
                if not node_obj:
                    continue
                if not getattr(node_obj, "is_data_node_copy", False):
                    continue
                # 先移除与该副本节点关联的边
                related_edge_ids = [
                    edge_id
                    for edge_id, edge in original.edges.items()
                    if edge.src_node == node_id or edge.dst_node == node_id
                ]
                for edge_id in related_edge_ids:
                    original.edges.pop(edge_id, None)
                # 再移除节点本身
                original.nodes.pop(node_id, None)

        # 回填坐标：以增强模型中的坐标为准，确保节点与副本的最终位置与自动排版一致。
        for node_id, aug_node in augmented.nodes.items():
            node_obj = original.nodes.get(node_id)
            if not node_obj:
                continue
            pos = getattr(aug_node, "pos", (0.0, 0.0)) or (0.0, 0.0)
            x_pos = float(pos[0]) if len(pos) > 0 else 0.0
            y_pos = float(pos[1]) if len(pos) > 1 else 0.0
            node_obj.pos = (x_pos, y_pos)

        # 回填基本块与布局 Y 调试信息。
        basic_blocks = list(getattr(result, "basic_blocks", None) or augmented.basic_blocks or [])
        original.basic_blocks = basic_blocks

        debug_map_aug = getattr(augmented, "_layout_y_debug_info", None) or {}
        if debug_map_aug:
            setattr(original, "_layout_y_debug_info", dict(debug_map_aug))


