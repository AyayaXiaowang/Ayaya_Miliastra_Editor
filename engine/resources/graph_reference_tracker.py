"""节点图引用追踪器 - 追踪节点图被哪些实体使用"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING
from engine.configs.resource_types import ResourceType
from engine.resources.graph_reference_service import build_graph_to_references_index

if TYPE_CHECKING:
    from engine.resources.resource_manager import ResourceManager
    from engine.resources.package_index_manager import PackageIndexManager


class GraphReferenceTracker:
    """节点图引用追踪器"""
    
    def __init__(self, resource_manager, package_index_manager):
        """初始化引用追踪器
        
        Args:
            resource_manager: 资源管理器
            package_index_manager: 存档索引管理器
        """
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self._composite_usage_cache: Dict[str, List[Dict[str, Any]]] = {}

        # 引用缓存：避免在“节点图库列表刷新”时为每张图重复全量扫描全部存档/模板/实例。
        # 缓存以资源库指纹为失效条件：指纹未变时，复用反向索引（graph_id -> references）。
        self._reference_cache_fingerprint: str = ""
        self._graph_references_cache: Dict[str, List[Tuple[str, str, str, str]]] = {}

    def invalidate_reference_cache(self) -> None:
        """主动失效引用缓存（在写回模板/实例/索引等会影响引用关系的操作后调用）。"""
        self._reference_cache_fingerprint = ""
        self._graph_references_cache.clear()

    def _ensure_reference_cache(self) -> None:
        """确保 graph_id -> references 的反向索引缓存可用。"""
        current_fingerprint = self.resource_manager.get_resource_library_fingerprint()
        if self._reference_cache_fingerprint == current_fingerprint and self._graph_references_cache:
            return
        self._rebuild_reference_cache(current_fingerprint)

    def _rebuild_reference_cache(self, fingerprint: str) -> None:
        """重建引用缓存（一次性扫描全部存档/模板/实例）。"""
        # 引用追踪只依赖资源 ID 归属，不需要刷新派生展示字段（resource_names）。
        # 关闭该刷新可以显著降低启动阶段的 I/O 与避免触发节点图解析链路。
        graph_to_refs = build_graph_to_references_index(
            package_index_manager=self.package_index_manager,
            resource_manager=self.resource_manager,
            include_combat_presets=True,
            include_skill_ugc_indirect=False,
            refresh_resource_names=False,
        )
        self._graph_references_cache = graph_to_refs
        self._reference_cache_fingerprint = fingerprint
    
    def find_references(self, graph_id: str) -> List[Tuple[str, str, str, str]]:
        """查找引用了指定节点图的所有实体
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            引用列表，格式为 [(entity_type, entity_id, entity_name, package_id), ...]
            entity_type: "template" | "instance" | "level_entity"
        """
        if not isinstance(graph_id, str) or not graph_id:
            return []
        self._ensure_reference_cache()
        return list(self._graph_references_cache.get(graph_id, []))
    
    def find_packages_using_graph(self, graph_id: str) -> List[str]:
        """查找使用了指定节点图的所有存档
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            存档ID列表
        """
        references = self.find_references(graph_id)
        package_ids = list(set(ref[3] for ref in references))
        return package_ids
    
    def get_reference_count(self, graph_id: str) -> int:
        """获取节点图的引用计数
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            引用次数
        """
        if not isinstance(graph_id, str) or not graph_id:
            return 0
        # 注意：只要返回“数量”，就不应为了防止外部修改而拷贝整个引用列表；
        # 在引用量较多的情况下，复制列表会在 UI 列表刷新/单击预览时放大卡顿。
        self._ensure_reference_cache()
        return len(self._graph_references_cache.get(graph_id, []))
    
    def update_reference(self, entity_type: str, entity_id: str, 
                        old_graph_id: str, new_graph_id: str) -> bool:
        """更新实体中的节点图引用
        
        Args:
            entity_type: 实体类型 ("template" | "instance" | "level_entity")
            entity_id: 实体ID
            old_graph_id: 旧的节点图ID
            new_graph_id: 新的节点图ID
        
        Returns:
            是否更新成功
        """
        # 根据实体类型加载数据
        if entity_type == "template":
            data = self.resource_manager.load_resource(
                ResourceType.TEMPLATE,
                entity_id
            )
        elif entity_type == "instance":
            data = self.resource_manager.load_resource(
                ResourceType.INSTANCE,
                entity_id
            )
        else:
            return False
        
        if not data:
            return False
        
        # 更新引用
        modified = False
        
        if entity_type == "template":
            default_graphs = data.get("default_graphs", [])
            if old_graph_id in default_graphs:
                idx = default_graphs.index(old_graph_id)
                default_graphs[idx] = new_graph_id
                modified = True
        elif entity_type == "instance":
            additional_graphs = data.get("additional_graphs", [])
            if old_graph_id in additional_graphs:
                idx = additional_graphs.index(old_graph_id)
                additional_graphs[idx] = new_graph_id
                modified = True
        
        # 保存修改
        if modified:
            if entity_type == "template":
                self.resource_manager.save_resource(
                    ResourceType.TEMPLATE,
                    entity_id,
                    data
                )
            elif entity_type == "instance":
                self.resource_manager.save_resource(
                    ResourceType.INSTANCE,
                    entity_id,
                    data
                )
            # 引用关系变更：失效引用缓存
            self.invalidate_reference_cache()
        
        return modified

    def find_graphs_using_composite(self, composite_node_name: str) -> List[Dict[str, Any]]:
        """列出使用指定复合节点的所有节点图（包含节点/连线信息）。"""
        key = composite_node_name.strip()
        if not key:
            return []
        if key in self._composite_usage_cache:
            return self._composite_usage_cache[key]

        usages: List[Dict[str, Any]] = []
        target_category = f"复合节点/{key}"
        graph_ids = self.resource_manager.list_resources(ResourceType.GRAPH)

        for graph_id in graph_ids:
            graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
            if not graph_data:
                continue
            payload = graph_data.get("data", graph_data)
            nodes = payload.get("nodes", [])
            node_ids = [
                node.get("id")
                for node in nodes
                if node.get("category") == target_category and node.get("id")
            ]
            if not node_ids:
                continue
            usages.append(
                {
                    "graph_id": graph_id,
                    "graph_name": graph_data.get("name", graph_id),
                    "node_ids": node_ids,
                    "edges": payload.get("edges", []),
                }
            )

        self._composite_usage_cache[key] = usages
        return usages

    def clear_composite_usage_cache(self, composite_node_name: Optional[str] = None) -> None:
        """清空复合节点引用缓存。"""
        if composite_node_name:
            self._composite_usage_cache.pop(composite_node_name, None)
        else:
            self._composite_usage_cache.clear()

