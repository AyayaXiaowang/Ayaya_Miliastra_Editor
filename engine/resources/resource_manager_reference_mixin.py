from __future__ import annotations

from pathlib import Path
from typing import List

from engine.configs.resource_types import ResourceType


class ResourceManagerReferenceMixin:
    """ResourceManager 的引用索引与模板“同文件多 ID”清理逻辑。"""

    def add_reference(self, resource_id: str, package_id: str) -> None:
        """添加资源引用

        Args:
            resource_id: 资源ID
            package_id: 存档ID
        """
        self._references.add_reference(resource_id, package_id)

    def remove_reference(self, resource_id: str, package_id: str) -> None:
        """移除资源引用

        Args:
            resource_id: 资源ID
            package_id: 存档ID
        """
        self._references.remove_reference(resource_id, package_id)

    def get_resource_references(self, resource_id: str) -> List[str]:
        """查询哪些存档引用了此资源

        Args:
            resource_id: 资源ID

        Returns:
            引用此资源的存档ID列表
        """
        return self._references.get_references(resource_id)

    def is_resource_referenced(self, resource_id: str) -> bool:
        """检查资源是否被引用

        Args:
            resource_id: 资源ID

        Returns:
            是否被引用
        """
        return self._references.is_referenced(resource_id)

    def _cleanup_stale_template_ids_for_file(
        self,
        current_template_id: str,
        resource_file: Path,
    ) -> None:
        """清理指向同一模板文件的旧模板 ID。

        规则：
        - 仅针对 `ResourceType.TEMPLATE`。
        - 找出所有 `resource_index[TEMPLATE]` 中指向同一 `resource_file` 且 ID != 当前 ID 的条目；
        - 这些条目视为“同文件多 ID”的脏数据，应直接清理，避免后续解析/引用分叉。
        """
        template_bucket = self.resource_index.get(ResourceType.TEMPLATE)
        if not template_bucket:
            return

        stale_ids: List[str] = []
        for template_id, path in template_bucket.items():
            if template_id == current_template_id:
                continue
            if path == resource_file:
                stale_ids.append(template_id)

        if not stale_ids:
            return

        name_mapping = self.name_to_id_index.get(ResourceType.TEMPLATE)

        for stale_id in stale_ids:
            # 1. 从资源路径索引与文件名缓存中移除
            self._state.remove_file_path(ResourceType.TEMPLATE, stale_id)
            self._state.remove_filename(ResourceType.TEMPLATE, stale_id)

            # 2. 从名称映射中移除所有指向该 ID 的条目
            if name_mapping is not None:
                keys_to_delete: List[str] = []
                for key, value in name_mapping.items():
                    if value == stale_id:
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    del name_mapping[key]

            # 3. 清除对应的内存缓存
            self.clear_cache(ResourceType.TEMPLATE, stale_id)



