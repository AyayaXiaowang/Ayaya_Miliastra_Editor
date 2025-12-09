"""复合节点代码解析器 - 薄封装与调度层

从函数/类格式代码解析为CompositeNodeConfig和虚拟引脚。
委托具体解析工作给专用解析器模块。
"""

from __future__ import annotations
import ast
from typing import Dict, Optional
from pathlib import Path

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.advanced_node_features import CompositeNodeConfig, MappedPort
from engine.graph.common import node_name_index_from_library, apply_layout_quietly
from engine.graph.utils.metadata_extractor import (
    GraphMetadata,
    extract_metadata_from_code,
)
from engine.graph.ir.virtual_pin_builder import build_virtual_pins_from_class
from engine.graph.composite.class_format_parser import ClassFormatParser
from engine.utils.logging.logger import log_info
from engine.graph.utils.ast_utils import (
    collect_module_constants,
    set_module_constants_context,
    clear_module_constants_context,
)


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
        
        # 5. 收集模块级常量并设置上下文（支持在节点调用中引用模块级常量）
        module_constants = collect_module_constants(tree)
        if self.verbose and module_constants:
            log_info("  收集到 {} 个模块级常量: {}", len(module_constants), list(module_constants.keys()))
        set_module_constants_context(module_constants)
        
        # 6. 委托类格式解析器解析所有装饰的方法，生成子图
        graph_model = self.class_parser.parse_class_methods(class_def, virtual_pins)
        
        # 清除模块常量上下文
        clear_module_constants_context()
        
        # 7. 应用布局
        if self.verbose:
            log_info("[CompositeCodeParser] 应用自动布局...")
        
        apply_layout_quietly(graph_model)

        # 7.1 将虚拟引脚映射扩展到布局阶段创建的"数据节点副本"上，保持映射与最终子图一致
        self._propagate_virtual_pin_mappings_to_copies(virtual_pins, graph_model)
        
        # 8. 构建CompositeNodeConfig
        class_name = class_def.name
        composite = CompositeNodeConfig(
            composite_id=metadata_obj.composite_id or f"composite_{class_name}",
            node_name=class_name,
            node_description=metadata_obj.node_description or "",
            scope=metadata_obj.scope or "server",
            virtual_pins=virtual_pins,
            sub_graph=graph_model.serialize(),
            folder_path=metadata_obj.folder_path or ""
        )
        
        if self.verbose:
            log_info(
                "[CompositeCodeParser] 解析完成: {}个虚拟引脚, {}个节点",
                len(virtual_pins),
                len(graph_model.nodes),
            )
        
        return composite

    def _propagate_virtual_pin_mappings_to_copies(
        self,
        virtual_pins,
        graph_model,
    ) -> None:
        """在布局后将虚拟引脚映射同步到数据节点副本上。

        布局管线在启用 DATA_NODE_CROSS_BLOCK_COPY 时，会为跨块共享的数据节点创建
        `is_data_node_copy=True` 的副本，并通过 `original_node_id` 记录根原始节点 ID。
        虚拟引脚映射是在布局前基于原始节点 ID 构建的，若不做同步，布局产生的副本
        将缺乏映射信息，导致在某些块内查看时看起来“输入未连接”。

        这里按以下规则扩展映射：
        - 针对每个虚拟引脚当前的 mapped_ports 条目 (node_id, port_name, ...)，
          查找所有 `original_node_id == node_id` 且 `is_data_node_copy=True` 的副本；
        - 为这些副本追加同名端口的映射，保持 is_input / is_flow 与原映射一致；
        - 已存在完全相同条目时不会重复追加。
        """
        # 构建 原始ID -> [副本ID...] 的索引，仅关注数据节点副本
        copies_by_origin = {}
        for node in graph_model.nodes.values():
            origin_id = getattr(node, "original_node_id", "") or ""
            if not origin_id:
                continue
            if not getattr(node, "is_data_node_copy", False):
                continue
            copies_by_origin.setdefault(str(origin_id), []).append(str(node.id))

        if not copies_by_origin:
            return

        for pin in virtual_pins:
            mapped = getattr(pin, "mapped_ports", None) or []
            if not mapped:
                continue

            # 复制当前列表快照，避免在迭代过程中扩容影响遍历
            existing_mappings = list(mapped)
            for entry in existing_mappings:
                origin_node_id = getattr(entry, "node_id", None)
                if not origin_node_id:
                    continue
                copy_ids = copies_by_origin.get(str(origin_node_id))
                if not copy_ids:
                    continue

                for copy_id in copy_ids:
                    # 避免添加重复映射
                    already_exists = any(
                        (mp.node_id == copy_id)
                        and (mp.port_name == entry.port_name)
                        and (mp.is_input == entry.is_input)
                        and (mp.is_flow == entry.is_flow)
                        for mp in pin.mapped_ports
                    )
                    if already_exists:
                        continue

                    pin.mapped_ports.append(
                        MappedPort(
                            node_id=copy_id,
                            port_name=entry.port_name,
                            is_input=entry.is_input,
                            is_flow=entry.is_flow,
                        )
                    )
    
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


