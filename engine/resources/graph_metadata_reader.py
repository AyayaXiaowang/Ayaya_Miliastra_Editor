"""节点图轻量元数据读取器（不执行节点图代码）。

职责：
- 从 `.py` 源码 docstring/注释中提取轻量元数据（graph_id/name/type/folder/description）
- 为列表展示统计 node_count/edge_count：
  - 优先复用持久化图缓存（命中且兼容时）
  - 否则退化为基于正则/行规则的轻量估算
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.utils.cache.cache_paths import get_graph_cache_dir

from .graph_cache_facade import GraphCacheFacade
from .resource_cache_service import ResourceCacheService
from .resource_file_ops import ResourceFileOps
from .resource_state import ResourceIndexState


class GraphMetadataReader:
    """节点图轻量元数据读取器（列表页用）。"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        file_ops: ResourceFileOps,
        index_state: ResourceIndexState,
        cache_service: ResourceCacheService,
        cache_facade: GraphCacheFacade,
    ) -> None:
        self._workspace_path = workspace_path
        self._file_ops = file_ops
        self._index_state = index_state
        self._cache_service = cache_service
        self._cache_facade = cache_facade

    def load_graph_metadata(self, graph_id: str) -> Optional[dict]:
        """加载节点图的轻量级元数据（不执行节点图代码）。"""
        resource_file = self._resolve_graph_file_path(graph_id)
        if not resource_file or not resource_file.exists():
            return None

        current_mtime = resource_file.stat().st_mtime
        cache_key = (ResourceType.GRAPH, f"{graph_id}_metadata")

        current_node_defs_fp = self._cache_facade.get_current_node_defs_fingerprint()
        current_layout_settings = self._cache_facade.current_layout_settings_snapshot()

        cached = self._cache_service.get(cache_key, current_mtime)
        if cached is not None and isinstance(cached, dict):
            cached_fp = str(cached.get("node_defs_fp") or "").strip()
            cached_layout_settings = cached.get("layout_settings")
            if cached_fp and cached_fp == current_node_defs_fp and cached_layout_settings == current_layout_settings:
                return cached
            # 旧缓存缺少指纹/布局设置或不匹配：清理并重新生成
            self._cache_service.clear(ResourceType.GRAPH, f"{graph_id}_metadata")

        raw_bytes = resource_file.read_bytes()
        content = raw_bytes.decode("utf-8")
        file_md5 = hashlib.md5(raw_bytes).hexdigest()

        metadata_obj = extract_metadata_from_code(content)
        metadata = {
            "graph_id": metadata_obj.graph_id or graph_id,
            "name": metadata_obj.graph_name or "",
            "graph_type": metadata_obj.graph_type or "server",
            "folder_path": metadata_obj.folder_path or "",
            "description": metadata_obj.description or "",
            "node_count": 0,
            "edge_count": 0,
            "modified_time": current_mtime,
            # 用于列表元数据缓存失效判定：避免“节点实现/布局语义变化”但图文件未变时，列表仍显示旧统计。
            "node_defs_fp": current_node_defs_fp,
            "layout_settings": current_layout_settings,
        }

        # 优先：若存在与当前图文件内容、节点定义指纹、布局设置兼容的持久化缓存，
        # 则直接使用缓存内的 nodes/edges 进行计数，确保与右侧属性面板口径一致，
        # 同时仍不触发解析与自动布局。
        cache_dir = get_graph_cache_dir(self._workspace_path)
        cache_file = cache_dir / f"{graph_id}.json"
        if cache_file.exists():
            cache_text = cache_file.read_text(encoding="utf-8")
            if cache_text.strip():
                payload = json.loads(cache_text)
                if isinstance(payload, dict):
                    cached_hash = payload.get("file_hash")
                    cached_fp = payload.get("node_defs_fp")
                    cached_result_data = payload.get("result_data")
                    if (
                        isinstance(cached_hash, str)
                        and isinstance(cached_fp, str)
                        and isinstance(cached_result_data, dict)
                        and cached_hash == file_md5
                        and cached_fp == current_node_defs_fp
                        and self._cache_facade.is_persistent_layout_settings_compatible(cached_result_data)
                    ):
                        cached_graph_data = cached_result_data.get("data")
                        if isinstance(cached_graph_data, dict):
                            cached_nodes = cached_graph_data.get("nodes")
                            cached_edges = cached_graph_data.get("edges")
                            if isinstance(cached_nodes, list) and isinstance(cached_edges, list):
                                metadata["node_count"] = len(cached_nodes)
                                metadata["edge_count"] = len(cached_edges)
                                self._cache_service.add(cache_key, metadata, current_mtime)
                                return metadata

        import re

        lines = content.split("\n")
        node_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if stripped.startswith("from ") or stripped.startswith("import "):
                continue
            if stripped.startswith("with ") or stripped.startswith("class ") or stripped.startswith("def "):
                continue

            if "=" in stripped and "(" in stripped and ")" in stripped:
                if " == " in stripped or " != " in stripped or " <= " in stripped or " >= " in stripped:
                    continue
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    right_side = parts[1].strip()
                    if re.match(r"^[\w\u4e00-\u9fa5]+\s*\(", right_side):
                        node_count += 1
                        continue

            if "(" in stripped and ")" in stripped:
                if re.match(r"^[\w\u4e00-\u9fa5]+\s*\(", stripped):
                    node_count += 1

        metadata["node_count"] = max(0, node_count)

        edge_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if "=" in stripped and "(" in stripped:
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    right_side = parts[1].strip()
                    param_refs = re.findall(r"=\s*([\w\u4e00-\u9fa5]+\d*)", right_side)
                    edge_count += len(param_refs)

        metadata["edge_count"] = max(0, edge_count)
        self._cache_service.add(cache_key, metadata, current_mtime)
        return metadata

    def _resolve_graph_file_path(self, graph_id: str) -> Optional[Path]:
        resource_file = self._index_state.get_file_path(ResourceType.GRAPH, graph_id)
        if resource_file is None:
            resource_file = self._file_ops.get_resource_file_path(
                ResourceType.GRAPH,
                graph_id,
                self._index_state.filename_cache,
                extension=".py",
            )
            if resource_file and resource_file.exists():
                self._index_state.set_file_path(ResourceType.GRAPH, graph_id, resource_file)
        return resource_file


