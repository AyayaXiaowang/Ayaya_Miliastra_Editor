"""复合节点加载器 - 负责复合节点的文件加载、保存和序列化"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, Optional
import ast

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from engine.nodes.node_definition_loader import NodeDef
from engine.graph import CompositeCodeParser
from engine.graph.composite_code_generator import CompositeCodeGenerator
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.graph.utils.ast_utils import find_composite_function
from engine.utils.logging.logger import log_info
from engine.utils.name_utils import sanitize_composite_filename


class CompositeNodeLoader:
    """复合节点加载器 - 处理文件的读取、解析和序列化
    
    职责：
    - 从文件加载复合节点（支持函数格式和类格式）
    - 保存复合节点为文件（函数格式）
    - 文件格式迁移（从旧的JSON格式到新的代码格式）
    - 文件名处理和路径计算
    """
    
    def __init__(
        self, 
        workspace_path: Path,
        composite_library_dir: Path,
        verbose: bool = False,
        base_node_library: Optional[Dict[str, NodeDef]] = None
    ):
        """初始化加载器
        
        Args:
            workspace_path: 工作空间路径
            composite_library_dir: 复合节点库目录
            verbose: 是否打印详细日志
            base_node_library: 基础节点库（用于解析时避免循环依赖）
        """
        self.workspace_path = workspace_path
        self.composite_library_dir = composite_library_dir
        self.verbose = verbose
        self.base_node_library = base_node_library
    
    def load_composite_from_file(
        self,
        file_path: Path,
        load_subgraph: bool = False,
    ) -> Optional[CompositeNodeConfig]:
        """从文件加载复合节点（自动检测格式）

        Args:
            file_path: 复合节点文件路径
            load_subgraph: 是否加载子图（False=懒加载只加载元数据，True=立即加载子图）

        Returns:
            复合节点配置，加载失败返回None
        """
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as file:
            code = file.read()

        if load_subgraph:
            # 需要完整解析子图时才构建节点库与解析器，避免元数据加载阶段的额外扫描开销
            # 优先使用外部注入的基础节点库，避免在加载过程中回调注册表导致循环依赖
            if self.base_node_library is not None:
                node_library = self.base_node_library
            else:
                # 回退：直接从实现侧加载基础节点库（不包含复合节点），避免触发注册表的完整加载流程
                from engine.nodes.impl_definition_loader import load_all_nodes_from_impl

                node_library = load_all_nodes_from_impl(
                    self.workspace_path,
                    include_composite=False,
                    verbose=self.verbose,
                )

            parser = CompositeCodeParser(node_library, verbose=self.verbose)
            # 完整解析（包括子图）- parse_code 会自动检测格式
            return parser.parse_code(code, file_path)

        # 只加载元数据和虚拟引脚（懒加载路径）：不依赖节点库，避免重复跑节点实现管线
        tree = ast.parse(code)
        metadata_obj = extract_metadata_from_code(code)

        # 检测格式：类格式 vs 函数格式
        if "@composite_class" in code:
            # 类格式：从类定义提取
            class_def = self._find_composite_class_in_tree(tree)
            if class_def:
                from engine.graph.ir.virtual_pin_builder import build_virtual_pins_from_class

                virtual_pins = build_virtual_pins_from_class(class_def)
                node_name = class_def.name
            else:
                virtual_pins = []
                node_name = "未命名"
        else:
            # 函数格式：从函数签名提取
            func_def = find_composite_function(tree)
            from engine.graph.ir.virtual_pin_builder import build_virtual_pins_from_signature

            virtual_pins = build_virtual_pins_from_signature(func_def) if func_def else []
            node_name = func_def.name if func_def else "未命名"

        # 计算文件夹路径
        folder_path = self.get_relative_folder_path(file_path)

        # 创建CompositeNodeConfig（不包含子图）
        return CompositeNodeConfig(
            composite_id=(metadata_obj.composite_id or f"composite_{node_name}"),
            node_name=(metadata_obj.node_name or node_name),
            node_description=(metadata_obj.node_description or ""),
            scope=(metadata_obj.scope or "server"),
            virtual_pins=virtual_pins,
            sub_graph={"nodes": [], "edges": [], "graph_variables": []},
            folder_path=(metadata_obj.folder_path or folder_path),
        )
    
    def _find_composite_class_in_tree(self, tree: ast.Module) -> Optional[ast.ClassDef]:
        """在AST中查找复合节点类定义
        
        Args:
            tree: AST根节点
            
        Returns:
            类定义节点，未找到返回None
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'composite_class':
                        return node
        return None
    
    def save_composite_to_file(self, composite: CompositeNodeConfig) -> Path:
        """保存复合节点为函数格式文件
        
        Args:
            composite: 复合节点配置
            
        Returns:
            保存的文件路径
        """
        # 获取保存路径
        file_path = self.get_file_save_path(composite)
        
        # 使用CompositeCodeGenerator生成函数格式代码
        # 生成器可选使用节点库；优先使用基础节点库以避免加载回路
        if self.base_node_library is not None:
            node_library = self.base_node_library
        else:
            from engine.nodes.impl_definition_loader import load_all_nodes_from_impl
            node_library = load_all_nodes_from_impl(
                self.workspace_path, 
                include_composite=False, 
                verbose=self.verbose
            )
        
        generator = CompositeCodeGenerator(node_library)
        code = generator.generate_code(composite)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(code)
        
        if self.verbose:
            log_info(f"保存复合节点（函数格式）: {file_path.name}")
        
        return file_path
    
    def migrate_from_json(self, json_file: Path) -> list[CompositeNodeConfig]:
        """从旧的JSON文件迁移到函数代码格式
        
        Args:
            json_file: 旧的JSON文件路径
            
        Returns:
            迁移的复合节点列表
        """
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        composites_in_json = data.get("composite_nodes", [])
        if not composites_in_json:
            # 空文件，直接删除
            if self.verbose:
                log_info(f"[迁移] JSON文件为空，删除: {json_file.name}")
            json_file.unlink()
            return []
        
        # 迁移每个复合节点
        migrated_composites = []
        for composite_data in composites_in_json:
            composite = CompositeNodeConfig.deserialize(composite_data)
            # 保存为函数代码文件
            self.save_composite_to_file(composite)
            migrated_composites.append(composite)
            if self.verbose:
                log_info(f"[迁移] {composite.node_name} (ID: {composite.composite_id})")
        
        # 删除旧JSON文件
        json_file.unlink()
        log_info(f"迁移完成: {len(migrated_composites)} 个复合节点，已删除旧JSON文件")
        
        return migrated_composites
    
    def get_file_save_path(self, composite: CompositeNodeConfig) -> Path:
        """根据配置获取复合节点的保存路径
        
        Args:
            composite: 复合节点配置
            
        Returns:
            完整的文件保存路径
        """
        if composite.folder_path:
            folder_dir = self.composite_library_dir / composite.folder_path
            folder_dir.mkdir(parents=True, exist_ok=True)
            return folder_dir / f"{composite.composite_id}.py"
        else:
            return self.composite_library_dir / f"{composite.composite_id}.py"
    
    def get_relative_folder_path(self, file_path: Path) -> str:
        """计算文件的相对文件夹路径
        
        Args:
            file_path: 文件的完整路径
            
        Returns:
            相对于复合节点库目录的文件夹路径（空字符串表示根目录）
        """
        if file_path.parent != self.composite_library_dir:
            return str(file_path.parent.relative_to(self.composite_library_dir))
        return ""
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """将节点名称转换为有效的文件名（不包含扩展名）。"""
        return sanitize_composite_filename(name)

