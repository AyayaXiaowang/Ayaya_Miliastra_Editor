"""复合节点代码解析器 - 薄封装与调度层

从 payload（可视化落盘）/类格式代码解析为 CompositeNodeConfig 和虚拟引脚。
委托具体解析工作给专用解析器模块。
"""

from __future__ import annotations
import ast
from typing import Dict, Optional
from pathlib import Path

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.advanced_node_features import CompositeNodeConfig, MappedPort
from engine.graph.common import node_name_index_from_library, apply_layout_quietly
from engine.graph.composite.source_format import (
    find_primary_composite_class,
    try_parse_composite_payload,
)
from engine.graph.utils.metadata_extractor import (
    GraphMetadata,
    extract_metadata_from_code,
)
from engine.graph.utils.graph_code_rewrite_config import build_graph_code_rewrite_config
from engine.graph.utils.list_literal_rewriter import rewrite_graph_code_list_literals
from engine.graph.utils.dict_literal_rewriter import rewrite_graph_code_dict_literals
from engine.graph.utils.syntax_sugar_rewriter import rewrite_graph_code_syntax_sugars
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
    
    def __init__(
        self,
        node_library: Dict[str, NodeDef],
        verbose: bool = False,
        workspace_path: Optional[Path] = None,
    ):
        """初始化解析器
        
        Args:
            node_library: 节点库（键格式："分类/节点名"）
            verbose: 是否输出详细日志
            workspace_path: 工作区根目录（用于解析阶段的布局上下文构建，避免反向依赖 NodeRegistry）
        """
        self.node_library = node_library
        self.verbose = verbose
        self.workspace_path = workspace_path
        
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
        """从代码解析复合节点（支持：payload / 类格式）
        
        Args:
            code: 源代码
            file_path: 文件路径（可选，用于提取folder_path）
            
        Returns:
            CompositeNodeConfig
        """
        tree = ast.parse(code)

        # 0) 优先：可视化编辑器落盘格式（JSON payload）
        payload_composite = try_parse_composite_payload(tree)
        if payload_composite is not None:
            return payload_composite

        # 仅支持类格式：使用AST检测并解析带有 @composite_class 装饰器的类
        if not self._detect_class_format(tree):
            raise ValueError("复合节点仅支持 payload 或类格式定义：未找到 COMPOSITE_PAYLOAD_JSON 且未找到 @composite_class")

        metadata_obj = extract_metadata_from_code(code)
        scope = str((metadata_obj.scope or metadata_obj.graph_type or "server") or "server").strip().lower()

        # 类格式复合节点：常见语法糖（下标读取/len/比较/and-or/+= 等）改写，保证 IR 解析与校验口径一致。
        rewrite_config = build_graph_code_rewrite_config(is_composite=True)
        tree, _syntax_rewrite_issues = rewrite_graph_code_syntax_sugars(
            tree,
            scope=scope,
            enable_shared_composite_sugars=rewrite_config.enable_shared_composite_sugars,
        )

        # 类格式复合节点：在解析前对类方法体中的 `[...]` 列表字面量做语法糖改写，
        # 将其等价转换为【拼装列表】节点调用，保证 IR 解析与校验口径一致。
        tree, _rewrite_issues = rewrite_graph_code_list_literals(
            tree,
            max_elements=rewrite_config.max_list_literal_elements,
        )
        # 类格式复合节点：字典字面量 `{k: v}` 语法糖改写，等价转换为【拼装字典】节点调用。
        tree, _dict_rewrite_issues = rewrite_graph_code_dict_literals(
            tree,
            max_pairs=rewrite_config.max_dict_literal_pairs,
        )
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
        
        from engine.layout.internal.layout_registry_context import LayoutRegistryContext
        from engine.configs.settings import Settings

        effective_workspace_path: Optional[Path] = self.workspace_path
        if effective_workspace_path is None:
            settings_workspace_root = getattr(Settings, "_workspace_root", None)
            if isinstance(settings_workspace_root, Path):
                effective_workspace_path = settings_workspace_root

        if effective_workspace_path is None:
            raise RuntimeError(
                "无法在复合节点解析阶段应用布局：workspace_path 未提供且 settings 未注入 workspace_root。"
                "请在调用 CompositeCodeParser 时显式传入 workspace_path，"
                "或在入口处调用 settings.set_config_path(workspace_path)。"
            )

        registry_context = LayoutRegistryContext.build_from_node_library(
            effective_workspace_path,
            node_library=self.node_library,
        )
        apply_layout_quietly(
            graph_model,
            node_library=self.node_library,
            registry_context=registry_context,
        )

        # 7.1 将虚拟引脚映射扩展到布局阶段创建的"数据节点副本"上，保持映射与最终子图一致
        self._propagate_virtual_pin_mappings_to_copies(virtual_pins, graph_model)

        # 7.2 虚拟引脚类型 → 子图端口类型覆盖（port_type_overrides）：
        # 类格式复合节点的子图内部通常不会显式生成“入口形参 → 节点端口”的数据连线，
        # 而是通过 VirtualPinConfig.mapped_ports 表达“外部引脚绑定到内部端口”的事实。
        # 为满足 strict 结构校验（禁止任何数据端口仍为泛型家族）与 UI 端口类型推断一致性，
        # 需要将虚拟引脚的 pin_type 回填为对应内部端口的类型覆盖。
        self._apply_virtual_pin_port_type_overrides(virtual_pins, graph_model)
        
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

    def _apply_virtual_pin_port_type_overrides(
        self,
        virtual_pins,
        graph_model,
    ) -> None:
        """将虚拟引脚类型写入子图 metadata.port_type_overrides。

        目的：
        - strict 结构校验要求子图内所有数据端口的有效类型必须可确定（禁止仍为泛型家族）；
        - 类格式复合节点的“入口形参/数据入引脚”通常不通过 data edge 建模，而是通过虚拟引脚映射表达；
        - 因此需要将 virtual_pins[].pin_type 回填到 mapped_ports 指向的内部端口，作为类型推断的稳定锚点。
        """
        if not virtual_pins or graph_model is None:
            return

        # 懒初始化 metadata
        metadata = getattr(graph_model, "metadata", None)
        if not isinstance(metadata, dict):
            graph_model.metadata = {}
            metadata = graph_model.metadata

        from engine.graph.port_type_effective_resolver import is_generic_type_name, safe_get_port_type_from_node_def

        overrides_raw = metadata.get("port_type_overrides")
        overrides: Dict[str, Dict[str, str]] = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}

        def _resolve_node_def_for_node(node) -> NodeDef | None:
            node_def_ref = getattr(node, "node_def_ref", None)
            if node_def_ref is None:
                return None
            kind = str(getattr(node_def_ref, "kind", "") or "").strip()
            key = str(getattr(node_def_ref, "key", "") or "").strip()
            if kind == "builtin":
                return self.node_library.get(key)
            if kind == "composite":
                # key 为 composite_id：node_library 的 key 可能为 canonical key，这里按 composite_id 回查一次
                for node_def in (self.node_library or {}).values():
                    if not getattr(node_def, "is_composite", False):
                        continue
                    if str(getattr(node_def, "composite_id", "") or "") == key:
                        return node_def
                return None
            return None

        for pin in list(virtual_pins or []):
            pin_type = str(getattr(pin, "pin_type", "") or "").strip()
            if (not pin_type) or is_generic_type_name(pin_type) or pin_type == "流程":
                continue

            mapped_ports = list(getattr(pin, "mapped_ports", None) or [])
            if not mapped_ports:
                continue

            for mapped in mapped_ports:
                if bool(getattr(mapped, "is_flow", False)):
                    continue
                node_id = str(getattr(mapped, "node_id", "") or "").strip()
                port_name = str(getattr(mapped, "port_name", "") or "").strip()
                if not node_id or not port_name:
                    continue

                # 若已有更具体覆盖则不重复写入
                existing_node_overrides = overrides.get(node_id)
                if isinstance(existing_node_overrides, dict):
                    existing = str(existing_node_overrides.get(port_name, "") or "").strip()
                    if existing and (not is_generic_type_name(existing)):
                        continue

                node = (getattr(graph_model, "nodes", None) or {}).get(node_id)
                node_def = _resolve_node_def_for_node(node) if node is not None else None
                is_input = bool(getattr(mapped, "is_input", True))
                declared = safe_get_port_type_from_node_def(node_def, port_name, is_input=is_input) if node_def is not None else ""
                if declared and (not is_generic_type_name(declared)):
                    # 已声明为具体类型的端口无需覆盖
                    continue

                node_overrides = dict(existing_node_overrides) if isinstance(existing_node_overrides, dict) else {}
                node_overrides[port_name] = pin_type
                overrides[node_id] = node_overrides

        if overrides:
            metadata["port_type_overrides"] = overrides

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
        return find_primary_composite_class(tree) is not None
    
    def _find_composite_class(self, tree: ast.Module) -> Optional[ast.ClassDef]:
        """查找带有 @composite_class 装饰器的类定义
        
        Args:
            tree: AST根节点
            
        Returns:
            类定义节点，如果未找到返回None
        """
        return find_primary_composite_class(tree)


