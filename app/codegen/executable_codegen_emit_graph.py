from __future__ import annotations

import re
from typing import Dict, List, Tuple

from engine.graph.common import (
    format_constant,
    group_by_event_with_topo_order as group_by_event,
    is_flow_port,
)
from engine.graph.ir.event_utils import get_event_param_names_from_node
from engine.graph.models import GraphModel, NodeModel
from engine.utils.name_utils import make_valid_identifier


class _ExecutableCodegenEmitGraphMixin:
    def _generate_graph_class(self, graph_model: GraphModel) -> List[str]:
        options = self.options
        lines: List[str] = []

        class_name = self._sanitize_class_name(graph_model.graph_name)
        if options.enable_auto_validate:
            lines.append("@validate_node_graph")
        lines.append(f"class {class_name}:")
        lines.append(f'    """节点图类：{graph_model.graph_name}"""')
        lines.append("")

        lines.append("    def __init__(self, game: GameRuntime, owner_entity):")
        lines.append('        """初始化节点图')
        lines.append("        ")
        lines.append("        Args:")
        lines.append("            game: 游戏运行时")
        lines.append("            owner_entity: 挂载的实体（自身实体）")
        lines.append('        """')
        lines.append("        self.game = game")
        lines.append("        self.owner_entity = owner_entity")
        lines.append("")

        event_flows = self._group_nodes_by_event(graph_model, verbose=False)
        if event_flows:
            for event_node_id, flow_nodes in event_flows.items():
                event_node = graph_model.nodes[event_node_id]
                lines.extend(self._generate_event_handler_method(event_node, flow_nodes, graph_model))
                lines.append("")
            lines.extend(self._generate_register_handlers(event_flows, graph_model))
            return lines

        # 新建空图/缺少事件节点的兜底：仍需生成至少一个 on_ 入口，保证解析与校验闭环可用。
        lines.extend(self._generate_default_event_stub())
        lines.append("")
        lines.extend(self._generate_default_register_handlers())
        return lines

    def _generate_default_event_stub(self) -> List[str]:
        """当图中没有任何事件流时，生成一个最小可用的默认事件入口。"""
        scope = self._ensure_graph_scope()
        if scope == "client":
            return [
                "    def on_节点图开始(self):",
                '        """事件处理器：节点图开始（新建模板默认入口）"""',
                "        节点图开始(self.game)",
                "        return",
            ]
        # server
        return [
            "    def on_实体创建时(self, 事件源实体, 事件源GUID):",
            '        """事件处理器：实体创建时（新建模板默认入口）"""',
            "        占位_局部变量句柄, 占位_局部变量值 = 获取局部变量(self.game, 初始值=0)",
            "        设置局部变量(self.game, 局部变量=占位_局部变量句柄, 值=占位_局部变量值)",
            "        return",
        ]

    def _generate_default_register_handlers(self) -> List[str]:
        """为默认事件入口生成最小 register_handlers。"""
        scope = self._ensure_graph_scope()
        if scope == "client":
            return [
                "    def register_handlers(self):",
                "        # client 节点图由运行时统一调用 on_节点图开始，不需要显式 register_event_handler",
                "        return",
            ]
        return [
            "    def register_handlers(self):",
            "        self.game.register_event_handler(",
            "            '实体创建时',",
            "            self.on_实体创建时,",
            "            owner=self.owner_entity,",
            "        )",
        ]

    def _generate_event_handler_method(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
    ) -> List[str]:
        lines: List[str] = []
        event_name = self._signal_codegen.get_event_name_for_node(graph_model, event_node.id) or event_node.title
        handler_suffix = make_valid_identifier(event_name)
        if not handler_suffix:
            handler_suffix = "event"

        if self._signal_codegen.is_signal_listen_node(event_node):
            lines.append(f"    def on_{handler_suffix}(self, **event_kwargs):")
        else:
            param_names = get_event_param_names_from_node(event_node)
            signature_parts = ["self", *param_names]
            lines.append(f"    def on_{handler_suffix}({', '.join(signature_parts)}):")

        lines.append(f'        """事件处理器：{event_name}"""')

        use_event_kwargs = self._signal_codegen.is_signal_listen_node(event_node)
        body_lines = self._generate_event_flow_body(
            event_node,
            flow_nodes,
            graph_model,
            use_event_kwargs=use_event_kwargs,
        )

        if not body_lines or all(not line.strip() for line in body_lines):
            lines.append("        pass")
            return lines

        for line in body_lines:
            if line:
                lines.append("        " + line)
            else:
                lines.append("")
        return lines

    def _get_event_output_params(self, event_node: NodeModel) -> List[str]:
        # 注意：SignalCodegenAdapter.build_listen_signal_output_mapping 期望的是“数据输出端口对应的方法参数名列表”
        return get_event_param_names_from_node(event_node)

    def _generate_event_flow_body(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
        *,
        use_event_kwargs: bool = False,
    ) -> List[str]:
        lines: List[str] = []
        var_mapping: Dict[Tuple[str, str], str] = {}
        var_types: Dict[str, str] = {}

        # 每个事件方法独立维护“类型化常量变量”缓存（避免跨事件污染）
        self._reset_typed_constant_state_for_event()

        graph_variable_types: Dict[str, str] = {}
        for entry in getattr(graph_model, "graph_variables", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            var_type = str(entry.get("variable_type") or "").strip()
            if name and var_type:
                graph_variable_types[name] = var_type

        event_params = self._get_event_output_params(event_node)
        event_mapping = self._signal_codegen.build_listen_signal_output_mapping(
            event_node,
            use_event_kwargs=use_event_kwargs,
            event_param_names=event_params,
        )
        var_mapping.update(event_mapping)

        # 预扫描：建立 “int 常量 → (GUID/配置ID/元件ID)” 的推断映射。
        # 说明：仅当该 int 常量在至少一个明确类型端口出现时才会被纳入，避免将大量 0/1/序号误判为 ID。
        self._typed_const_type_by_int_value = self._infer_typed_constant_int_types_for_event(
            flow_nodes,
            graph_model,
            special_types={"GUID", "配置ID", "元件ID"},
        )

        # 基于 flow edges 生成结构化控制流（支持：双分支 if/else + 多分支 match-case）。
        from engine.graph.models import EdgeModel

        def _indent_block(body: List[str]) -> List[str]:
            if not body:
                return ["    pass"]
            return [("    " + line) if line else "" for line in body]

        def _has_flow_input(node: NodeModel) -> bool:
            return any(is_flow_port(node, p.name, False) for p in (node.inputs or []))

        # 索引：flow/data 入边
        flow_next: Dict[Tuple[str, str], str] = {}
        data_in_edges: Dict[str, List[EdgeModel]] = {}
        for edge in graph_model.edges.values():
            src_node = graph_model.nodes.get(edge.src_node)
            dst_node = graph_model.nodes.get(edge.dst_node)
            if src_node is None or dst_node is None:
                continue

            if is_flow_port(src_node, edge.src_port, True) and is_flow_port(dst_node, edge.dst_port, False):
                key = (edge.src_node, edge.src_port)
                if key in flow_next and flow_next[key] != edge.dst_node:
                    raise ValueError(
                        f"flow edge ambiguity: src={edge.src_node}.{edge.src_port} "
                        f"-> {flow_next[key]!r} / {edge.dst_node!r}"
                    )
                flow_next[key] = edge.dst_node
                continue

            if not is_flow_port(dst_node, edge.dst_port, False):
                data_in_edges.setdefault(edge.dst_node, []).append(edge)

        generated_nodes: set[str] = {event_node.id}

        def _ensure_data_deps(node_id: str) -> List[str]:
            """确保 node_id 的数据依赖节点已生成（仅生成“无流程入”的节点）。"""
            out_lines: List[str] = []
            for e in data_in_edges.get(node_id, []):
                src_id = str(e.src_node)
                if src_id == event_node.id:
                    continue
                if src_id in generated_nodes:
                    continue
                src_node = graph_model.nodes.get(src_id)
                if src_node is None:
                    continue
                if _has_flow_input(src_node):
                    raise ValueError(
                        f"data dependency requires a flow node that has not executed yet: "
                        f"dst={node_id!r} depends_on={src_id!r}({src_node.title})"
                    )
                out_lines.extend(_ensure_data_deps(src_id))
                out_lines.extend(
                    self._generate_node_call(
                        src_node,
                        graph_model,
                        var_mapping,
                        var_types=var_types,
                        graph_variable_types=graph_variable_types,
                    )
                )
                generated_nodes.add(src_id)
            return out_lines

        def _pick_flow_dst(src_id: str, port_name: str) -> str:
            dst = flow_next.get((src_id, port_name))
            return str(dst) if dst else ""

        def _render_match_case_label(port_name: str, *, prefer_int: bool) -> str:
            text = str(port_name or "").strip()
            if prefer_int and re.fullmatch(r"-?\d+", text):
                return str(int(text))
            return format_constant(text)

        def _emit_flow_chain(start_node_id: str) -> List[str]:
            node_id = str(start_node_id or "").strip()
            if not node_id:
                return []
            if node_id in generated_nodes:
                return []
            node = graph_model.nodes.get(node_id)
            if node is None:
                return []

            node_title = str(getattr(node, "title", "") or "").strip()

            # 双分支：生成 if/else
            if node_title == "双分支":
                branch_pre: List[str] = []
                branch_pre.extend(_ensure_data_deps(node_id))

                input_params = self._collect_input_params(node, graph_model, var_mapping)
                cond_expr = input_params.get("条件", "False")

                generated_nodes.add(node_id)

                true_start = _pick_flow_dst(node_id, "是")
                false_start = _pick_flow_dst(node_id, "否")

                # 将分支体入口节点所需的“数据依赖节点（无流程入）”提升到 if/else 之前，
                # 避免出现“仅在某个分支内生成了局部变量句柄，但另一分支仍引用该句柄”的 Unbound 情况。
                if true_start:
                    branch_pre.extend(_ensure_data_deps(true_start))
                if false_start:
                    branch_pre.extend(_ensure_data_deps(false_start))

                true_body = _emit_flow_chain(true_start) if true_start else []
                false_body = _emit_flow_chain(false_start) if false_start else []

                branch_out: List[str] = []
                branch_out.extend(branch_pre)
                branch_out.append(f"if {cond_expr}:")
                branch_out.extend(_indent_block(true_body))
                branch_out.append("else:")
                branch_out.extend(_indent_block(false_body))
                return branch_out

            # 多分支：生成 match-case（端口名约定：默认=“默认”，其余输出口为 str(case_value)）
            if node_title == "多分支":
                match_pre: List[str] = []
                match_pre.extend(_ensure_data_deps(node_id))

                input_params = self._collect_input_params(node, graph_model, var_mapping)
                subject_expr = input_params.get("控制表达式", "0")

                generated_nodes.add(node_id)

                # case 类型推断：若全部分支口名均为整数文本，则按 int 输出；否则按字符串输出
                case_ports = [
                    str(p.name)
                    for p in (node.outputs or [])
                    if is_flow_port(node, p.name, True) and str(p.name) != "默认"
                ]
                prefer_int = bool(case_ports) and all(re.fullmatch(r"-?\d+", p) for p in case_ports)

                for port_name in [*case_ports, "默认"]:
                    branch_start = _pick_flow_dst(node_id, port_name)
                    if branch_start:
                        match_pre.extend(_ensure_data_deps(branch_start))

                match_out: List[str] = []
                match_out.extend(match_pre)
                match_out.append(f"match {subject_expr}:")
                for port_name in case_ports:
                    match_out.append(f"    case {_render_match_case_label(port_name, prefer_int=prefer_int)}:")
                    branch_start = _pick_flow_dst(node_id, port_name)
                    match_out.extend(_indent_block(_emit_flow_chain(branch_start) if branch_start else []))
                match_out.append("    case _:")  # 默认分支
                default_start = _pick_flow_dst(node_id, "默认")
                match_out.extend(_indent_block(_emit_flow_chain(default_start) if default_start else []))
                return match_out

            # 普通流程节点：顺序生成调用，并沿默认流程口继续
            out_lines: List[str] = []
            out_lines.extend(_ensure_data_deps(node_id))
            out_lines.extend(
                self._generate_node_call(
                    node,
                    graph_model,
                    var_mapping,
                    var_types=var_types,
                    graph_variable_types=graph_variable_types,
                )
            )
            generated_nodes.add(node_id)

            next_id = _pick_flow_dst(node_id, "流程出")
            if not next_id:
                # 回退：选择第一个可用的流程输出口
                for p in (node.outputs or []):
                    if is_flow_port(node, p.name, True):
                        next_id = _pick_flow_dst(node_id, str(p.name))
                        if next_id:
                            break
            if next_id:
                out_lines.extend(_emit_flow_chain(next_id))
            return out_lines

        # 事件节点的默认流程出口：优先 流程出，否则取第一个流程输出口
        start_flow = _pick_flow_dst(event_node.id, "流程出")
        if not start_flow:
            for p in (event_node.outputs or []):
                if is_flow_port(event_node, p.name, True):
                    start_flow = _pick_flow_dst(event_node.id, str(p.name))
                    if start_flow:
                        break

        if start_flow:
            lines.extend(_emit_flow_chain(start_flow))
        return lines

    def _group_nodes_by_event(self, graph_model: GraphModel, verbose: bool = False) -> Dict[str, List[str]]:
        """按事件对图进行分组（用于生成多个 on_* 事件方法）。

        说明：
        - engine 层的 `group_by_event_with_topo_order` 主要依赖“事件节点”分类来识别事件入口；
        - client 图的入口节点【节点图开始】在资源库中属于“其他节点”，因此需要在 codegen 层做一次兜底识别，
          否则会误判为“无事件流”，退化到默认空图模板（从而丢失真实流程）。
        """
        flows = group_by_event(graph_model, include_data_dependencies=True)
        if flows:
            if verbose:
                print(f"  找到 {len(flows)} 个事件流")
            return flows

        scope = self._ensure_graph_scope()
        if scope != "client":
            if verbose:
                print("  未找到事件流（非 client scope），将回退到默认事件入口模板")
            return flows

        # client 兜底：将【节点图开始】视作事件入口
        start_nodes = [n for n in graph_model.nodes.values() if str(getattr(n, "title", "") or "") == "节点图开始"]
        if not start_nodes:
            if verbose:
                print("  未找到事件流且不存在【节点图开始】节点，回退到默认事件入口模板")
            return flows
        if len(start_nodes) != 1:
            raise ValueError(f"client 图存在多个【节点图开始】节点，无法确定事件入口：{len(start_nodes)}")

        event_node = start_nodes[0]

        # 计算该事件下的可达节点集合（用于类型化常量预扫描等）
        from engine.graph.models import EdgeModel

        flow_out: Dict[str, List[Tuple[str, str]]] = {}
        for edge in graph_model.edges.values():
            if not isinstance(edge, EdgeModel):
                continue
            src_node = graph_model.nodes.get(edge.src_node)
            dst_node = graph_model.nodes.get(edge.dst_node)
            if src_node is None or dst_node is None:
                continue
            if is_flow_port(src_node, edge.src_port, True) and is_flow_port(dst_node, edge.dst_port, False):
                flow_out.setdefault(str(edge.src_node), []).append((str(edge.src_port), str(edge.dst_node)))

        def _flow_port_sort_key(port_name: str) -> Tuple[int, str]:
            if port_name == "流程出":
                return (0, port_name)
            if port_name == "是":
                return (1, port_name)
            if port_name == "否":
                return (2, port_name)
            return (10, port_name)

        visited: set[str] = set()
        ordered: List[str] = []

        def _dfs(node_id: str) -> None:
            nid = str(node_id)
            if nid in visited:
                return
            visited.add(nid)
            ordered.append(nid)
            nexts = sorted(flow_out.get(nid, []), key=lambda it: _flow_port_sort_key(it[0]))
            for _port, dst in nexts:
                _dfs(dst)

        _dfs(event_node.id)
        return {event_node.id: ordered}

    def _generate_register_handlers(
        self,
        event_flows: Dict[str, List[str]],
        graph_model: GraphModel,
    ) -> List[str]:
        # client 节点图：运行时统一调用 on_节点图开始，不需要显式 register_event_handler。
        scope = self._ensure_graph_scope()
        if scope == "client":
            return [
                "    def register_handlers(self):",
                "        # client 节点图由运行时统一调用 on_节点图开始，不需要显式 register_event_handler",
                "        return",
            ]

        lines: List[str] = []
        lines.append("    def register_handlers(self):")
        lines.append('        """注册所有事件处理器"""')

        if not event_flows:
            lines.append("        pass")
            return lines

        for event_node_id in event_flows:
            event_name = self._signal_codegen.get_event_name_for_node(graph_model, event_node_id)
            handler_suffix = make_valid_identifier(event_name)
            if not handler_suffix:
                handler_suffix = "event"
            lines.append("        self.game.register_event_handler(")
            lines.append(f'            "{event_name}",')
            lines.append(f"            self.on_{handler_suffix},")
            lines.append("            owner=self.owner_entity")
            lines.append("        )")

        return lines


__all__ = ["_ExecutableCodegenEmitGraphMixin"]

