"""复合节点加载器 - 负责复合节点的文件加载、保存和序列化"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
import ast

from engine.nodes.advanced_node_features import CompositeNodeConfig
from engine.nodes.node_definition_loader import NodeDef
from engine.graph import CompositeCodeParser
from engine.graph.composite.source_format import (
    find_primary_composite_class,
    try_parse_composite_payload,
)
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.utils.logging.logger import log_info
from engine.utils.name_utils import sanitize_composite_filename
from engine.utils.resource_library_layout import discover_resource_root_directories
from engine.utils.runtime_scope import get_active_package_id


class CompositeNodeLoader:
    """复合节点加载器 - 处理文件的读取、解析和序列化
    
    职责：
    - 从文件加载复合节点（仅支持：payload / 类格式）
    - 保存复合节点为文件（类格式，含 JSON payload；用于可视化编辑闭环）
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
        self._code_generator = None
        self._cached_composite_node_defs_for_parse: Optional[Dict[str, NodeDef]] = None
        self._cached_active_package_id: Optional[str] = None

    def set_code_generator(self, code_generator) -> None:
        """注入复合节点代码生成器（应用层实现）。"""
        self._code_generator = code_generator
    
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
            if self.base_node_library is None:
                raise ValueError(
                    "CompositeNodeLoader.load_composite_from_file(load_subgraph=True) 需要注入 base_node_library。"
                    "禁止在此处隐式重新扫描实现库或反向触发 NodeRegistry，以避免缓存不一致/循环依赖。"
                )
            # 关键：解析复合节点子图时需要“基础节点库 + 当前作用域内的复合节点 NodeDef”，
            # 否则方法体内的 `self.<复合实例>.<入口>(...)` 无法被识别并建模为 IR 节点，
            # 会表现为“复合节点内部为空壳”（尤其是嵌套复合）。
            active_package_id = get_active_package_id()
            if active_package_id != self._cached_active_package_id or self._cached_composite_node_defs_for_parse is None:
                from engine.nodes.pipeline.composite_runner import run_composite_pipeline

                self._cached_composite_node_defs_for_parse = run_composite_pipeline(
                    workspace_path=self.workspace_path,
                    base_node_library=dict(self.base_node_library),
                    verbose=bool(self.verbose),
                )
                self._cached_active_package_id = active_package_id

            node_library: Dict[str, NodeDef] = dict(self.base_node_library)
            node_library.update(dict(self._cached_composite_node_defs_for_parse or {}))

            parser = CompositeCodeParser(
                node_library,
                verbose=self.verbose,
                workspace_path=self.workspace_path,
            )
            # 完整解析（包括子图）- parse_code 会自动检测格式
            return parser.parse_code(code, file_path)

        # 只加载元数据和虚拟引脚（懒加载路径）：不依赖节点库，避免重复跑节点实现管线
        tree = ast.parse(code)
        metadata_obj = extract_metadata_from_code(code)

        # 优先：可视化编辑器落盘格式（JSON payload）
        payload_composite = try_parse_composite_payload(tree)
        if payload_composite is not None:
            folder_path = self.get_relative_folder_path(file_path)
            # 懒加载：保留虚拟引脚与元数据，子图保持空壳，避免在启动阶段加载大图
            return CompositeNodeConfig(
                composite_id=payload_composite.composite_id,
                node_name=payload_composite.node_name,
                node_description=payload_composite.node_description or "",
                scope=payload_composite.scope or "server",
                virtual_pins=payload_composite.virtual_pins,
                sub_graph={"nodes": [], "edges": [], "graph_variables": []},
                folder_path=(payload_composite.folder_path or metadata_obj.folder_path or folder_path),
            )

        # 仅支持类格式：从类定义提取虚拟引脚
        class_def = find_primary_composite_class(tree)
        if class_def is None:
            raise ValueError(
                "复合节点仅支持 payload 或类格式定义：未找到 COMPOSITE_PAYLOAD_JSON 且未找到 @composite_class"
            )

        from engine.graph.ir.virtual_pin_builder import build_virtual_pins_from_class

        virtual_pins = build_virtual_pins_from_class(class_def)
        node_name = class_def.name

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
    
    def save_composite_to_file(self, composite: CompositeNodeConfig) -> Path:
        """保存复合节点为类格式文件（含 JSON payload）
        
        Args:
            composite: 复合节点配置
            
        Returns:
            保存的文件路径
        """
        # 获取保存路径
        file_path = self.get_file_save_path(composite)
        
        if self._code_generator is None:
            raise ValueError(
                "CompositeNodeLoader.save_composite_to_file 需要注入复合节点代码生成器（应用层实现），"
                "以避免 engine 层绑定运行时/插件导入。"
            )

        code = self._code_generator.generate_code(composite)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(code)
        
        if self.verbose:
            log_info(f"保存复合节点（类格式）: {file_path.name}")
        
        return file_path
    
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
        parent_dir = file_path.parent.resolve()

        direct_relative = self._get_relative_folder_path_if_under(parent_dir, self.composite_library_dir)
        if direct_relative is not None:
            return direct_relative

        # 兼容多 root：当复合节点文件位于共享/项目存档目录下时，按实际落盘目录推断 folder_path。
        workspace_root = self.workspace_path.resolve()
        resource_library_root = (workspace_root / "assets" / "资源库").resolve()
        resource_roots = discover_resource_root_directories(resource_library_root)
        candidate_library_dirs = [root / "复合节点库" for root in resource_roots]
        candidate_library_dirs_sorted = sorted(
            candidate_library_dirs,
            key=lambda path: len(path.resolve().parts),
            reverse=True,
        )
        for composite_library_dir in candidate_library_dirs_sorted:
            inferred_relative = self._get_relative_folder_path_if_under(parent_dir, composite_library_dir)
            if inferred_relative is not None:
                return inferred_relative

        return ""

    @staticmethod
    def _get_relative_folder_path_if_under(parent_dir: Path, composite_library_dir: Path) -> str | None:
        """若 parent_dir 位于 composite_library_dir 下，返回相对路径文本；否则返回 None。"""
        parent_parts = parent_dir.resolve().parts
        root_parts = composite_library_dir.resolve().parts
        if len(parent_parts) < len(root_parts):
            return None
        if parent_parts[: len(root_parts)] != root_parts:
            return None
        relative_parts = parent_parts[len(root_parts) :]
        if not relative_parts:
            return ""
        return "/".join(str(part) for part in relative_parts)
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """将节点名称转换为有效的文件名（不包含扩展名）。"""
        return sanitize_composite_filename(name)

