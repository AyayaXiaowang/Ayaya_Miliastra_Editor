"""
CodeToGraphParser（IR 管线版）

职责：仅作为 Graph Code → GraphModel 的编排器，不实现任何节点运行逻辑。
- AST 扫描、控制流建模、节点/端口构造、常量提取、嵌套调用展开、边路由、环境与校验均由 `engine.graph.ir.*` 提供。
- 节点来源完全由传入的 `node_library`/`NodeDef` 决定，调用方只能使用节点库中已经定义好的节点，本模块只做静态建模与布局。
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path
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
    extract_constant_value,
    NOT_EXTRACTABLE,
)
from engine.graph.common import SIGNAL_LISTEN_NODE_TITLE, SIGNAL_NAME_PORT_NAME
from engine.graph.semantic import SEMANTIC_SIGNAL_ID_CONSTANT_KEY
from importlib import import_module


class CodeToGraphParser:
    def __init__(
        self,
        node_library: Dict[str, NodeDef],
        verbose: bool = False,
        *,
        workspace_path: Optional[Path] = None,
    ):
        self.node_library = node_library
        self.verbose = verbose
        self.workspace_path = workspace_path

        # 名称索引（统一构建，含同义/别名）。
        # 注意：该索引在 parse_code(...) 时会按 scope 重新构建，以支持 server/client 变体自动映射。
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

    def _reset_state_for_new_parse(self) -> None:
        """重置解析器的“跨文件/跨次解析不可共享”的状态。

        背景：
        - GraphLoader 会缓存 GraphCodeParser，而 GraphCodeParser 会复用同一个 CodeToGraphParser 实例；
        - 若 VarEnv / Validators 不在每次 parse 开始时清空，会导致“实时重解析”串用上一次解析的：
          - 方法体命名常量（local_const_values）
          - 局部变量句柄/持久映射（persistent_var_map）
          - 赋值分析缓存（assignment_counts / multi_assign_stack）
        进而出现循环体内【设置局部变量】建模位置漂移、以及常量回填错误等问题。
        """
        self._env = VarEnv()
        self._validators = Validators()

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
        scope: str = "server",
        folder_path: str = "",
    ) -> GraphModel:
        if self.verbose:
            log_info("[CodeToGraphParser] 开始解析代码...")

        # 重要：每次解析必须从干净状态开始，避免复用缓存解析器实例时串用旧的 VarEnv/Validators。
        self._reset_state_for_new_parse()

        # scope-aware 节点名索引：确保 client 节点图解析时能自动命中 `名称#client` 变体，
        # 避免误用 server 版本节点导致端口名不一致（UI 连线会被跳过）。
        normalized_scope = str(scope or "server").strip().lower()
        self.node_name_index = node_name_index_from_library(self.node_library, scope=normalized_scope)
        self._factory_ctx.node_name_index = self.node_name_index
        self._factory_ctx.graph_scope = normalized_scope
        self._factory_ctx.graph_folder_path = str(folder_path or "")

        module = tree or ast.parse(code)

        # 模块级命名常量上下文：供 extract_constant_value 在解析时引用。
        # 额外：支持“节点图类体内的类常量”通过 `self.<字段>`（尤其是 self._xxx）在调用参数中被静态提取，
        # 以便 UI 能正确回填到 node.input_constants（例如 定时器名称 / 变量名 等标识性参数）。
        clear_module_constants_context()
        module_constants = collect_module_constants(module)
        set_module_constants_context(module_constants)

        graph_model = GraphModel()
        graph_model.graph_name = graph_name
        graph_model.graph_id = str(uuid.uuid4())

        class_def = ir_find_graph_class(module)
        if not class_def:
            raise ValueError("未找到节点图类定义")

        # 收集节点图类体内的“类常量”，并注入到模块常量上下文中：
        # - 仅收集 class body 顶层的 AnnAssign/Assign，且右值可静态提取；
        # - 写入 key 为 "self.<字段名>"，用于 extract_constant_value 在解析 self.<字段> 时命中。
        class_self_constants: Dict[str, Any] = {}
        for stmt in list(getattr(class_def, "body", []) or []):
            if isinstance(stmt, ast.AnnAssign):
                target = getattr(stmt, "target", None)
                value_expr = getattr(stmt, "value", None)
                if isinstance(target, ast.Name) and isinstance(value_expr, ast.expr):
                    const_val = extract_constant_value(value_expr)
                    if const_val is not NOT_EXTRACTABLE:
                        class_self_constants[f"self.{target.id}"] = const_val
            elif isinstance(stmt, ast.Assign):
                targets = list(getattr(stmt, "targets", []) or [])
                value_expr = getattr(stmt, "value", None)
                if (
                    len(targets) == 1
                    and isinstance(targets[0], ast.Name)
                    and isinstance(value_expr, ast.expr)
                ):
                    const_val = extract_constant_value(value_expr)
                    if const_val is not NOT_EXTRACTABLE:
                        class_self_constants[f"self.{targets[0].id}"] = const_val

        if class_self_constants:
            merged_constants: Dict[str, Any] = dict(module_constants)
            merged_constants.update(class_self_constants)
            clear_module_constants_context()
            set_module_constants_context(merged_constants)

        if self.verbose:
            log_info("  找到类定义: {}", class_def.name)

        # 提取复合节点实例映射（从 __init__ 方法）
        self._register_composite_instances(class_def)
        composite_instances_snapshot = dict(self._env.composite_instances)

        # register_handlers 信号绑定映射：method_base_name -> literal
        handler_literal_by_method = ir_scan_register_handlers_bindings(class_def)

        # 信号仓库：用于识别 register_handlers 是否绑定到已定义信号，
        # 从而将对应事件节点表现为【监听信号】（不写入 signal_bindings）。
        signal_module = import_module("engine.signal")
        get_repo = getattr(signal_module, "get_default_signal_repository")
        signal_repo = get_repo()

        for event_ir in ir_scan_event_methods(class_def):
            event_name = event_ir.name
            method = event_ir.method_def

            # 重置事件上下文（不能复用上一个事件方法的 VarEnv 状态）：
            # - assignment_counts/local_const_values 等在 parse_method_body 内会被缓存用于递归解析；
            # - 若跨事件复用，会导致“局部变量建模/常量回填”错误地使用旧缓存。
            self._env = VarEnv()
            self._env.composite_instances = dict(composite_instances_snapshot)

            event_node = ir_create_event_node(event_name, method, self._factory_ctx)
            # 记录事件节点的源码位置信息与顺序（用于稳定布局与块编号）
            event_node.source_lineno = getattr(method, "lineno", 0)
            event_node.source_end_lineno = getattr(method, "end_lineno", getattr(method, "lineno", 0))

            # 下沉信号事件推导：若 register_handlers 里将该 on_<method> 绑定到了已定义信号，
            # 则将事件节点表现为【监听信号】并写入节点常量（由 GraphSemanticPass 统一生成 signal_bindings）。
            literal = handler_literal_by_method.get(event_name)
            if isinstance(literal, str) and literal.strip():
                resolved_id = str(literal).strip()
                resolved_payload: Any = None
                if signal_repo is not None:
                    resolved_payload = signal_repo.get_payload(resolved_id)
                    if not (isinstance(resolved_payload, dict) and resolved_payload):
                        resolved_by_name = signal_repo.resolve_id_by_name(resolved_id)
                        if resolved_by_name:
                            resolved_id = str(resolved_by_name)
                            resolved_payload = signal_repo.get_payload(resolved_id)
                if isinstance(resolved_payload, dict) and resolved_payload:
                    event_node.title = SIGNAL_LISTEN_NODE_TITLE
                    # 确保存在“信号名”输入端口（事件节点可能没有输入端口）
                    if not any(getattr(p, "name", "") == SIGNAL_NAME_PORT_NAME for p in (event_node.inputs or [])):
                        event_node.inputs = list(event_node.inputs or [])
                        event_node.inputs.append(PortModel(name=SIGNAL_NAME_PORT_NAME, is_input=True))
                    display_name = str(resolved_payload.get("signal_name") or "").strip()
                    event_node.input_constants.setdefault(SIGNAL_NAME_PORT_NAME, display_name or literal)
                    # 回填稳定 ID（隐藏常量），供 GraphSemanticPass 生成 metadata["signal_bindings"]
                    event_node.input_constants[SEMANTIC_SIGNAL_ID_CONSTANT_KEY] = str(resolved_id)

            graph_model.event_flow_order.append(event_node.id)
            graph_model.event_flow_titles.append(event_node.title)
            graph_model.nodes[event_node.id] = event_node
            self._env.current_event_node = event_node

            ir_register_event_outputs(event_node, method, self._env, graph_model=graph_model)

            nodes, edges = ir_parse_method_body(
                method.body, event_node, graph_model, False, self._env, self._factory_ctx, self._validators
            )
            for n in nodes:
                graph_model.nodes[n.id] = n
            for e in edges:
                graph_model.edges[e.id] = e

        # IR 解析过程中收集的告警/错误信息：用于上层做“严格模式（fail-closed）”判定或 UI 提示。
        if getattr(self._validators, "warnings", None):
            graph_model.metadata["ir_warnings"] = list(self._validators.warnings or [])
        if getattr(self._validators, "errors", None):
            graph_model.metadata["ir_errors"] = list(self._validators.errors or [])

        # 布局（调用点保持不变）
        apply_layout_quietly(graph_model, workspace_path=self.workspace_path)
        if self.verbose:
            log_info("[CodeToGraphParser] 自动布局完成")

        # 清理模块常量上下文，避免跨文件残留
        clear_module_constants_context()
        return graph_model



