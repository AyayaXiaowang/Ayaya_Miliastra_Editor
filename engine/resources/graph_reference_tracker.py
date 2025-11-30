"""节点图引用追踪器 - 追踪节点图被哪些实体使用"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING
from engine.configs.resource_types import ResourceType

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
    
    def find_references(self, graph_id: str) -> List[Tuple[str, str, str, str]]:
        """查找引用了指定节点图的所有实体
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            引用列表，格式为 [(entity_type, entity_id, entity_name, package_id), ...]
            entity_type: "template" | "instance" | "level_entity"
        """
        references = []
        
        # 获取所有存档
        packages = self.package_index_manager.list_packages()
        
        for package_info in packages:
            package_id = package_info["package_id"]
            package_index = self.package_index_manager.load_package_index(package_id)
            
            if not package_index:
                continue
            
            # 检查模板中的引用
            for template_id in package_index.resources.templates:
                template_data = self.resource_manager.load_resource(
                    ResourceType.TEMPLATE,
                    template_id
                )
                if template_data:
                    # default_graphs 是 graph_id 列表
                    default_graphs = template_data.get("default_graphs", [])
                    if graph_id in default_graphs:
                        references.append((
                            "template",
                            template_id,
                            template_data.get("name", "未命名"),
                            package_id
                        ))
            
            # 检查实例中的引用
            for instance_id in package_index.resources.instances:
                instance_data = self.resource_manager.load_resource(
                    ResourceType.INSTANCE,
                    instance_id
                )
                if instance_data:
                    # additional_graphs 是 graph_id 列表
                    additional_graphs = instance_data.get("additional_graphs", [])
                    if graph_id in additional_graphs:
                        references.append((
                            "instance",
                            instance_id,
                            instance_data.get("name", "未命名"),
                            package_id
                        ))
            
            # 检查关卡实体中的引用
            if package_index.level_entity_id:
                level_entity_data = self.resource_manager.load_resource(
                    ResourceType.INSTANCE,
                    package_index.level_entity_id
                )
                if level_entity_data:
                    # additional_graphs 是 graph_id 列表（关卡实体作为特殊实例存储）
                    additional_graphs = level_entity_data.get("additional_graphs", [])
                    if graph_id in additional_graphs:
                        references.append((
                            "level_entity",
                            package_id,
                            "关卡实体",
                            package_id
                        ))
        
        return references
    
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
        return len(self.find_references(graph_id))
    
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

