from __future__ import annotations

from typing import List, Optional

from engine.configs.resource_types import ResourceType


class ResourceManagerMetadataMixin:
    """ResourceManager 的 UI 元数据构建与搜索。"""

    def get_resource_metadata(self, resource_type: ResourceType, resource_id: str) -> Optional[dict]:
        """获取用于 UI 展示与搜索的资源元数据（统一格式）。

        说明：
        - 对多数资源类型，该方法会读取资源 payload（节点图会触发解析与布局，因此不适合在“列表页”高频调用）。
        - 节点图的列表展示应优先走 `load_graph_metadata()` 的轻量路径。
        """
        payload = self.load_resource(resource_type, resource_id)
        if not payload:
            return None
        return self._metadata_service.build_resource_metadata(resource_type, resource_id, payload)

    def search_resources(self, keyword: str, resource_type: Optional[ResourceType] = None) -> List[dict]:
        """搜索资源（按名称或描述）

        Args:
            keyword: 搜索关键词
            resource_type: 可选的资源类型过滤

        Returns:
            匹配的资源元数据列表
        """
        results = []
        keyword_lower = keyword.lower()

        resource_types = [resource_type] if resource_type else list(ResourceType)

        for rtype in resource_types:
            resource_ids = self.list_resources(rtype)
            for resource_id in resource_ids:
                metadata = self.get_resource_metadata(rtype, resource_id)
                if metadata:
                    if (
                        keyword_lower in metadata["name"].lower()
                        or keyword_lower in metadata.get("description", "").lower()
                        or keyword_lower in resource_id.lower()
                    ):
                        results.append(metadata)

        return results



