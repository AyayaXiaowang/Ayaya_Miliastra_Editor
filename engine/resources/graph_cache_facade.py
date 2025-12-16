"""节点图缓存门面（内存 + 持久化）。

职责：
- 进程内缓存（ResourceCacheService）读写与失效策略（含 node_defs_fp）。
- 节点定义/解析器指纹（node_defs_fp）短 TTL 缓存，避免 UI 高频刷新卡顿。
- 布局设置快照与持久化缓存兼容性判断（避免“切换设置后仍命中旧布局缓存”）。
- UI 侧增量更新持久化缓存（delta 合并、指纹重算、写盘与同步内存）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from engine.configs.resource_types import ResourceType
from engine.configs.settings import settings
from engine.resources.persistent_graph_cache_manager import PersistentGraphCacheManager
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from engine.utils.logging.logger import log_info

from .graph_fingerprints_service import GraphFingerprintsService
from .resource_cache_service import ResourceCacheService


class GraphCacheFacade:
    """节点图缓存门面：统一封装内存缓存与磁盘持久化缓存的读写/失效。"""

    def __init__(
        self,
        workspace_path: Path,
        *,
        cache_service: ResourceCacheService,
        persistent_graph_cache_manager: PersistentGraphCacheManager,
        fingerprints_service: GraphFingerprintsService,
        node_defs_fp_cache_ttl_seconds: float = 1.0,
    ) -> None:
        self._workspace_path = workspace_path
        self._cache_service = cache_service
        self._persistent_graph_cache_manager = persistent_graph_cache_manager
        self._fingerprints_service = fingerprints_service

        # ===== 节点定义/解析器指纹缓存（避免频繁全目录扫描导致 UI 卡顿） =====
        self._cached_node_defs_fp: str = ""
        self._cached_node_defs_fp_at: float = 0.0
        self._node_defs_fp_cache_ttl_seconds: float = float(node_defs_fp_cache_ttl_seconds)

    # ===== node_defs_fp（短 TTL） =====

    def get_current_node_defs_fingerprint(self) -> str:
        """获取当前节点定义/解析器指纹（带短 TTL 缓存）。

        注意：该方法可能被高频调用（节点图库刷新/任务清单刷新/文件监控触发的增量刷新等），
        因此必须避免每次都全量扫描目录。
        """
        import time

        now = time.monotonic()
        if self._cached_node_defs_fp and (now - self._cached_node_defs_fp_at) < self._node_defs_fp_cache_ttl_seconds:
            return self._cached_node_defs_fp

        new_fingerprint = compute_node_defs_fingerprint(self._workspace_path)
        # 若指纹发生变化，清理图相关的内存缓存，确保后续读取会触发重新解析
        if self._cached_node_defs_fp and new_fingerprint != self._cached_node_defs_fp:
            self._cache_service.clear(ResourceType.GRAPH)

        self._cached_node_defs_fp = new_fingerprint
        self._cached_node_defs_fp_at = now
        return new_fingerprint

    # ===== 内存缓存（ResourceCacheService） =====

    def get_graph_from_memory_cache(self, graph_id: str, current_mtime: float) -> Optional[dict]:
        cache_key = (ResourceType.GRAPH, graph_id)
        cached_value = self._cache_service.get(cache_key, current_mtime)
        if cached_value is None:
            return None

        # 内存缓存默认仅依赖图文件 mtime；但当节点库/解析器实现变更时（node_defs_fp 变化），
        # 需要强制失效以避免 UI 继续显示旧的解析结果（例如事件节点标题/端口规则更新后仍沿用旧模型）。
        current_node_defs_fp = self.get_current_node_defs_fingerprint()
        cached_meta = cached_value.get("metadata") if isinstance(cached_value, dict) else None
        cached_fp = ""
        if isinstance(cached_meta, dict):
            cached_fp = str(cached_meta.get("node_defs_fp") or "").strip()

        if cached_fp and cached_fp == current_node_defs_fp:
            return cached_value

        # 缓存缺少 fp 或 fp 不一致：清理并回退到持久化缓存/重解析路径
        self._cache_service.clear(ResourceType.GRAPH, graph_id)
        return None

    def store_graph_in_memory_cache(self, graph_id: str, result_data: dict, current_mtime: float) -> None:
        cache_key = (ResourceType.GRAPH, graph_id)
        self._cache_service.add(cache_key, result_data, current_mtime)

    # ===== 布局设置快照/兼容性 =====

    @staticmethod
    def current_layout_settings_snapshot() -> dict:
        """获取与布局结果相关的全局设置快照（跨块复制、紧凑排列、布局算法版本等）。"""
        return {
            "DATA_NODE_CROSS_BLOCK_COPY": bool(getattr(settings, "DATA_NODE_CROSS_BLOCK_COPY", True)),
            "LAYOUT_TIGHT_BLOCK_PACKING": bool(getattr(settings, "LAYOUT_TIGHT_BLOCK_PACKING", True)),
            "LAYOUT_COMPACT_DATA_Y_IN_BLOCK": bool(getattr(settings, "LAYOUT_COMPACT_DATA_Y_IN_BLOCK", True)),
            "LAYOUT_DATA_Y_COMPACT_PULL": float(getattr(settings, "LAYOUT_DATA_Y_COMPACT_PULL", 0.6)),
            "LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD": float(
                getattr(settings, "LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD", 200.0)
            ),
            # 布局算法版本号：用于在跨块复制/块归属等布局语义发生变更时主动失效旧缓存。
            "LAYOUT_ALGO_VERSION": int(getattr(settings, "LAYOUT_ALGO_VERSION", 1)),
        }

    def is_persistent_layout_settings_compatible(self, persisted_result_data: dict) -> bool:
        """检查持久化缓存中的布局设置快照是否与当前全局设置兼容。"""
        if not isinstance(persisted_result_data, dict):
            return False
        metadata = persisted_result_data.get("metadata")
        if not isinstance(metadata, dict):
            return False
        cached_settings = metadata.get("layout_settings")
        if not isinstance(cached_settings, dict):
            return False

        current_snapshot = self.current_layout_settings_snapshot()
        for key, current_value in current_snapshot.items():
            cached_value = cached_settings.get(key)
            if isinstance(current_value, bool):
                if not isinstance(cached_value, bool):
                    return False
                if cached_value != current_value:
                    return False
                continue
            # 对于非布尔字段（例如布局算法版本号），使用精确相等判定，缺失或不相等即视为不兼容
            if cached_value != current_value:
                return False
        return True

    # ===== 持久化缓存（PersistentGraphCacheManager） =====

    def load_persistent_graph_cache_if_compatible(self, graph_id: str, file_path: Path) -> Optional[Dict[str, Any]]:
        persisted = self._persistent_graph_cache_manager.load_persistent_graph_cache(graph_id, file_path)
        if not persisted:
            return None
        if not self.is_persistent_layout_settings_compatible(persisted):
            return None
        return persisted

    def save_persistent_graph_cache(self, graph_id: str, file_path: Path, result_data: Dict[str, Any]) -> None:
        self._persistent_graph_cache_manager.save_persistent_graph_cache(graph_id, file_path, result_data)

    # ===== 对外：更新图的持久化缓存（支持 delta 合并） =====

    def update_persistent_graph_cache(
        self,
        graph_id: str,
        file_path: Path,
        result_data: dict,
        *,
        delta: Optional[dict] = None,
        layout_changed: Optional[bool] = None,
    ) -> dict:
        """更新图的持久化缓存并同步内存缓存，返回最终写入的数据。"""
        log_info(
            "[缓存][图] 更新持久化缓存：{}（delta={}, layout_changed={}）",
            graph_id,
            "是" if delta else "否",
            layout_changed,
        )

        final_result: dict

        if delta:
            base = self._persistent_graph_cache_manager.read_persistent_graph_cache_result_data(graph_id)
            if base is None:
                base = result_data or {}
            final_result = dict(base)

            for result_key, result_value in (result_data or {}).items():
                final_result[result_key] = result_value

            delta_data = (delta or {}).get("data")
            if isinstance(delta_data, dict):
                final_data = dict(final_result.get("data") or {})

                if "nodes" in delta_data:
                    existing_nodes = final_data.get("nodes") or []
                    node_by_id = {
                        node_dict.get("id"): node_dict
                        for node_dict in existing_nodes
                        if isinstance(node_dict, dict) and "id" in node_dict
                    }

                    for delta_node_dict in (delta_data.get("nodes") or []):
                        node_id = delta_node_dict.get("id")
                        if not node_id:
                            continue
                        existing_node_dict = node_by_id.get(node_id, {})
                        merged_node_dict = dict(existing_node_dict)
                        for node_field, node_field_value in delta_node_dict.items():
                            merged_node_dict[node_field] = node_field_value
                        node_by_id[node_id] = merged_node_dict

                    seen_node_ids = set()
                    merged_nodes_list = []
                    for existing_node_dict in existing_nodes:
                        existing_node_id = existing_node_dict.get("id")
                        if existing_node_id in node_by_id and existing_node_id not in seen_node_ids:
                            merged_nodes_list.append(node_by_id[existing_node_id])
                            seen_node_ids.add(existing_node_id)

                    for remaining_node_id, remaining_node_dict in node_by_id.items():
                        if remaining_node_id not in seen_node_ids:
                            merged_nodes_list.append(remaining_node_dict)

                    final_data["nodes"] = merged_nodes_list

                for key in ("edges", "graph_variables"):
                    if key in delta_data:
                        final_data[key] = delta_data[key]

                final_result["data"] = final_data

            for field in ("name", "graph_type", "folder_path", "description"):
                if field in (delta or {}):
                    final_result[field] = delta[field]

            if "metadata" in (delta or {}):
                merged_metadata = dict(final_result.get("metadata") or {})
                merged_metadata.update(delta["metadata"])
                final_result["metadata"] = merged_metadata
        else:
            final_result = result_data

        need_recompute_fingerprints = bool(layout_changed if layout_changed is not None else True)

        if bool(getattr(settings, "FINGERPRINT_ENABLED", False)) and isinstance(final_result, dict):
            metadata_obj = final_result.get("metadata") or {}
            has_old_fingerprints = isinstance(metadata_obj.get("fingerprints"), dict)
            if not need_recompute_fingerprints and has_old_fingerprints:
                pass
            else:
                data_obj = final_result.get("data") or {}
                nodes_list = data_obj.get("nodes") or []
                fingerprints = self._fingerprints_service.build_fingerprints_from_serialized_nodes(
                    nodes_list, require_nodes=True
                )
                if fingerprints:
                    metadata_obj = final_result.get("metadata") or {}
                    metadata_obj["fingerprints"] = fingerprints
                    final_result["metadata"] = metadata_obj

        # 更新布局设置快照，确保持久化缓存与当前布局开关状态（如跨块复制）一致
        if isinstance(final_result, dict):
            metadata_obj2 = final_result.get("metadata") or {}
            metadata_obj2["layout_settings"] = self.current_layout_settings_snapshot()
            final_result["metadata"] = metadata_obj2

        self._persistent_graph_cache_manager.save_persistent_graph_cache(graph_id, file_path, final_result)
        current_mtime = file_path.stat().st_mtime
        self.store_graph_in_memory_cache(graph_id, final_result, current_mtime)
        return final_result


