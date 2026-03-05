from __future__ import annotations

from typing import Dict, Set


class _GlobalCopyManagerQueryMixin:
    def get_block_copy_mapping(self, block_id: str) -> Dict[str, str]:
        """获取指定块的副本映射：原始ID -> 副本ID"""
        mapping: Dict[str, str] = {}
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                mapping[original_id] = copy_id
        return mapping

    def get_block_owned_nodes(self, block_id: str) -> Set[str]:
        """获取指定块"拥有"的数据节点（原始节点，非副本）"""
        owned: Set[str] = set()
        for original_id, plan in self.copy_plans.items():
            if plan.owner_block_id == block_id:
                owned.add(original_id)

        # 加上只被这个块使用的节点
        dependency = self.block_dependencies.get(block_id)
        if dependency:
            for data_id in dependency.full_data_closure:
                if data_id not in self.copy_plans:
                    owned.add(data_id)

        return owned

    def get_block_data_nodes(self, block_id: str) -> Set[str]:
        """获取指定块应该放置的所有数据节点ID

        包括：拥有的原始节点 + 该块的副本节点
        """
        result: Set[str] = set()

        # 该块拥有的原始节点
        result.update(self.get_block_owned_nodes(block_id))

        # 该块的副本节点
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                result.add(copy_id)

        return result

