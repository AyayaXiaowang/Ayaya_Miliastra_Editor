"""
CodeToGraphParser（IR 管线版）

职责：仅作为 Graph Code → GraphModel 的编排器，不实现任何节点运行逻辑。
- AST 扫描、控制流建模、节点/端口构造、常量提取、嵌套调用展开、边路由、环境与校验均由 `engine.graph.ir.*` 提供。
- 节点来源完全由传入的 `node_library`/`NodeDef` 决定，调用方只能使用节点库中已经定义好的节点，本模块只做静态建模与布局。
"""
from __future__ import annotations

import ast
import uuid
from typing import Dict, Optional

from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.graph.common import apply_layout_quietly
from engine.graph.ir.ast_scanner import (
    find_graph_class as ir_find_graph_class,
    scan_event_methods as ir_scan_event_methods,
)
from engine.graph.ir.var_env import VarEnv
from engine.graph.ir.validators import Validators
from engine.graph.ir.node_factory import (
    FactoryContext as IRFactoryContext,
    create_event_node as ir_create_event_node,
    register_event_outputs as ir_register_event_outputs,
)
from engine.graph.ir.flow_builder import parse_method_body as ir_parse_method_body
from engine.graph.common import node_name_index_from_library
from engine.utils.logging.logger import log_info
from engine.graph.utils.composite_instance_utils import iter_composite_instance_pairs


class CodeToGraphParser:
    def __init__(self, node_library: Dict[str, NodeDef], verbose: bool = False):
        self.node_library = node_library
        self.verbose = verbose

        # 名称索引（统一构建，含同义/别名）
        self.node_name_index: Dict[str, str] = node_name_index_from_library(node_library)
        self._composite_defs_by_class: Dict[str, NodeDef] = {}
        for key, node_def in node_library.items():
            if getattr(node_def, "is_composite", False):
                self._composite_defs_by_class[node_def.name] = node_def
                if '/' in node_def.name:
                    self._composite_defs_by_class.setdefault(node_def.name.replace('/', ''), node_def)

        # IR 环境与上下文
        self._env = VarEnv()
        self._validators = Validators()
        self._factory_ctx = IRFactoryContext(
            node_library=self.node_library,
            node_name_index=self.node_name_index,
            verbose=self.verbose,
        )

    def _register_composite_instances(self, class_def: ast.ClassDef) -> None:
        """从 __init__ 中提取复合节点实例映射。"""
        for alias, class_name in iter_composite_instance_pairs(class_def):
            node_def = self._composite_defs_by_class.get(class_name)
            if not node_def:
                continue
            self._env.set_composite_instance(alias, node_def.composite_id)
            if self.verbose:
                log_info(
                    "  [复合节点] 识别实例: self.{} -> {} ({})",
                    alias,
                    node_def.name,
                    node_def.composite_id,
                )
    
    def parse_code(
        self,
        code: str,
        graph_name: str = "未命名节点图",
        *,
        tree: Optional[ast.Module] = None,
    ) -> GraphModel:
        if self.verbose:
            log_info("[CodeToGraphParser] 开始解析代码...")

        module = tree or ast.parse(code)

        # 清理复合节点实例映射，避免跨文件残留
        self._env.composite_instances.clear()

        graph_model = GraphModel()
        graph_model.graph_name = graph_name
        graph_model.graph_id = str(uuid.uuid4())

        class_def = ir_find_graph_class(module)
        if not class_def:
            raise ValueError("未找到节点图类定义")

        if self.verbose:
            log_info("  找到类定义: {}", class_def.name)

        # 提取复合节点实例映射（从 __init__ 方法）
        self._register_composite_instances(class_def)

        for event_ir in ir_scan_event_methods(class_def):
            event_name = event_ir.name
            method = event_ir.method_def

            # 重置事件上下文
            self._env.var_map.clear()
            self._env.node_sequence.clear()
            self._env.current_event_node = None

            event_node = ir_create_event_node(event_name, method, self._factory_ctx)
            # 记录事件节点的源码位置信息与顺序（用于稳定布局与块编号）
            event_node.source_lineno = getattr(method, "lineno", 0)
            event_node.source_end_lineno = getattr(method, "end_lineno", getattr(method, "lineno", 0))
            graph_model.event_flow_order.append(event_node.id)
            graph_model.event_flow_titles.append(event_name)
            graph_model.nodes[event_node.id] = event_node
            self._env.current_event_node = event_node

            ir_register_event_outputs(event_node, method, self._env)

            nodes, edges = ir_parse_method_body(
                method.body, event_node, graph_model, False, self._env, self._factory_ctx, self._validators
            )
            for n in nodes:
                graph_model.nodes[n.id] = n
            for e in edges:
                graph_model.edges[e.id] = e

        # 布局（调用点保持不变）
        apply_layout_quietly(graph_model)
        if self.verbose:
            log_info("[CodeToGraphParser] 自动布局完成")

        return graph_model



