"""复合节点管理器 - 管理全局复合节点库（函数格式）"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
import sys
import subprocess

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig, MappedPort
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.composite_node_loader import CompositeNodeLoader
from engine.nodes.composite_folder_manager import CompositeFolderManager
from engine.nodes.composite_virtual_pin_manager import CompositeVirtualPinManager
from engine.nodes.node_registry import get_node_registry
from engine.utils.logging.logger import log_info, log_warn, log_error

if TYPE_CHECKING:
    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.graph_reference_tracker import GraphReferenceTracker
    from engine.resources.resource_manager import ResourceManager


class CompositeNodeManager:
    """复合节点管理器 - 负责复合节点的增删改查和持久化
    
    使用离散化存储：每个复合节点一个 .py 文件（函数代码格式）
    """
    
    def __init__(
        self,
        workspace_path: Path,
        verbose: bool = False,
        base_node_library: Optional[Dict[str, NodeDef]] = None,
        resource_manager: Optional["ResourceManager"] = None,
        package_index_manager: Optional["PackageIndexManager"] = None,
        reference_tracker: Optional["GraphReferenceTracker"] = None,
    ):
        """初始化复合节点管理器
        
        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
            verbose: 是否打印详细日志（默认False）
            base_node_library: 外部注入的基础节点库（避免循环依赖）
        """
        self.workspace_path = workspace_path
        self.composite_library_dir = workspace_path / "assets" / "资源库" / "复合节点库"
        self.verbose = verbose
        
        # 确保目录存在
        self.composite_library_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存中的复合节点库 {composite_id: CompositeNodeConfig}
        self.composite_nodes: Dict[str, CompositeNodeConfig] = {}
        
        # 索引：{composite_id: file_path}
        self.composite_index: Dict[str, Path] = {}
        
        # 初始化子模块
        self.loader = CompositeNodeLoader(
            workspace_path=workspace_path,
            composite_library_dir=self.composite_library_dir,
            verbose=verbose,
            base_node_library=base_node_library,
        )
        self.folder_manager = CompositeFolderManager(self.composite_library_dir)
        self.virtual_pin_manager = CompositeVirtualPinManager(self.composite_nodes)

        self._resource_manager: Optional["ResourceManager"] = resource_manager
        self._package_index_manager: Optional["PackageIndexManager"] = package_index_manager
        self._graph_reference_tracker: Optional["GraphReferenceTracker"] = reference_tracker
        
        # 加载现有的复合节点
        self._load_library()

    def _ensure_resource_manager(self) -> "ResourceManager":
        if self._resource_manager is None:
            from engine.resources.resource_manager import ResourceManager

            self._resource_manager = ResourceManager(self.workspace_path)
        return self._resource_manager

    def _ensure_package_index_manager(self) -> "PackageIndexManager":
        if self._package_index_manager is None:
            from engine.resources.package_index_manager import PackageIndexManager

            self._package_index_manager = PackageIndexManager(
                self.workspace_path,
                self._ensure_resource_manager(),
            )
        return self._package_index_manager

    def _ensure_graph_reference_tracker(self) -> "GraphReferenceTracker":
        if self._graph_reference_tracker is None:
            from engine.resources.graph_reference_tracker import GraphReferenceTracker

            self._graph_reference_tracker = GraphReferenceTracker(
                self._ensure_resource_manager(),
                self._ensure_package_index_manager(),
            )
        return self._graph_reference_tracker
    
    def _load_library(self) -> None:
        """从文件加载复合节点库（函数代码格式）"""
        # 扫描所有 .py 文件（包括子文件夹）
        py_files = list(self.composite_library_dir.glob("**/*.py"))
        
        # 扫描并收集所有文件夹
        self.folder_manager.scan_folders()
        
        # 加载复合节点
        for py_file in py_files:
            if py_file.name.startswith("composite_") and py_file.suffix == ".py":
                composite = self.loader.load_composite_from_file(py_file, load_subgraph=False)
                if composite:
                    self.composite_nodes[composite.composite_id] = composite
                    self.composite_index[composite.composite_id] = py_file
        
        if self.verbose:
            log_info(f"加载了 {len(self.composite_nodes)} 个复合节点，{len(self.folder_manager.folders)} 个文件夹")
        
        # 迁移旧的JSON文件（如果存在）
        old_json_file = self.composite_library_dir / "composite_nodes.json"
        if old_json_file.exists():
            migrated_composites = self.loader.migrate_from_json(old_json_file)
            for composite in migrated_composites:
                self.composite_nodes[composite.composite_id] = composite
                file_path = self.loader.get_file_save_path(composite)
                self.composite_index[composite.composite_id] = file_path
    
    
    def generate_unique_name(self, base_name: str = "新建复合节点") -> str:
        """生成唯一的复合节点名称
        
        Args:
            base_name: 基础名称（默认为"新建复合节点"）
            
        Returns:
            唯一的名称，格式如：新建复合节点1、新建复合节点2...
        """
        existing_names = {composite.node_name for composite in self.composite_nodes.values()}
        
        # 如果基础名称没有被使用，直接返回
        if base_name not in existing_names:
            return base_name
        
        # 否则添加数字后缀
        counter = 1
        while True:
            new_name = f"{base_name}{counter}"
            if new_name not in existing_names:
                return new_name
            counter += 1
    
    def create_composite_node(
        self, 
        node_name: str = None, 
        node_description: str = "",
        sub_graph: dict = None,
        virtual_pins: List[VirtualPinConfig] = None,
        folder_path: str = ""
    ) -> str:
        """创建新的复合节点
        
        Args:
            node_name: 节点名称（如果为None，则自动生成唯一名称）
            node_description: 节点描述
            sub_graph: 子图数据（标准节点图格式）
            virtual_pins: 虚拟引脚列表
            folder_path: 文件夹路径（空字符串表示根目录）
            
        Returns:
            composite_id: 新创建的复合节点ID
        """
        # 如果没有提供名称，自动生成
        if node_name is None:
            node_name = self.generate_unique_name()
        
        # 生成唯一ID（使用节点名称）
        sanitized_name = CompositeNodeLoader.sanitize_filename(node_name)
        composite_id = f"composite_{sanitized_name}"
        
        # 创建配置
        composite = CompositeNodeConfig(
            composite_id=composite_id,
            node_name=node_name,
            node_description=node_description,
            scope="server",  # 固定为server
            virtual_pins=virtual_pins or [],
            sub_graph=sub_graph or {"nodes": [], "edges": [], "graph_variables": []},
            folder_path=folder_path
        )
        
        # 添加到库中
        self.composite_nodes[composite_id] = composite
        
        # 保存为函数代码文件
        file_path = self.loader.save_composite_to_file(composite)
        self.composite_index[composite_id] = file_path
        
        log_info(f"创建复合节点: {node_name} (ID: {composite_id})")
        return composite_id
    
    def get_composite_node(self, composite_id: str) -> Optional[CompositeNodeConfig]:
        """获取复合节点
        
        Args:
            composite_id: 复合节点ID
            
        Returns:
            复合节点配置，如果不存在返回None
        """
        return self.composite_nodes.get(composite_id)
    
    def analyze_composite_update_impact(self, composite_id: str, new_composite: CompositeNodeConfig) -> dict:
        """分析复合节点更新的影响
        
        检测：
        1. 引脚是否有删除或类型变更
        2. 哪些节点图使用了这个复合节点
        3. 哪些连线会受到影响
        
        Args:
            composite_id: 复合节点ID
            new_composite: 新的复合节点配置
            
        Returns:
            影响分析结果字典：
            {
                "has_impact": bool,  # 是否有影响
                "removed_pins": List[str],  # 被删除的引脚名称列表
                "changed_pins": List[str],  # 类型变更的引脚名称列表
                "affected_graphs": List[dict],  # 受影响的节点图列表
                "total_affected_connections": int  # 受影响的连线总数
            }
        """
        if composite_id not in self.composite_nodes:
            return {"has_impact": False, "error": "复合节点不存在"}
        
        old_composite = self.composite_nodes[composite_id]
        
        # 1. 检测引脚变化
        old_pins = {pin.pin_name: pin for pin in old_composite.virtual_pins}
        new_pins = {pin.pin_name: pin for pin in new_composite.virtual_pins}
        
        removed_pins = []
        changed_pins = []
        
        for pin_name, old_pin in old_pins.items():
            if pin_name not in new_pins:
                # 引脚被删除
                removed_pins.append(pin_name)
            else:
                # 检查引脚类型是否改变
                new_pin = new_pins[pin_name]
                if (old_pin.is_flow != new_pin.is_flow or 
                    old_pin.is_input != new_pin.is_input or
                    old_pin.pin_type != new_pin.pin_type):
                    changed_pins.append(pin_name)
        
        # 如果没有删除或变更，直接返回
        if not removed_pins and not changed_pins:
            return {
                "has_impact": False,
                "removed_pins": [],
                "changed_pins": [],
                "affected_graphs": [],
                "total_affected_connections": 0
            }
        
        tracker = self._ensure_graph_reference_tracker()
        affected_graphs = []
        composite_usages = tracker.find_graphs_using_composite(new_composite.node_name)

        for usage in composite_usages:
            node_ids = set(usage.get("node_ids", []))
            edges = usage.get("edges", []) or []
            affected_connections = []

            for edge in edges:
                edge_affected = False
                affected_port = None

                if edge.get("src_node") in node_ids:
                    src_port = edge.get("src_port")
                    if src_port in removed_pins or src_port in changed_pins:
                        edge_affected = True
                        affected_port = src_port

                if edge.get("dst_node") in node_ids:
                    dst_port = edge.get("dst_port")
                    if dst_port in removed_pins or dst_port in changed_pins:
                        edge_affected = True
                        affected_port = dst_port

                if edge_affected:
                    affected_connections.append(
                        {
                            "edge_id": edge.get("id"),
                            "port_name": affected_port,
                            "is_removed": affected_port in removed_pins,
                            "is_changed": affected_port in changed_pins,
                        }
                    )

            if affected_connections:
                affected_graphs.append(
                    {
                        "graph_id": usage["graph_id"],
                        "graph_name": usage.get("graph_name", usage["graph_id"]),
                        "affected_connections": affected_connections,
                        "connection_count": len(affected_connections),
                    }
                )

        total_connections = sum(g["connection_count"] for g in affected_graphs)
        
        return {
            "has_impact": len(affected_graphs) > 0,
            "removed_pins": removed_pins,
            "changed_pins": changed_pins,
            "affected_graphs": affected_graphs,
            "total_affected_connections": total_connections
        }
    
    def update_composite_node(self, composite_id: str, composite: CompositeNodeConfig, skip_impact_check: bool = False) -> bool:
        """更新复合节点
        
        Args:
            composite_id: 复合节点ID
            composite: 新的复合节点配置
            skip_impact_check: 是否跳过影响检查（用户已确认的情况）
            
        Returns:
            是否成功
        """
        if composite_id not in self.composite_nodes:
            log_error(f"复合节点不存在: {composite_id}")
            return False
        
        # 如果不跳过影响检查，需要先分析影响
        # 注意：这里不在manager层做UI交互，只更新数据
        # UI层应该先调用 analyze_composite_update_impact() 并显示确认对话框
        
        self.composite_nodes[composite_id] = composite
        file_path = self.loader.save_composite_to_file(composite)
        self.composite_index[composite_id] = file_path
        if self._graph_reference_tracker is not None:
            self._graph_reference_tracker.clear_composite_usage_cache(composite.node_name)

        log_info(f"更新复合节点: {composite.node_name} (ID: {composite_id})")
        return True
    
    def delete_composite_node(self, composite_id: str) -> bool:
        """删除复合节点
        
        Args:
            composite_id: 复合节点ID
            
        Returns:
            是否成功
        """
        if composite_id not in self.composite_nodes:
            log_error(f"复合节点不存在: {composite_id}")
            return False
        
        node_name = self.composite_nodes[composite_id].node_name
        
        # 删除代码文件
        if composite_id in self.composite_index:
            file_path = self.composite_index[composite_id]
            if file_path.exists():
                file_path.unlink()
            del self.composite_index[composite_id]
        
        del self.composite_nodes[composite_id]
        
        log_info(f"删除复合节点: {node_name} (ID: {composite_id})")
        return True
    
    def load_subgraph_if_needed(self, composite_id: str) -> bool:
        """按需加载复合节点的子图（懒加载机制）
        
        当复合节点被真正使用时（编辑或实例化），调用此方法加载子图。
        如果子图已加载，则直接返回成功。
        
        Args:
            composite_id: 复合节点ID
            
        Returns:
            是否成功加载（或已加载）
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            if self.verbose:
                log_warn(f"复合节点不存在: {composite_id}")
            return False
        
        # 检查子图是否已加载（非空且有节点）
        if composite.sub_graph and len(composite.sub_graph.get('nodes', [])) > 0:
            return True  # 已加载
        
        # 从文件重新加载（包含子图）
        file_path = self.composite_index.get(composite_id)
        if not file_path or not file_path.exists():
            if self.verbose:
                log_warn(f"找不到复合节点文件: {composite_id}")
            return False

        # 强制加载子图
        composite_with_subgraph = self.loader.load_composite_from_file(file_path, load_subgraph=True)
        if composite_with_subgraph:
            # 更新子图和虚拟引脚（包含mapped_ports）
            composite.sub_graph = composite_with_subgraph.sub_graph
            composite.virtual_pins = composite_with_subgraph.virtual_pins
            if self.verbose:
                log_info(f"延迟加载子图: {composite.node_name} (ID: {composite_id})")
            return True
        
        return False
    
    def list_composite_nodes(self, folder_path: str = None) -> List[CompositeNodeConfig]:
        """列出所有复合节点
        
        Args:
            folder_path: 文件夹路径（None表示所有节点，空字符串表示根目录）
            
        Returns:
            复合节点列表
        """
        if folder_path is None:
            return list(self.composite_nodes.values())
        else:
            return [c for c in self.composite_nodes.values() if c.folder_path == folder_path]
    
    def create_folder(self, folder_name: str, parent_folder: str = "") -> bool:
        """创建文件夹
        
        Args:
            folder_name: 文件夹名称
            parent_folder: 父文件夹路径（空字符串表示根目录）
            
        Returns:
            是否成功
        """
        return self.folder_manager.create_folder(folder_name, parent_folder)
    
    def delete_folder(self, folder_path: str, force: bool = False) -> bool:
        """删除文件夹
        
        Args:
            folder_path: 文件夹路径
            force: 是否强制删除（包含复合节点的文件夹）
            
        Returns:
            是否成功
        """
        # 检查文件夹中是否有复合节点
        nodes_in_folder = [c for c in self.composite_nodes.values() if c.folder_path == folder_path]
        
        # 如果需要强制删除，先删除文件夹中的所有复合节点
        if force and nodes_in_folder:
            for composite in nodes_in_folder:
                self.delete_composite_node(composite.composite_id)
        
        # 委托给文件夹管理器
        return self.folder_manager.delete_folder(folder_path, nodes_in_folder, force)
    
    def move_to_folder(self, composite_id: str, target_folder: str) -> bool:
        """将复合节点移动到指定文件夹
        
        Args:
            composite_id: 复合节点ID
            target_folder: 目标文件夹路径（空字符串表示根目录）
            
        Returns:
            是否成功
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            log_error(f"复合节点不存在: {composite_id}")
            return False
        
        # 检查目标文件夹是否存在
        if not self.folder_manager.validate_target_folder(target_folder):
            log_error(f"目标文件夹不存在: {target_folder}")
            return False
        
        # 删除旧文件
        old_file_path = self.composite_index.get(composite_id)
        if old_file_path and old_file_path.exists():
            old_file_path.unlink()
        
        # 更新文件夹路径
        composite.folder_path = target_folder
        
        # 保存到新位置
        file_path = self.loader.save_composite_to_file(composite)
        self.composite_index[composite_id] = file_path
        
        log_info(f"移动复合节点 '{composite.node_name}' 到文件夹: {target_folder or '(根目录)'}")
        return True
    
    def validate_composite_node(self, composite: CompositeNodeConfig) -> List[str]:
        """验证复合节点定义的完整性
        
        Args:
            composite: 复合节点配置
            
        Returns:
            错误信息列表（空列表表示验证通过）
        """
        errors = []
        
        # 检查基本信息
        if not composite.node_name:
            errors.append("复合节点名称不能为空")
        
        if not composite.composite_id:
            errors.append("复合节点ID不能为空")
        
        # 检查作用域
        if composite.scope != "server":
            errors.append(f"复合节点作用域必须为'server'，当前为'{composite.scope}'")
        
        # 检查虚拟引脚
        if not composite.virtual_pins:
            errors.append("复合节点至少需要一个虚拟引脚")
        
        # 检查虚拟引脚序号唯一性
        pin_indices = [pin.pin_index for pin in composite.virtual_pins]
        if len(pin_indices) != len(set(pin_indices)):
            errors.append("虚拟引脚序号存在重复")
        
        # 检查子图
        if not composite.sub_graph:
            errors.append("复合节点子图不能为空")
        elif "nodes" not in composite.sub_graph:
            errors.append("复合节点子图格式错误：缺少'nodes'字段")
        
        return errors
    
    def composite_to_node_def(self, composite: CompositeNodeConfig) -> NodeDef:
        """将复合节点转换为NodeDef格式，以便在节点库中使用
        
        Args:
            composite: 复合节点配置
            
        Returns:
            NodeDef对象
        """
        from engine.nodes.advanced_node_features import convert_composite_to_node_def
        return convert_composite_to_node_def(composite)
    
    def get_all_node_defs(self) -> Dict[str, NodeDef]:
        """获取所有复合节点的NodeDef表示
        
        注意：此方法主要供外部工具或UI直接访问使用。
        
        对于常规节点库访问，推荐使用：
            from engine.nodes.node_registry import get_node_registry
            registry = get_node_registry(workspace_path)
            library = registry.get_library()  # 包含所有节点（含复合节点）
        
        Returns:
            {节点键: NodeDef} 字典，键格式为 "复合节点/节点名称"
        """
        node_defs = {}
        
        for composite in self.composite_nodes.values():
            node_def = self.composite_to_node_def(composite)
            key = f"复合节点/{composite.node_name}"
            node_defs[key] = node_def
        
        return node_defs
    
    # ========== 虚拟引脚映射管理 ==========
    
    def add_virtual_pin_mapping(
        self,
        composite_id: str,
        pin_index: int,
        node_id: str,
        port_name: str,
        is_input: bool,
        port_type: str = None,
        is_flow: bool = False
    ) -> bool:
        """为虚拟引脚添加端口映射
        
        Args:
            composite_id: 复合节点ID
            pin_index: 虚拟引脚序号
            node_id: 内部节点ID
            port_name: 端口名称
            is_input: 端口方向
            port_type: 端口类型（可选，用于类型检查）
            is_flow: 是否为流程端口
            
        Returns:
            是否成功
        """
        return self.virtual_pin_manager.add_virtual_pin_mapping(
            composite_id, pin_index, node_id, port_name, is_input, port_type, is_flow
        )
    
    def remove_virtual_pin_mapping(
        self,
        composite_id: str,
        pin_index: int,
        node_id: str,
        port_name: str
    ) -> bool:
        """移除虚拟引脚的端口映射
        
        Args:
            composite_id: 复合节点ID
            pin_index: 虚拟引脚序号
            node_id: 内部节点ID
            port_name: 端口名称
            
        Returns:
            是否成功
        """
        return self.virtual_pin_manager.remove_virtual_pin_mapping(
            composite_id, pin_index, node_id, port_name
        )
    
    def find_port_virtual_pin(
        self,
        composite_id: str,
        node_id: str,
        port_name: str
    ) -> Optional[VirtualPinConfig]:
        """查找端口对应的虚拟引脚
        
        Args:
            composite_id: 复合节点ID
            node_id: 内部节点ID
            port_name: 端口名称
            
        Returns:
            虚拟引脚配置，如果没有映射则返回None
        """
        return self.virtual_pin_manager.find_port_virtual_pin(
            composite_id, node_id, port_name
        )
    
    def get_available_virtual_pins(
        self,
        composite_id: str,
        is_input: bool,
        is_flow: bool = None
    ) -> List[VirtualPinConfig]:
        """获取可用的虚拟引脚列表（用于添加到现有虚拟引脚）
        
        Args:
            composite_id: 复合节点ID
            is_input: 端口方向
            is_flow: 是否为流程端口（None表示不过滤）
            
        Returns:
            同方向、同类型的虚拟引脚列表
        """
        return self.virtual_pin_manager.get_available_virtual_pins(
            composite_id, is_input, is_flow
        )
    
    def get_pin_display_number(
        self,
        composite_id: str,
        virtual_pin: VirtualPinConfig
    ) -> tuple[str, int]:
        """获取虚拟引脚的显示编号
        
        引脚编号规则：流程口和数据口分别编号，输入和输出分别编号
        
        Args:
            composite_id: 复合节点ID
            virtual_pin: 虚拟引脚配置
            
        Returns:
            (类型前缀, 编号)，例如 ("流", 1) 表示 [流1]
        """
        return self.virtual_pin_manager.get_pin_display_number(
            composite_id, virtual_pin
        )


# 全局实例（延迟初始化）
_global_manager: Optional[CompositeNodeManager] = None


def get_composite_node_manager(
    workspace_path: Path = None,
    verbose: bool = False,
    base_node_library: Optional[Dict[str, NodeDef]] = None,
) -> CompositeNodeManager:
    """获取全局复合节点管理器实例
    
    Args:
        workspace_path: 工作空间路径（仅首次调用时需要）
        verbose: 是否打印详细日志（仅首次创建时有效）
        base_node_library: 可选的基础节点库（仅首次创建时用于避免循环依赖）
        
    Returns:
        复合节点管理器实例
    """
    global _global_manager

    if _global_manager is None:
        if workspace_path is None:
            raise ValueError("首次调用需要提供workspace_path")
        # 若未显式注入基础节点库，则优先复用集中式节点注册表中的节点定义，避免重复跑节点实现管线
        if base_node_library is None:
            registry = get_node_registry(workspace_path, include_composite=True)
            base_node_library = registry.get_library()
        _global_manager = CompositeNodeManager(
            workspace_path,
            verbose=verbose,
            base_node_library=base_node_library,
        )

    return _global_manager

