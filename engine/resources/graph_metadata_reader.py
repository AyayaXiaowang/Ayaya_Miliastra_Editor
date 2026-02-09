"""节点图轻量元数据读取器（不执行节点图代码）。

职责：
- 从 `.py` 源码 docstring/注释中提取轻量元数据（graph_id/name/type/folder/description）
- 为列表展示统计 node_count/edge_count：
  - 优先复用持久化图缓存（命中且兼容时）
  - 若无可用缓存，则不做任何估算（保持为空，由打开节点图时生成缓存后再展示）
"""

from __future__ import annotations

import ast
import io
from pathlib import Path
from typing import Optional
import tokenize

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import GraphMetadata, extract_metadata_from_docstring
from engine.utils.source_text import read_source_text

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
                inferred_graph_type, inferred_folder_path = self._file_ops.infer_graph_type_and_folder_path(resource_file)

                # folder_path/graph_type 以文件路径为准：避免“移动文件后缓存/Docstring 滞后”。
                if inferred_graph_type:
                    new_cached = dict(cached)
                    if str(new_cached.get("graph_type") or "").strip() != inferred_graph_type:
                        new_cached["graph_type"] = inferred_graph_type
                    if str(new_cached.get("folder_path") or "") != inferred_folder_path:
                        new_cached["folder_path"] = inferred_folder_path
                    if new_cached != cached:
                        self._cache_service.add(cache_key, new_cached, current_mtime)
                    return new_cached

                folder_value = cached.get("folder_path")
                folder_text = folder_value.strip() if isinstance(folder_value, str) else ""
                if folder_text:
                    sanitized_folder = self._file_ops.sanitize_folder_path(folder_text)
                    if sanitized_folder != folder_text:
                        cached = dict(cached)
                        cached["folder_path"] = sanitized_folder
                        self._cache_service.add(cache_key, cached, current_mtime)
                    return cached

                return cached
            # 旧缓存缺少指纹/布局设置或不匹配：清理并重新生成
            self._cache_service.clear(ResourceType.GRAPH, f"{graph_id}_metadata")

        source = read_source_text(resource_file)
        content = source.text
        file_md5 = source.md5

        metadata_obj = self._extract_graph_metadata_from_source(content)
        inferred_graph_type, inferred_folder_path = self._file_ops.infer_graph_type_and_folder_path(resource_file)
        graph_type = inferred_graph_type or str(metadata_obj.graph_type or "").strip() or "server"
        folder_path = inferred_folder_path if inferred_graph_type else str(metadata_obj.folder_path or "").strip()
        folder_path = self._file_ops.sanitize_folder_path(folder_path) if folder_path else ""
        metadata = {
            "graph_id": metadata_obj.graph_id or graph_id,
            "name": metadata_obj.graph_name or "",
            "graph_type": graph_type,
            "folder_path": folder_path,
            "description": metadata_obj.description or "",
            # 重要：列表页不主动“计算/估算”节点数与连线数。
            # - 仅当命中持久化 graph_cache 且校验兼容时，才填充真实统计；
            # - 否则保持为 None（UI 应展示为 "-" 或空），统计只能在打开节点图时生成缓存。
            "node_count": None,
            "edge_count": None,
            "modified_time": current_mtime,
            # 用于列表元数据缓存失效判定：避免“节点实现/布局语义变化”但图文件未变时，列表仍显示旧统计。
            "node_defs_fp": current_node_defs_fp,
            "layout_settings": current_layout_settings,
        }

        # 优先：若存在与当前图文件内容、节点定义指纹、布局设置兼容的持久化缓存，
        # 则直接使用缓存内的 nodes/edges 进行计数，确保与右侧属性面板口径一致，
        # 同时仍不触发解析与自动布局。
        payload = self._cache_facade.read_persistent_graph_cache_payload(graph_id)
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
        self._cache_service.add(cache_key, metadata, current_mtime)
        return metadata

    @staticmethod
    def _extract_module_docstring(source_text: str) -> str:
        """从源码中提取模块 docstring（无需构建 AST）。

        说明：
        - 仅用于列表元数据提取：我们只关心首个语句是否为字符串字面量；
        - 使用 tokenize 快速读取首个 token，避免对大图文件做 ast.parse() 造成明显卡顿。
        """
        readline = io.StringIO(source_text).readline
        for tok in tokenize.generate_tokens(readline):
            tok_type = tok.type
            if tok_type in {
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.COMMENT,
                tokenize.ENCODING,
            }:
                continue
            if tok_type == tokenize.STRING:
                value = ast.literal_eval(tok.string)
                if isinstance(value, str):
                    return value
                return ""
            return ""
        return ""

    def _extract_graph_metadata_from_source(self, source_text: str) -> GraphMetadata:
        docstring = self._extract_module_docstring(source_text)
        if docstring:
            return extract_metadata_from_docstring(docstring)
        return GraphMetadata()

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


