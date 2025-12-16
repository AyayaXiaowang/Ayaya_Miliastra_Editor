"""
CodeToGraphParser（IR 管线版）

职责：仅作为 Graph Code → GraphModel 的编排器，不实现任何节点运行逻辑。
- AST 扫描、控制流建模、节点/端口构造、常量提取、嵌套调用展开、边路由、环境与校验均由 `engine.graph.ir.*` 提供。
- 节点来源完全由传入的 `node_library`/`NodeDef` 决定，调用方只能使用节点库中已经定义好的节点，本模块只做静态建模与布局。
"""
from __future__ import annotations

import ast
import uuid
from typing import Dict, Optional, Any, List

from engine.graph.models import GraphModel, NodeModel, PortModel
from engine.nodes.node_definition_loader import NodeDef
from engine.graph.common import apply_layout_quietly
from engine.graph.ir.ast_scanner import (
    find_graph_class as ir_find_graph_class,
    scan_event_methods as ir_scan_event_methods,
    scan_register_handlers_bindings as ir_scan_register_handlers_bindings,
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
from engine.graph.utils.ast_utils import (
    collect_module_constants,
    set_module_constants_context,
    clear_module_constants_context,
)
from engine.graph.common import SIGNAL_LISTEN_NODE_TITLE, SIGNAL_NAME_PORT_NAME
from importlib import import_module


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
        # 模块级命名常量上下文：供 extract_constant_value 在解析时引用
        clear_module_constants_context()
        set_module_constants_context(collect_module_constants(module))

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

        # register_handlers 信号绑定映射：method_base_name -> literal
        handler_literal_by_method = ir_scan_register_handlers_bindings(class_def)

        # 结构体索引：用于结构体节点绑定推导（一次构建，多处复用）
        if self._factory_ctx.struct_name_to_id is None or self._factory_ctx.struct_fields_by_id is None:
            from engine.resources.definition_schema_view import get_default_definition_schema_view

            schema_view = get_default_definition_schema_view()
            all_structs = schema_view.get_all_struct_definitions() or {}
            struct_name_to_id: Dict[str, str] = {}
            struct_fields_by_id: Dict[str, List[str]] = {}
            for struct_id, payload in all_structs.items():
                if not isinstance(struct_id, str) or not isinstance(payload, dict):
                    continue
                name_raw = payload.get("name")
                struct_name = str(name_raw).strip() if isinstance(name_raw, str) else ""
                if struct_name:
                    struct_name_to_id[struct_name] = struct_id
                struct_name_to_id[struct_id] = struct_id
                defined_fields: List[str] = []
                value_entries = payload.get("value")
                if isinstance(value_entries, list):
                    for entry in value_entries:
                        if not isinstance(entry, dict):
                            continue
                        raw_key = entry.get("key")
                        field_name = str(raw_key).strip() if isinstance(raw_key, str) else ""
                        if field_name and field_name not in defined_fields:
                            defined_fields.append(field_name)
                struct_fields_by_id[struct_id] = defined_fields

            self._factory_ctx.struct_name_to_id = struct_name_to_id
            self._factory_ctx.struct_fields_by_id = struct_fields_by_id

        # 信号仓库：供事件节点与发送信号节点推导稳定 signal_id
        if self._factory_ctx.signal_repo is None:
            signal_module = import_module("engine.signal")
            get_repo = getattr(signal_module, "get_default_signal_repository")
            self._factory_ctx.signal_repo = get_repo()

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

            # 下沉信号事件推导：若 register_handlers 里将该 on_<method> 绑定到了已定义信号，
            # 则将事件节点表现为【监听信号】并写入 signal_bindings。
            literal = handler_literal_by_method.get(event_name)
            if isinstance(literal, str) and literal.strip():
                repo = self._factory_ctx.signal_repo
                resolved_id = str(literal).strip()
                resolved_payload: Any = None
                if repo is not None:
                    resolved_payload = repo.get_payload(resolved_id)
                    if not (isinstance(resolved_payload, dict) and resolved_payload):
                        resolved_by_name = repo.resolve_id_by_name(resolved_id)
                        if resolved_by_name:
                            resolved_id = str(resolved_by_name)
                            resolved_payload = repo.get_payload(resolved_id)
                if isinstance(resolved_payload, dict) and resolved_payload:
                    event_node.title = SIGNAL_LISTEN_NODE_TITLE
                    # 确保存在“信号名”输入端口（事件节点可能没有输入端口）
                    if not any(getattr(p, "name", "") == SIGNAL_NAME_PORT_NAME for p in (event_node.inputs or [])):
                        event_node.inputs = list(event_node.inputs or [])
                        event_node.inputs.append(PortModel(name=SIGNAL_NAME_PORT_NAME, is_input=True))
                    display_name = str(resolved_payload.get("signal_name") or "").strip()
                    event_node.input_constants.setdefault(SIGNAL_NAME_PORT_NAME, display_name or literal)
                    if not graph_model.get_node_signal_id(event_node.id):
                        graph_model.set_node_signal_binding(event_node.id, resolved_id)

            graph_model.event_flow_order.append(event_node.id)
            graph_model.event_flow_titles.append(event_node.title)
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

        # 清理模块常量上下文，避免跨文件残留
        clear_module_constants_context()
        return graph_model



