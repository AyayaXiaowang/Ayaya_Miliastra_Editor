from __future__ import annotations

from typing import Tuple

from engine.resources.resource_manager import ResourceType


class PackageLibraryResourceTextMixin:
    """资源展示名与 extra info 缓存（避免列表/树频繁反复读取）。"""

    def _display_name(self, resource_type: ResourceType, resource_id: str) -> str:
        """获取资源的显示名（优先中文名，回退 ID）。"""
        cache_key = (resource_type, resource_id)
        cached = self._resource_name_cache.get(cache_key)
        if cached:
            return cached
        meta = self.rm.get_resource_metadata(resource_type, resource_id)
        if meta and meta.get("name"):
            name = meta["name"]
        else:
            name = resource_id
        self._resource_name_cache[cache_key] = name
        return name

    def _resolve_graph_display_name(self, graph_id: str) -> str:
        cached = self._graph_display_name_cache.get(graph_id)
        if cached:
            return cached
        metadata = self.rm.load_graph_metadata(graph_id) or {}
        name = metadata.get("name") or graph_id
        self._graph_display_name_cache[graph_id] = name
        return name

    def _get_resource_extra_info(
        self,
        resource_type: ResourceType,
        resource_id: str,
    ) -> Tuple[str, str]:
        """获取资源的 GUID 与挂载节点图信息（名称汇总）。

        返回:
            (guid_text, graphs_text)
        """
        cache_key = (resource_type, resource_id)
        cached = self._resource_extra_cache.get(cache_key)
        if cached is not None:
            return cached

        guid_text = ""
        graphs_text = ""

        meta = self.rm.get_resource_metadata(resource_type, resource_id)
        if meta:
            raw_guid = meta.get("guid")
            if raw_guid:
                guid_text = str(raw_guid)

            raw_graph_ids = meta.get("graph_ids") or []
            if isinstance(raw_graph_ids, list) and raw_graph_ids:
                graph_names: list[str] = []
                for graph_id in raw_graph_ids:
                    if not isinstance(graph_id, str):
                        continue
                    graph_name = self._resolve_graph_display_name(graph_id)
                    if graph_name == graph_id:
                        graph_names.append(graph_name)
                    else:
                        graph_names.append(f"{graph_name} ({graph_id})")
                graphs_text = ", ".join(graph_names)

        result = (guid_text, graphs_text)
        self._resource_extra_cache[cache_key] = result
        return result

    def _clear_display_name_cache(self) -> None:
        self._resource_name_cache.clear()
        self._graph_display_name_cache.clear()
        self._resource_extra_cache.clear()

