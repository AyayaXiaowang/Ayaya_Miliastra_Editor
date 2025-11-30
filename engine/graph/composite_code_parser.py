"""复合节点代码解析器 - 薄封装与调度层

从函数/类格式代码解析为CompositeNodeConfig和虚拟引脚。
委托具体解析工作给专用解析器模块。
"""

from __future__ import annotations
import ast
from typing import Dict, Optional
from pathlib import Path

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.advanced_node_features import CompositeNodeConfig
from engine.graph.common import node_name_index_from_library, apply_layout_quietly
from engine.graph.utils.metadata_extractor import (
    GraphMetadata,
    extract_metadata_from_code,
)
from engine.graph.ir.virtual_pin_builder import build_virtual_pins_from_class
from engine.graph.composite.class_format_parser import ClassFormatParser
from engine.utils.logging.logger import log_info


class CompositeCodeParser:
    """复合节点代码解析器（薄封装与调度层）
    
    负责：
    1. 识别并解析类格式代码
    2. 提取元数据
    3. 委托专用解析器进行实际解析
    4. 应用布局
    5. 构建最终的CompositeNodeConfig
    """
    
    def __init__(self, node_library: Dict[str, NodeDef], verbose: bool = False):
        """初始化解析器
        
        Args:
            node_library: 节点库（键格式："分类/节点名"）
            verbose: 是否输出详细日志
        """
        self.node_library = node_library
        self.verbose = verbose
        
        # 建立统一的节点名索引（含同义键）
        self.node_name_index = node_name_index_from_library(node_library)
        
        # 创建专用解析器（仅支持类格式）
        self.class_parser = ClassFormatParser(node_library, verbose)
    
    def parse_file(self, file_path: Path) -> CompositeNodeConfig:
        """从文件解析复合节点
        
        Args:
            file_path: 复合节点文件路径
            
        Returns:
            CompositeNodeConfig
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        return self.parse_code(code, file_path)
    
    def parse_code(self, code: str, file_path: Optional[Path] = None) -> CompositeNodeConfig:
        """从代码解析复合节点（仅支持类格式）
        
        Args:
            code: 源代码
            file_path: 文件路径（可选，用于提取folder_path）
            
        Returns:
            CompositeNodeConfig
        """
        tree = ast.parse(code)
        # 仅支持类格式：使用AST检测并解析带有 @composite_class 装饰器的类
        if not self._detect_class_format(tree):
            raise ValueError("复合节点仅支持类格式定义：未找到带 @composite_class 装饰器的类")
        metadata_obj = extract_metadata_from_code(code)
        return self.parse_class_format(code, file_path, tree=tree, metadata_obj=metadata_obj)
    
    def parse_class_format(
        self,
        code: str,
        file_path: Optional[Path] = None,
        *,
        tree: Optional[ast.Module] = None,
        metadata_obj: Optional[GraphMetadata] = None,
    ) -> CompositeNodeConfig:
        """从类格式代码解析复合节点（新格式）
        
        Args:
            code: 源代码
            file_path: 文件路径（可选，用于提取folder_path）
            
        Returns:
            CompositeNodeConfig
        """
        if self.verbose:
            log_info("[CompositeCodeParser] 开始解析复合节点代码（类格式）...")
        
        # 1. 解析AST
        if tree is None:
            tree = ast.parse(code)
        
        # 2. 提取元数据（从代码：docstring + GRAPH_VARIABLES）
        if metadata_obj is None:
            metadata_obj = extract_metadata_from_code(code)
        metadata = {
            'composite_id': metadata_obj.composite_id,
            'node_name': metadata_obj.node_name,
            'node_description': metadata_obj.node_description,
            'scope': metadata_obj.scope,
            'folder_path': metadata_obj.folder_path,
        }
        
        # 3. 找到复合节点类定义
        class_def = self._find_composite_class(tree)
        if not class_def:
            raise ValueError("未找到复合节点类定义")
        
        if self.verbose:
            log_info("  找到类定义: {}", class_def.name)
        
        # 4. 从类的装饰器方法提取虚拟引脚
        virtual_pins = build_virtual_pins_from_class(class_def)
        
        if self.verbose:
            log_info("  提取了 {} 个虚拟引脚", len(virtual_pins))
        
        # 5. 委托类格式解析器解析所有装饰的方法，生成子图
        graph_model = self.class_parser.parse_class_methods(class_def, virtual_pins)
        
        # 6. 应用布局
        if self.verbose:
            log_info("[CompositeCodeParser] 应用自动布局...")
        
        apply_layout_quietly(graph_model)
        
        # 7. 构建CompositeNodeConfig
        composite = CompositeNodeConfig(
            composite_id=metadata.get("composite_id", f"composite_{class_def.name}"),
            node_name=metadata.get("node_name", class_def.name),
            node_description=metadata.get("node_description", ""),
            scope=metadata.get("scope", "server"),
            virtual_pins=virtual_pins,
            sub_graph=graph_model.serialize(),
            folder_path=metadata.get("folder_path", "")
        )
        
        if self.verbose:
            log_info(
                "[CompositeCodeParser] 解析完成: {}个虚拟引脚, {}个节点",
                len(virtual_pins),
                len(graph_model.nodes),
            )
        
        return composite
    
    def _detect_class_format(self, tree: ast.Module) -> bool:
        """检测是否为类格式（基于AST）"""
        return self._find_composite_class(tree) is not None
    
    def _find_composite_class(self, tree: ast.Module) -> Optional[ast.ClassDef]:
        """查找带有 @composite_class 装饰器的类定义
        
        Args:
            tree: AST根节点
            
        Returns:
            类定义节点，如果未找到返回None
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 检查是否有 @composite_class 装饰器
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'composite_class':
                        return node
        return None


