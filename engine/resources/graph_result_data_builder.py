"""节点图 result_data 组装器（单一真源）。

职责：
- 将 GraphModel 序列化为标准 `load_resource(ResourceType.GRAPH, ...)` 返回结构（result_data）。
- 统一补齐缓存相关 metadata：node_defs_fp / fingerprints / layout_settings。
- 统一 folder_path 的标准化与从文件路径推断（用于 UI 基本信息展示与历史缓存自愈）。

说明：
- 该模块只负责“结构组装”，不负责写盘/写缓存；写入由 GraphCacheFacade / PersistentGraphCacheManager 负责。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from engine.graph.models.graph_model import GraphModel

from .graph_cache_facade import GraphCacheFacade
from .graph_fingerprints_service import GraphFingerprintsService
from .resource_file_ops import ResourceFileOps


@dataclass(frozen=True, slots=True)
class GraphResultDataBuilder:
    """GraphModel -> result_data 的统一组装器。"""

    file_ops: ResourceFileOps
    cache_facade: GraphCacheFacade
    fingerprints_service: GraphFingerprintsService

    def build_result_data(
        self,
        *,
        graph_id: str,
        graph_model: GraphModel,
        parsed_metadata: Optional[dict] = None,
        resource_file: Optional[Path] = None,
        base_result_metadata: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """构建标准 result_data。

        Args:
            graph_id: 资源索引层的节点图 ID（通常等于文件名对应的 ID）。
            graph_model: 已完成布局/同步的 GraphModel。
            parsed_metadata: 可选的解析器元数据（GraphCodeParser.parse_file 返回的 metadata dict）。
            resource_file: 可选的节点图源文件路径，用于 folder_path 推断与标准化。
            base_result_metadata: 可选的 result_data["metadata"] 基础字典（将被拷贝并与统一字段合并）。
        """
        graph_data = graph_model.serialize()
        metadata_dict = dict(parsed_metadata or {})

        # ===== 顶层字段（对齐 load_graph 返回结构） =====
        result_graph_id = metadata_dict.get("graph_id", graph_id)
        result_name = metadata_dict.get("graph_name", graph_data.get("graph_name", ""))
        result_graph_type = metadata_dict.get(
            "graph_type",
            (graph_data.get("metadata") or {}).get("graph_type", "server"),
        )
        result_folder_path = metadata_dict.get("folder_path", "")
        result_description = metadata_dict.get("description", graph_data.get("description", ""))

        # ===== 缓存相关 metadata（result_data["metadata"]） =====
        result_metadata: Dict[str, Any] = dict(base_result_metadata or {})
        result_metadata["node_defs_fp"] = self.cache_facade.get_current_node_defs_fingerprint()

        fingerprints = self.fingerprints_service.build_fingerprints_from_graph_model(graph_model)
        if fingerprints:
            result_metadata["fingerprints"] = fingerprints

        result_metadata["layout_settings"] = self.cache_facade.current_layout_settings_snapshot()

        result_data: Dict[str, Any] = {
            "graph_id": result_graph_id,
            "name": result_name,
            "graph_type": result_graph_type,
            "folder_path": result_folder_path,
            "description": result_description,
            "data": graph_data,
            "metadata": result_metadata,
        }

        if resource_file is not None:
            self.ensure_folder_path_from_file(result_data, resource_file=resource_file)

        return result_data

    def ensure_folder_path_from_file(self, result_data: dict, *, resource_file: Path) -> bool:
        """确保 result_data 内的 folder_path 已被填充/标准化。

        设计动机：
        - 现有节点图示例多数只在 docstring 中写 graph_id/name/type/description，不再重复写 folder_path；
        - 但 UI 的“基本信息/文件夹”需要稳定展示文件夹路径；
        - 同时需要兼容缓存命中：旧缓存可能存了空 folder_path，不能要求用户手动清缓存。
        """
        if not isinstance(result_data, dict):
            return False

        changed = False

        folder_value = result_data.get("folder_path")
        folder_text = folder_value.strip() if isinstance(folder_value, str) else ""
        if folder_text:
            sanitized_folder = self.file_ops.sanitize_folder_path(folder_text)
            if sanitized_folder != folder_text:
                result_data["folder_path"] = sanitized_folder
                folder_text = sanitized_folder
                changed = True
        else:
            _, inferred_folder_path = self.file_ops.infer_graph_type_and_folder_path(resource_file)
            if inferred_folder_path:
                result_data["folder_path"] = inferred_folder_path
                folder_text = inferred_folder_path
                changed = True

        # 将 folder_path 镜像写入 graph_data.metadata：下游很多链路只拿到 result_data["data"]
        # （GraphModel 序列化），因此需要在该处保证 GraphModel.metadata 可见 folder_path。
        if folder_text:
            data_obj = result_data.get("data")
            if isinstance(data_obj, dict):
                meta_obj = data_obj.get("metadata")
                if not isinstance(meta_obj, dict):
                    meta_obj = {}
                    data_obj["metadata"] = meta_obj
                    changed = True
                if meta_obj.get("folder_path") != folder_text:
                    meta_obj["folder_path"] = folder_text
                    changed = True

        return changed


