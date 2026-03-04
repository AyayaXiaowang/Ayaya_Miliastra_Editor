from __future__ import annotations

from collections import deque
import keyword
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from engine.graph.common import (
    LOOP_NODE_NAMES,
    format_constant,
)
from engine.graph.port_type_effective_resolver import (
    EffectivePortTypeResolver,
    build_port_type_overrides,
)
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.type_registry import TYPE_FLOAT, TYPE_INTEGER
from engine.utils.name_utils import make_valid_identifier

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    ReverseGraphCodeOptions,
    _COPY_MARKER,
    _is_data_node_copy,
    _is_layout_artifact_node_id,
    _is_local_var_relay_node_id,
    _resolve_node_def,
    _strip_copy_suffix,
    _try_resolve_node_def,
)

_ARITHMETIC_OPERATOR_BY_TITLE: Mapping[str, str] = {
    "加法运算": "+",
    "减法运算": "-",
    "乘法运算": "*",
    "除法运算": "/",
}
_NUMERIC_TYPES: set[str] = {TYPE_INTEGER, TYPE_FLOAT}


def _render_node_call_args(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
    var_mapping: Mapping[Tuple[str, str], str],
) -> List[str]:
    """渲染节点调用参数（不包含 self.game）。"""
    # 仅输出“有数据连线或有输入常量”的端口；缺省保持省略，以便 NodeDef.input_defaults 生效。
    provided: List[Tuple[str, str]] = []
    for port in (node.inputs or []):
        port_name = str(getattr(port, "name", "") or "")
        if not port_name:
            continue
        if is_flow_port_with_context(node, port_name, False, node_library):
            continue
        expr = None
        source = data_in_edge.get((node.id, port_name))
        if source is not None:
            expr = var_mapping.get((source[0], source[1]))
            if expr is None:
                raise ReverseGraphCodeError(
                    f"无法解析数据来源变量：{node.title}.{port_name} 来自 {source}"
                )
        elif port_name in (node.input_constants or {}):
            expr = format_constant((node.input_constants or {}).get(port_name))
        else:
            continue
        provided.append((port_name, expr))

    # 参数输出策略：
    # - 优先关键字参数（可读、避免跳位）；
    # - 若端口名不可作为 keyword，则尝试用位置参数（要求“从0开始连续提供”）。
    keyword_args: List[str] = []
    positional_args: List[str] = []

    provided_map = {k: v for k, v in provided}
    inputs_in_order = [str(x) for x in list(getattr(node_def, "inputs", []) or [])]

    def _is_kw(name: str) -> bool:
        return bool(name) and name.isidentifier() and (not keyword.iskeyword(name))

    # 若存在不可作为 keyword 的端口名，则必须转为 positional，并要求不跳位
    needs_positional = any((not _is_kw(name)) for name in provided_map.keys())
    if not needs_positional:
        for port_name in inputs_in_order:
            if port_name in provided_map:
                keyword_args.append(f"{port_name}={provided_map[port_name]}")
        # 对于动态输入端口（不在 NodeDef.inputs 中），按 node.inputs 顺序追加（稳定）
        for port_name, expr in provided:
            if port_name in inputs_in_order:
                continue
            keyword_args.append(f"{port_name}={expr}")
        return keyword_args

    # 情况 A：动态数字端口（典型：拼装列表/拼装字典等变参节点），NodeDef.inputs 仅含占位符，实际端口按位置生成
    non_kw_names = [name for name in provided_map.keys() if not _is_kw(name)]
    if non_kw_names and all(str(name).isdigit() for name in non_kw_names):
        numeric_ports = sorted({int(str(name)) for name in non_kw_names})
        if numeric_ports and numeric_ports[0] != 0:
            raise ReverseGraphCodeError(
                f"节点 {node.title} 的数字端口必须从 0 开始连续提供，但当前最小端口为 {numeric_ports[0]}"
            )
        for expected in range(0, (numeric_ports[-1] if numeric_ports else -1) + 1):
            key = str(expected)
            if key not in provided_map:
                raise ReverseGraphCodeError(
                    f"节点 {node.title} 的数字端口必须连续提供（缺少 {key!r}），无法生成位置参数"
                )
            positional_args.append(provided_map[key])

        # 其余（可关键字）端口按 NodeDef.inputs 顺序追加为 keyword，避免跳位
        for port_name in inputs_in_order:
            if port_name in provided_map and _is_kw(port_name):
                keyword_args.append(f"{port_name}={provided_map[port_name]}")
        for port_name, expr in provided:
            if port_name in inputs_in_order or port_name.isdigit():
                continue
            if not _is_kw(port_name):
                raise ReverseGraphCodeError(
                    f"节点 {node.title} 的动态端口名不可作为关键字参数：{port_name!r}"
                )
            keyword_args.append(f"{port_name}={expr}")
        return positional_args + keyword_args

    # 情况 B：静态端口中出现不可 keyword 的名称（极少见），尝试按 NodeDef.inputs 位置表达，且不允许跳位
    max_index = -1
    for idx, name in enumerate(inputs_in_order):
        if name in provided_map and (not _is_kw(name)):
            max_index = max(max_index, idx)
    if max_index < 0:
        raise ReverseGraphCodeError(
            f"节点 {node.title} 存在不可关键字参数的动态端口，且无法按位置参数表达"
        )

    for idx in range(0, max_index + 1):
        port_name = inputs_in_order[idx]
        if port_name not in provided_map:
            raise ReverseGraphCodeError(
                f"节点 {node.title} 需要以位置参数表达端口 {inputs_in_order[max_index]!r}，"
                f"但其前置端口 {port_name!r} 缺少数据来源/常量，无法不跳位生成"
            )
        positional_args.append(provided_map[port_name])

    for port_name in inputs_in_order[max_index + 1 :]:
        if port_name in provided_map:
            keyword_args.append(f"{port_name}={provided_map[port_name]}")

    # 动态端口：只能在 keyword 区域表达（若不可关键字则在上面已报错）
    for port_name, expr in provided:
        if port_name in inputs_in_order:
            continue
        if not _is_kw(port_name):
            raise ReverseGraphCodeError(
                f"节点 {node.title} 的动态端口名不可作为关键字参数：{port_name!r}"
            )
        keyword_args.append(f"{port_name}={expr}")

    return positional_args + keyword_args


class _StructuredEventEmitter:
    """按流程边结构化生成事件方法体（支持 if/match/for/break + 复合节点多流程出口 match）。"""

    def __init__(
        self,
        *,
        model: GraphModel,
        member_set: set[str],
        node_library: Dict[str, NodeDef],
        node_name_index: Dict[str, str],
        call_name_candidates_by_identity: Dict[int, List[str]],
        composite_alias_by_id: Dict[str, str],
        options: ReverseGraphCodeOptions,
    ) -> None:
        self.model = model
        self.member_set = set(member_set)
        self.node_library = node_library
        self.node_name_index = node_name_index
        self.call_name_candidates_by_identity = call_name_candidates_by_identity
        self.composite_alias_by_id = dict(composite_alias_by_id or {})
        self._composite_entry_method_name: str = "执行"
        self.options = options

        self._port_type_resolver = EffectivePortTypeResolver(
            self.model,
            node_def_resolver=lambda node_obj: _resolve_node_def(node=node_obj, node_library=self.node_library),
            port_type_overrides=build_port_type_overrides(self.model),
        )

        # (dst_node, dst_port) -> (src_node, src_port)
        self.data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        # src_node -> [(src_port, dst_node, dst_port), ...]（仅流程边）
        self.flow_out: Dict[str, List[Tuple[str, str, str]]] = {}
        # (src_node, src_port) -> (dst_node, dst_port)
        self.flow_out_by_port: Dict[Tuple[str, str], Tuple[str, str]] = {}

        self._build_edge_indices()

        self.emitted_nodes: set[str] = set()

    def _is_flow_port(self, node: NodeModel, port_name: str, is_source: bool) -> bool:
        return is_flow_port_with_context(node, port_name, is_source, self.node_library)

    def _resolve_data_source(
        self,
        src_node_id: str,
        src_port: str,
        *,
        raw_data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
        depth: int = 0,
    ) -> Tuple[str, str]:
        """对 data edge 的源端做归一化：
        - data copy 节点 → canonical original id
        - localvar relay 节点（node_localvar_relay_block_*）的 `值` 输出 → 透传其 `初始值` 上游来源
        """
        if depth > 50:
            return str(src_node_id), str(src_port)

        src_id = str(src_node_id)
        port = str(src_port)
        node = self.model.nodes.get(src_id)
        if node is not None:
            if _is_data_node_copy(node) or (_COPY_MARKER in src_id):
                candidate = str(getattr(node, "original_node_id", "") or "") or src_id
                canonical = _strip_copy_suffix(candidate)
                if canonical and canonical != src_id:
                    return self._resolve_data_source(
                        canonical,
                        port,
                        raw_data_in_edge=raw_data_in_edge,
                        depth=depth + 1,
                    )

        if _is_local_var_relay_node_id(src_id) and port == "值":
            upstream = raw_data_in_edge.get((src_id, "初始值"))
            if upstream is not None:
                return self._resolve_data_source(
                    upstream[0],
                    upstream[1],
                    raw_data_in_edge=raw_data_in_edge,
                    depth=depth + 1,
                )

        return src_id, port

    def _build_edge_indices(self) -> None:
        raw_data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for edge in (getattr(self.model, "edges", None) or {}).values():
            if edge.dst_node not in self.member_set:
                continue
            if edge.src_node not in self.member_set:
                continue
            dst_node = self.model.nodes.get(edge.dst_node)
            src_node = self.model.nodes.get(edge.src_node)
            if dst_node is None or src_node is None:
                continue

            src_is_flow = self._is_flow_port(src_node, str(edge.src_port), True)
            dst_is_flow = self._is_flow_port(dst_node, str(edge.dst_port), False)

            if src_is_flow and dst_is_flow:
                self.flow_out.setdefault(edge.src_node, []).append(
                    (str(edge.src_port), str(edge.dst_node), str(edge.dst_port))
                )
                key = (str(edge.src_node), str(edge.src_port))
                if key in self.flow_out_by_port:
                    raise ReverseGraphCodeError(
                        f"同一流程输出端口存在多条流程连线：{src_node.title}.{edge.src_port}"
                    )
                self.flow_out_by_port[key] = (str(edge.dst_node), str(edge.dst_port))
                continue

            if (not src_is_flow) and (not dst_is_flow):
                key2 = (str(edge.dst_node), str(edge.dst_port))
                if key2 in raw_data_in_edge:
                    raise ReverseGraphCodeError(
                        f"输入端口存在多条数据连线：{dst_node.title}.{edge.dst_port}"
                    )
                raw_data_in_edge[key2] = (str(edge.src_node), str(edge.src_port))

        # 归一化 data_in_edge：剔除 layout relay / data copy 的影响（避免反向生成把布局结构写成真实语义节点）
        for (dst_node_id, dst_port), (src_node_id, src_port) in raw_data_in_edge.items():
            resolved_src = self._resolve_data_source(
                str(src_node_id),
                str(src_port),
                raw_data_in_edge=raw_data_in_edge,
            )
            self.data_in_edge[(str(dst_node_id), str(dst_port))] = resolved_src

    def emit_event_body(
        self,
        *,
        out_lines: List[str],
        event_node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> Optional[str]:
        visited_flow: set[str] = set()

        # 事件主入口：event.流程出 -> ...
        entry = self.flow_out_by_port.get((str(event_node.id), "流程出"))
        if entry is not None:
            start_node, start_port = entry
            if start_port == "跳出循环":
                raise ReverseGraphCodeError("事件入口不应直接连到循环的跳出循环端口")
            self._emit_flow_sequence(
                out_lines=out_lines,
                start_node_id=start_node,
                stop_node_id=None,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=[],
                visited_flow=visited_flow,
            )

        # 额外流程入口：
        # 有些图（尤其是 client 校准/布局图）会在同一事件方法内放置“无流程入”的流程入口节点，
        # 它们与事件主入口不连通，但仍属于图的一部分。这里按 member_set 扫描并补发这些入口序列。
        def _is_flow_entry_node(node: NodeModel) -> bool:
            has_flow_out = any(
                (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))
                for p in (getattr(node, "outputs", None) or [])
            )
            has_flow_in = any(
                (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), False))
                for p in (getattr(node, "inputs", None) or [])
            )
            return bool(has_flow_out and (not has_flow_in))

        extra_roots: List[str] = []
        for node_id in sorted(self.member_set):
            if str(node_id) == str(getattr(event_node, "id", "") or ""):
                continue
            if node_id in self.emitted_nodes:
                continue
            node = self.model.nodes.get(str(node_id))
            if node is None:
                continue
            if str(getattr(node, "category", "") or "") == "事件节点":
                continue
            if _is_flow_entry_node(node):
                extra_roots.append(str(node_id))

        for root_id in extra_roots:
            self._emit_flow_sequence(
                out_lines=out_lines,
                start_node_id=root_id,
                stop_node_id=None,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=[],
                visited_flow=visited_flow,
            )

        # client 过滤器节点图：return <值> 会被解析为 graph_end（节点图结束）节点。
        # 对这种“无流程、纯数据链”的图，需要在这里补发数据节点，并将返回表达式交给上层写入 `return <expr>`。
        graph_end_nodes: List[NodeModel] = []
        for nid in self.member_set:
            node = self.model.nodes.get(str(nid))
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=str(nid), node=node):
                continue
            if str(getattr(node, "id", "") or "").startswith("graph_end_"):
                graph_end_nodes.append(node)
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                graph_end_nodes.append(node)

        return_expr: Optional[str] = None
        if graph_end_nodes:
            if len(graph_end_nodes) > 1:
                raise ReverseGraphCodeError(
                    "同一事件内存在多个节点图结束（graph_end）节点，无法稳定反向生成 return："
                    + ", ".join(str(getattr(n, "id", "") or "") for n in graph_end_nodes[:5])
                    + ("..." if len(graph_end_nodes) > 5 else "")
                )
            end_node = graph_end_nodes[0]
            expr = self._expr_for_optional_data_input(
                node_id=str(end_node.id),
                port_name="结果",
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                out_lines=out_lines,
                indent=indent,
                loop_stack=[],
            )
            if not str(expr or "").strip():
                raise ReverseGraphCodeError("节点图结束（graph_end）缺少结果数据来源，无法生成 return 表达式")
            return_expr = str(expr)

        # 覆盖性校验：事件 member_set 内除了事件节点自身与布局产物外，不应再有无法发出的节点
        remaining: List[str] = []
        for nid in self.member_set:
            nid_str = str(nid)
            if nid_str == str(getattr(event_node, "id", "") or ""):
                continue
            if nid_str.startswith("graph_end_"):
                continue
            if nid_str in self.emitted_nodes:
                continue
            node = self.model.nodes.get(nid_str)
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=nid_str, node=node):
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                continue
            remaining.append(nid_str)

        if remaining:
            node = self.model.nodes.get(remaining[0])
            title = f"{getattr(node, 'category', '')}/{getattr(node, 'title', '')}" if node is not None else "<missing>"
            raise ReverseGraphCodeError(
                "事件内存在无法稳定反向生成的节点（可能是无流程入但也非流程入口，或存在多入口 join 等结构）："
                + f"{remaining[0]} ({title})"
            )

        return return_expr

    def _emit_flow_sequence(
        self,
        *,
        out_lines: List[str],
        start_node_id: Optional[str],
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        current = str(start_node_id) if start_node_id else ""
        while current and current != str(stop_node_id or ""):
            if current in visited_flow:
                # 防止意外环路导致死循环（结构化图不应出现此情况）
                return
            visited_flow.add(current)

            node = self.model.nodes.get(current)
            if node is None:
                return

            title = str(getattr(node, "title", "") or "").strip()

            # break：正向解析会将 `break` 物化为【跳出循环】节点，并由该节点连到循环节点输入【跳出循环】。
            # 反向生成时应还原为语句级 `break`，避免输出 `跳出循环(self.game)` + `break` 的重复语义。
            if title == "跳出循环":
                next_flow = self._pick_single_flow_successor(current)
                if next_flow is None:
                    raise ReverseGraphCodeError("【跳出循环】节点缺少流程后继，无法反向生成 break")
                next_node, next_port = next_flow
                if next_port != "跳出循环":
                    raise ReverseGraphCodeError("【跳出循环】节点的流程后继必须连到循环节点输入【跳出循环】")
                if not loop_stack:
                    raise ReverseGraphCodeError("发现跳出循环语义，但当前不在循环体内")
                if next_node != loop_stack[-1]:
                    raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                self.emitted_nodes.add(str(current))
                out_lines.append(f"{indent}break")
                return

            # 控制流：双分支 if/else
            if title == "双分支":
                true_target = self._flow_target(current, "是")
                false_target = self._flow_target(current, "否")
                # 若该双分支节点未连接任何分支出口，则其仅作为“流程控制节点/双分支”普通节点存在（常见于校准/布局图）。
                # 此时不能用 `if ...:` 语法表达（解析器无法从常量/复杂表达式稳定抽取条件变量），应退化为普通节点调用。
                if true_target is None and false_target is None:
                    self._emit_node_statement(
                        out_lines=out_lines,
                        node_id=current,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent,
                    )
                    next_flow = self._pick_single_flow_successor(current)
                    if next_flow is None:
                        return
                    next_node, next_port = next_flow
                    if next_port == "跳出循环":
                        if not loop_stack:
                            raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                        if next_node != loop_stack[-1]:
                            raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                        out_lines.append(f"{indent}break")
                        return
                    current = next_node
                    continue

                # 结构化 if 已在源码中体现该节点语义：标记为已发出，避免后续覆盖性校验误判“遗漏节点”
                self.emitted_nodes.add(str(current))
                join = self._find_join_for_branches(
                    branch_starts=[true_target, false_target],
                    stop_node_id=stop_node_id,
                )

                # 允许“部分分支接续到外层 stop_node_id”的结构（与多分支 match 的兜底逻辑一致）：
                # - 外层 control-flow（例如循环/更外层 if）可能传入 stop_node_id 作为本 block 的终止边界；
                # - 若当前 if 的某一侧分支可达 stop_node_id、另一侧不可达，则不存在“至少两侧可达”的 join，
                #   但仍需要让可达侧继续向后生成，并在不可达侧末尾注入 return 防止错误接续。
                if (not join) and stop_node_id:
                    stop = str(stop_node_id)
                    for target in (true_target, false_target):
                        if target is None:
                            continue
                        node_id, dst_port = target
                        if dst_port == "跳出循环":
                            continue
                        if node_id and self._can_reach(str(node_id), stop):
                            join = stop
                            break

                # 关键点：若两条分支的流程节点共同依赖某些“纯数据节点”，必须把这些数据节点提升到 if 之前，
                # 否则解析器在分支体 snapshot/restore 下会出现“另一分支看不到变量映射”的缺线。
                self._emit_shared_data_sources_for_branches(
                    out_lines=out_lines,
                    indent=indent,
                    branch_targets=[true_target, false_target],
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                )
                cond_expr = self._expr_for_required_data_input(
                    node_id=current,
                    port_name="条件",
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    out_lines=out_lines,
                    indent=indent,
                    loop_stack=loop_stack,
                )

                out_lines.append(f"{indent}if {cond_expr}:")
                self._emit_branch_body(
                    out_lines=out_lines,
                    branch_target=true_target,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent + "    ",
                    loop_stack=loop_stack,
                    visited_flow=set(visited_flow),
                )
                out_lines.append(f"{indent}else:")
                self._emit_branch_body(
                    out_lines=out_lines,
                    branch_target=false_target,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent + "    ",
                    loop_stack=loop_stack,
                    visited_flow=set(visited_flow),
                )

                # 有共享 tail 才能继续向后生成，否则整个 if 结构已覆盖剩余流程
                if join:
                    current = join
                    continue
                return

            # 控制流：多分支 match/case
            if title == "多分支":
                # 若多分支节点没有任何流程出口连线，则其仅作为普通节点存在（常见于校准/布局图），退化为普通节点调用。
                has_any_branch_edge = bool(self.flow_out.get(str(current), []) or [])
                if not has_any_branch_edge:
                    self._emit_node_statement(
                        out_lines=out_lines,
                        node_id=current,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent,
                    )
                    next_flow = self._pick_single_flow_successor(current)
                    if next_flow is None:
                        return
                    next_node, next_port = next_flow
                    if next_port == "跳出循环":
                        if not loop_stack:
                            raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                        if next_node != loop_stack[-1]:
                            raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                        out_lines.append(f"{indent}break")
                        return
                    current = next_node
                    continue

                # 结构化 match 已在源码中体现该节点语义：标记为已发出，避免后续覆盖性校验误判“遗漏节点”
                self.emitted_nodes.add(str(current))
                control_expr = self._expr_for_required_match_subject(
                    node_id=current,
                    port_name="控制表达式",
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    out_lines=out_lines,
                    indent=indent,
                    loop_stack=loop_stack,
                )

                # 分支端口（流程输出）：包含默认 + 动态 case
                flow_out_ports = [
                    str(getattr(p, "name", "") or "")
                    for p in (getattr(node, "outputs", None) or [])
                    if str(getattr(p, "name", "") or "")
                ]
                if not flow_out_ports:
                    raise ReverseGraphCodeError("多分支节点缺少输出端口")

                branch_targets = [self._flow_target(current, port) for port in flow_out_ports]
                join = self._find_join_for_branches(branch_starts=branch_targets, stop_node_id=stop_node_id)

                # 允许“部分分支接续到外层 stop_node_id”的结构：
                # - 对于嵌套控制流（例如 if 分支内的 match），外层会给当前 block 传入 stop_node_id；
                # - 若 match 的部分 case 能到达 stop_node_id、但并非所有 case 都能到达，则 _find_join_for_branches
                #   会返回 None（因为不存在“至少两个分支共同可达”的 join）；
                # - 这种图在 AST 中应表达为：无法到达 join 的 case 末尾显式 `return`，其余 case 继续向后执行。
                # 因此这里将 stop_node_id 作为“弱 join”兜底：让可达分支继续向后，且让不可达分支被 _emit_branch_body 注入 return。
                if (not join) and stop_node_id:
                    stop = str(stop_node_id)
                    for target in branch_targets:
                        if target is None:
                            continue
                        node_id, dst_port = target
                        if dst_port == "跳出循环":
                            continue
                        if node_id and self._can_reach(str(node_id), stop):
                            join = stop
                            break

                self._emit_shared_data_sources_for_branches(
                    out_lines=out_lines,
                    indent=indent,
                    branch_targets=branch_targets,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                )

                out_lines.append(f"{indent}match {control_expr}:")
                # case 输出顺序：
                # - 对于“嵌套控制流 + 外层 join”的图，IR 在外层 if/match 的出口推断中会使用“分支体最后一个流程节点”作为接续点；
                #   因此这里需要保证“能接续到 join 的分支”在源码中尽量靠后，避免错误地把不可达分支当作接续点。
                # - 若 join 存在：将可达 join 的 case 放在后面；不可达的 case 放在前面。
                ordered_ports = list(flow_out_ports)
                if join:
                    join_id = str(join)
                    reachable_ports: List[str] = []
                    unreachable_ports: List[str] = []
                    for port_name in ordered_ports:
                        target = self._flow_target(current, port_name)
                        if target is None or target[1] == "跳出循环":
                            unreachable_ports.append(port_name)
                            continue
                        start_id = str(target[0])
                        if start_id == join_id or self._can_reach(start_id, join_id):
                            reachable_ports.append(port_name)
                        else:
                            unreachable_ports.append(port_name)
                    ordered_ports = unreachable_ports + reachable_ports

                for port_name in ordered_ports:
                    pattern = self._render_match_case_pattern(port_name)
                    out_lines.append(f"{indent}    case {pattern}:")
                    self._emit_branch_body(
                        out_lines=out_lines,
                        branch_target=self._flow_target(current, port_name),
                        join_node_id=join,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent + "        ",
                        loop_stack=loop_stack,
                        visited_flow=set(visited_flow),
                    )

                if join:
                    current = join
                    continue
                return

            # 控制流：复合节点多流程出口（match self.<复合实例>.<入口>(...)）
            #
            # 对齐正向解析协议：`engine.graph.ir.statement_flow_builder.handle_match_over_composite_call`
            # - match subject 必须为 `self.<alias>.<method>(...)`
            # - case 使用字符串字面量（流程出口名）或 `_`（仅当存在“默认”出口时）
            node_def = _try_resolve_node_def(node=node, node_library=self.node_library)
            if node_def is not None and bool(getattr(node_def, "is_composite", False)):
                flow_outputs_in_order = [
                    str(getattr(p, "name", "") or "")
                    for p in (getattr(node, "outputs", None) or [])
                    if str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True)
                ]
                connected_flow_outputs = [
                    name for name in flow_outputs_in_order if self._flow_target(current, name) is not None
                ]
                needs_match = False
                if len(connected_flow_outputs) > 1:
                    needs_match = True
                elif (
                    len(connected_flow_outputs) == 1
                    and len(flow_outputs_in_order) > 1
                    and connected_flow_outputs[0] != flow_outputs_in_order[0]
                ):
                    # 仅连接了一个“非默认（非首个）”流程出口：必须用 match 显式指定出口，
                    # 否则解析器会用默认出口自动接续，导致 src_port 语义不一致。
                    needs_match = True

                if needs_match:
                    # 复合节点的 match 语法无法表达其“数据输出”的变量绑定；
                    # 若该复合节点的任一数据输出被下游节点引用，则当前图无法稳定反向（fail-closed）。
                    for (_dst_node, _dst_port), (src_node_id, src_port) in list(self.data_in_edge.items()):
                        if str(src_node_id) != str(current):
                            continue
                        if not self._is_flow_port(node, str(src_port), True):
                            raise ReverseGraphCodeError(
                                f"复合节点 {node.title} 的数据输出端口 {src_port!r} 被下游引用，但该节点又存在多流程出口；"
                                "当前版本无法同时表达“多流程出口 + 数据输出”语义，请拆分图结构或减少对该数据输出的依赖。"
                            )

                    # 先确保复合节点调用所需的数据来源节点已被发出（仅允许纯数据节点在此处被提前发出）
                    for port in (getattr(node, "inputs", None) or []):
                        pname = str(getattr(port, "name", "") or "")
                        if not pname or self._is_flow_port(node, pname, False):
                            continue
                        source = self.data_in_edge.get((str(node.id), pname))
                        if source is None:
                            continue
                        src_node_id, _src_port = source
                        if src_node_id not in self.emitted_nodes:
                            self._ensure_data_node_emitted(
                                out_lines=out_lines,
                                node_id=src_node_id,
                                var_mapping=var_mapping,
                                used_var_names=used_var_names,
                                indent=indent,
                            )

                    # match subject：self.<复合实例>.<入口>(...)
                    composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
                        getattr(node, "composite_id", "") or ""
                    ).strip()
                    if not composite_id:
                        composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
                    alias = self.composite_alias_by_id.get(composite_id) or (
                        make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
                    )
                    if not alias.isidentifier() or keyword.iskeyword(alias):
                        raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")

                    call_args = _render_node_call_args(
                        node=node,
                        node_def=node_def,
                        node_library=self.node_library,
                        data_in_edge=self.data_in_edge,
                        var_mapping=var_mapping,
                    )
                    if call_args:
                        subject_expr = f"self.{alias}.{self._composite_entry_method_name}({', '.join(call_args)})"
                    else:
                        subject_expr = f"self.{alias}.{self._composite_entry_method_name}()"

                    branch_targets = [self._flow_target(current, port) for port in connected_flow_outputs]
                    join = self._find_join_for_branches(branch_starts=branch_targets, stop_node_id=stop_node_id)

                    self._emit_shared_data_sources_for_branches(
                        out_lines=out_lines,
                        indent=indent,
                        branch_targets=branch_targets,
                        join_node_id=join,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                    )

                    out_lines.append(f"{indent}match {subject_expr}:")
                    for port_name in connected_flow_outputs:
                        pattern = "_" if port_name == "默认" else repr(port_name)
                        out_lines.append(f"{indent}    case {pattern}:")
                        self._emit_branch_body(
                            out_lines=out_lines,
                            branch_target=self._flow_target(current, port_name),
                            join_node_id=join,
                            var_mapping=var_mapping,
                            used_var_names=used_var_names,
                            indent=indent + "        ",
                            loop_stack=loop_stack,
                            visited_flow=set(visited_flow),
                        )

                    self.emitted_nodes.add(str(current))
                    if join:
                        current = join
                        continue
                    return

            # 控制流：for 循环（有限循环 / 列表迭代循环）
            if title in LOOP_NODE_NAMES:
                # 循环前提升：若循环后的流程节点依赖某些“纯数据节点”，这些节点必须在循环外定义，
                # 否则 IR 解析在 loop 的 snapshot/restore 下会丢失变量映射，导致循环后缺线。
                next_target_preview = self._flow_target(current, "循环完成")
                if next_target_preview is not None and next_target_preview[1] != "跳出循环":
                    after_region = self._collect_flow_nodes_in_region(
                        start_node_id=next_target_preview[0],
                        stop_node_id=stop_node_id,
                    )
                    after_sources = self._collect_direct_data_sources_into_nodes(after_region)
                    for src_id in sorted(after_sources):
                        if src_id in self.emitted_nodes:
                            continue
                        src_node = self.model.nodes.get(src_id)
                        if src_node is None:
                            continue
                        if self._node_has_any_flow_port(src_node):
                            continue
                        if not self._can_emit_data_node_without_unbound_flow_sources(
                            node_id=str(src_id),
                            var_mapping=var_mapping,
                            visiting=set(),
                        ):
                            continue
                        self._ensure_data_node_emitted(
                            out_lines=out_lines,
                            node_id=src_id,
                            var_mapping=var_mapping,
                            used_var_names=used_var_names,
                            indent=indent,
                        )

                if title == "有限循环":
                    loop_var = self._unique_var_name("当前循环值", used_var_names)
                    var_mapping[(current, "当前循环值")] = loop_var
                    start_expr = self._expr_for_optional_data_input(
                        node_id=current,
                        port_name="循环起始值",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    end_expr = self._expr_for_optional_data_input(
                        node_id=current,
                        port_name="循环终止值",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    if not end_expr:
                        raise ReverseGraphCodeError("有限循环缺少 循环终止值（必须有数据来源或常量）")
                    if start_expr and start_expr != "0":
                        range_expr = f"range({start_expr}, {end_expr})"
                    else:
                        range_expr = f"range({end_expr})"
                    out_lines.append(f"{indent}for {loop_var} in {range_expr}:")
                else:
                    # 列表迭代循环：迭代列表必须为变量名（Name），否则正向解析不会连边
                    loop_var = self._unique_var_name("迭代值", used_var_names)
                    var_mapping[(current, "迭代值")] = loop_var
                    iter_expr = self._expr_for_required_match_subject(
                        node_id=current,
                        port_name="迭代列表",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    out_lines.append(f"{indent}for {loop_var} in {iter_expr}:")

                # 循环节点本身是控制流结构，不会通过 `_emit_node_statement` 生成；
                # 但其数据输出（当前循环值/迭代值）会被循环体内节点引用。
                # 这里将其视为“已发出”，避免下游在解析数据来源时误判为“需要提前生成流程节点”。
                self.emitted_nodes.add(str(current))

                body_target = self._flow_target(current, "循环体")
                if body_target is None:
                    out_lines.append(f"{indent}    pass")
                elif body_target[1] == "跳出循环":
                    raise ReverseGraphCodeError("循环体出口不应直接连到跳出循环端口")
                else:
                    self._emit_flow_sequence(
                        out_lines=out_lines,
                        start_node_id=body_target[0],
                        stop_node_id=None,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent + "    ",
                        loop_stack=loop_stack + [current],
                        visited_flow=set(),
                    )

                # 循环后续：从 循环完成 出口继续
                next_target = self._flow_target(current, "循环完成")
                if next_target is None:
                    return
                if next_target[1] == "跳出循环":
                    raise ReverseGraphCodeError("循环完成出口不应连到跳出循环端口")
                current = next_target[0]
                continue

            # 普通节点：按调用生成
            self._emit_node_statement(
                out_lines=out_lines,
                node_id=current,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

            next_flow = self._pick_single_flow_successor(current)
            if next_flow is None:
                return
            next_node, next_port = next_flow
            if next_port == "跳出循环":
                # break：仅当处于循环体内且目标为当前循环节点时才合法
                if not loop_stack:
                    raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                if next_node != loop_stack[-1]:
                    raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                out_lines.append(f"{indent}break")
                return
            current = next_node

    def _emit_branch_body(
        self,
        *,
        out_lines: List[str],
        branch_target: Optional[Tuple[str, str]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        # break-only 分支：直接连接到循环节点的“跳出循环”
        if branch_target is not None and branch_target[1] == "跳出循环":
            if not loop_stack or branch_target[0] != loop_stack[-1]:
                raise ReverseGraphCodeError("break 分支不在正确的循环上下文内")
            out_lines.append(f"{indent}break")
            return

        if branch_target is None or (join_node_id and branch_target[0] == join_node_id):
            out_lines.append(f"{indent}pass")
            return

        self._emit_flow_sequence(
            out_lines=out_lines,
            start_node_id=branch_target[0],
            stop_node_id=join_node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
            visited_flow=visited_flow,
        )

        # 若 join 存在但该分支不通向 join，则必须显式 return 以避免解析器自动接续
        if join_node_id and (not self._can_reach(branch_target[0], join_node_id)):
            out_lines.append(f"{indent}return")

    def _emit_shared_data_sources_for_branches(
        self,
        *,
        out_lines: List[str],
        indent: str,
        branch_targets: List[Optional[Tuple[str, str]]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
    ) -> None:
        """将被多个分支共同依赖的“纯数据节点”提升到控制流语句之前。"""
        branch_flow_nodes: List[set[str]] = []
        for target in branch_targets:
            if target is None:
                branch_flow_nodes.append(set())
                continue
            node_id, dst_port = target
            if dst_port == "跳出循环":
                branch_flow_nodes.append(set())
                continue
            branch_flow_nodes.append(
                self._collect_flow_nodes_in_region(start_node_id=node_id, stop_node_id=join_node_id)
            )

        # 统计每个“数据来源节点”在多少个分支中被使用（只看直接连到分支内流程节点的数据边）
        src_count: Dict[str, int] = {}
        for flow_nodes in branch_flow_nodes:
            srcs = self._collect_direct_data_sources_into_nodes(flow_nodes)
            for src in srcs:
                src_count[src] = src_count.get(src, 0) + 1

        shared_sources = [node_id for node_id, count in src_count.items() if count >= 2]
        # join 节点本身的“纯数据来源”也必须在控制流语句前被绑定，
        # 否则可能出现“仅在某个分支内首次发出该数据节点 -> join 后使用时缺少数据来源”的严格解析失败。
        join_sources: set[str] = set()
        if join_node_id:
            join_sources = self._collect_direct_data_sources_into_nodes({str(join_node_id)})

        lifted_sources = set(shared_sources) | set(join_sources)
        # 稳定输出顺序：按 node_id 排序（避免 diff 噪音）
        for node_id in sorted(lifted_sources):
            if node_id in self.emitted_nodes:
                continue
            if not self._can_emit_data_node_without_unbound_flow_sources(
                node_id=str(node_id),
                var_mapping=var_mapping,
                visiting=set(),
            ):
                continue
            self._ensure_data_node_emitted(
                out_lines=out_lines,
                node_id=node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

    def _collect_flow_nodes_in_region(self, *, start_node_id: str, stop_node_id: Optional[str]) -> set[str]:
        """收集从 start 出发沿流程边可达、且在 stop 之前的流程节点集合。"""
        visited: set[str] = set()
        q = deque([str(start_node_id)])
        stop = str(stop_node_id) if stop_node_id else ""
        while q:
            node_id = q.popleft()
            if not node_id or node_id in visited:
                continue
            if stop and node_id == stop:
                continue
            visited.add(node_id)
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append(dst_node)
        return visited

    def _collect_direct_data_sources_into_nodes(self, nodes: set[str]) -> set[str]:
        """返回所有“直接连到这些节点任一数据输入端口”的来源节点集合（不做传递闭包）。"""
        result: set[str] = set()
        for dst_id in nodes:
            dst_node = self.model.nodes.get(dst_id)
            if dst_node is None:
                continue
            for port in (dst_node.inputs or []):
                pname = str(getattr(port, "name", "") or "")
                if not pname:
                    continue
                if self._is_flow_port(dst_node, pname, False):
                    continue
                source = self.data_in_edge.get((dst_id, pname))
                if source is None:
                    continue
                result.add(source[0])
        return result

    def _node_has_any_flow_port(self, node: NodeModel) -> bool:
        for port in (getattr(node, "outputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, True):
                return True
        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, False):
                return True
        return False

    def _can_emit_data_node_without_unbound_flow_sources(
        self,
        *,
        node_id: str,
        var_mapping: Mapping[Tuple[str, str], str],
        visiting: set[str],
    ) -> bool:
        """判断一个“纯数据节点”能否在当前作用域被提前发出（不依赖未绑定的流程节点输出）。"""
        nid = str(node_id or "")
        if not nid:
            return False
        if nid in visiting:
            return True
        visiting.add(nid)

        node = self.model.nodes.get(nid)
        if node is None:
            return False
        if self._node_has_any_flow_port(node):
            return False

        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):
                continue
            source = self.data_in_edge.get((nid, pname))
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            if src_key in var_mapping:
                continue
            src_node = self.model.nodes.get(src_key[0])
            if src_node is None:
                return False
            if self._node_has_any_flow_port(src_node):
                return False
            if not self._can_emit_data_node_without_unbound_flow_sources(
                node_id=src_key[0],
                var_mapping=var_mapping,
                visiting=visiting,
            ):
                return False

        return True

    def _emit_node_statement(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        if node_id in self.emitted_nodes:
            return
        node = self.model.nodes.get(node_id)
        if node is None:
            return

        node_def = _resolve_node_def(node=node, node_library=self.node_library)
        call_name = _pick_call_name_for_node(
            node=node,
            node_def=node_def,
            node_library=self.node_library,
            node_name_index=self.node_name_index,
            call_name_candidates_by_identity=self.call_name_candidates_by_identity,
        )

        # 先确保所有数据输入的来源节点已被发出（仅允许纯数据节点在此处被提前发出）
        for port in (node.inputs or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):
                continue
            source = self.data_in_edge.get((node_id, pname))
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            # 事件参数 / 已有映射：不需要也不允许“提前发出”源节点
            if src_key in var_mapping:
                continue
            if str(src_node_id) not in self.emitted_nodes:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=str(src_node_id),
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )

        data_outputs = [
            p
            for p in (node.outputs or [])
            if (str(getattr(p, "name", "") or "")) and (not self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))
        ]
        output_var_names: List[str] = []
        if data_outputs:
            raw_names = [str(getattr(p, "name", "") or "") for p in data_outputs]
            # 动态输出端口（NodeDef.output_types 为空）：
            # 解析器会把“赋值目标变量名”当作输出端口名生成动态端口；
            # 因此必须使用端口名本身作为变量名，避免由于去重/改名导致 round-trip 端口集合变化。
            is_dynamic_outputs = bool(node_def is not None and (not getattr(node_def, "output_types", None)))
            output_var_names = raw_names if is_dynamic_outputs else _finalize_output_var_names(raw_names, used=used_var_names)
            for port, var_name in zip(data_outputs, output_var_names):
                port_name = str(getattr(port, "name", "") or "")
                var_mapping[(node.id, port_name)] = var_name

        extra_args = _render_node_call_args(
            node=node,
            node_def=node_def,
            node_library=self.node_library,
            data_in_edge=self.data_in_edge,
            var_mapping=var_mapping,
        )
        if bool(getattr(node_def, "is_composite", False)):
            composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
                getattr(node, "composite_id", "") or ""
            ).strip()
            if not composite_id:
                composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
            alias = self.composite_alias_by_id.get(composite_id) or (
                make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
            )
            if not alias.isidentifier() or keyword.iskeyword(alias):
                raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")
            if extra_args:
                call_expr = f"self.{alias}.{self._composite_entry_method_name}({', '.join(extra_args)})"
            else:
                call_expr = f"self.{alias}.{self._composite_entry_method_name}()"
        else:
            call_expr = f"{call_name}({', '.join(['self.game'] + extra_args)})"

        if self._try_emit_arithmetic_operator_statement(
            out_lines=out_lines,
            node=node,
            node_id=node_id,
            output_var_names=output_var_names,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        ):
            return

        if output_var_names:
            if len(output_var_names) == 1:
                out_lines.append(f"{indent}{output_var_names[0]} = {call_expr}")
            else:
                lhs = ", ".join(output_var_names)
                out_lines.append(f"{indent}{lhs} = {call_expr}")
        else:
            out_lines.append(f"{indent}{call_expr}")

        self.emitted_nodes.add(node_id)

    def _expr_for_required_data_input_or_constant(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
    ) -> str:
        node = self.model.nodes.get(node_id)
        if node is None:
            raise ReverseGraphCodeError("节点不存在")

        source = self.data_in_edge.get((node_id, port_name))
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            if expr is None:
                raise ReverseGraphCodeError(f"无法解析数据来源变量：{node.title}.{port_name}")
            return expr

        if port_name in (node.input_constants or {}):
            return format_constant((node.input_constants or {}).get(port_name))

        raise ReverseGraphCodeError(f"节点缺少输入：{node.title}.{port_name}")

    def _resolve_arithmetic_operator_numeric_result_type(self, *, node_id: str) -> str:
        left_type = str(self._port_type_resolver.resolve(str(node_id), "左值", is_input=True) or "").strip()
        right_type = str(self._port_type_resolver.resolve(str(node_id), "右值", is_input=True) or "").strip()
        out_type = str(self._port_type_resolver.resolve(str(node_id), "结果", is_input=False) or "").strip()
        if left_type in _NUMERIC_TYPES and right_type in _NUMERIC_TYPES and out_type in _NUMERIC_TYPES:
            return out_type
        node = self.model.nodes.get(str(node_id))
        title = str(getattr(node, "title", "") or "") if node is not None else str(node_id)
        raise ReverseGraphCodeError(
            f"启用了 prefer_arithmetic_operators，但节点 {title} 的左右值类型不是数值："
            f"左值={left_type or '（未知）'} 右值={right_type or '（未知）'} 结果={out_type or '（未知）'}；"
            "请修正端口类型推断/覆盖，或关闭该选项以输出 canonical 节点调用。"
        )

    def _try_emit_arithmetic_operator_statement(
        self,
        *,
        out_lines: List[str],
        node: NodeModel,
        node_id: str,
        output_var_names: List[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> bool:
        if not bool(getattr(self.options, "prefer_arithmetic_operators", False)):
            return False

        title = str(getattr(node, "title", "") or "").strip()
        op = _ARITHMETIC_OPERATOR_BY_TITLE.get(title)
        if not op:
            return False

        if not output_var_names:
            raise ReverseGraphCodeError(f"算术节点 {title} 缺少数据输出端口，无法生成运算符表达式")
        if len(output_var_names) != 1:
            raise ReverseGraphCodeError(f"算术节点 {title} 存在多数据输出，无法生成运算符表达式")

        result_type = self._resolve_arithmetic_operator_numeric_result_type(node_id=str(node_id))

        left_expr = self._expr_for_required_data_input_or_constant(
            node_id=str(node_id),
            port_name="左值",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
        )
        right_expr = self._expr_for_required_data_input_or_constant(
            node_id=str(node_id),
            port_name="右值",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
        )
        expr = f"({left_expr} {op} {right_expr})"
        out_lines.append(f'{indent}{output_var_names[0]}: "{result_type}" = {expr}')
        self.emitted_nodes.add(str(node_id))
        return True

    def _ensure_data_node_emitted(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        if node_id in self.emitted_nodes:
            return
        node = self.model.nodes.get(node_id)
        if node is None:
            return

        # 只允许纯数据节点被“提前发出”，避免破坏流程结构
        if any(self._is_flow_port(node, str(getattr(p, "name", "") or ""), True) for p in (node.outputs or [])) or any(
            self._is_flow_port(node, str(getattr(p, "name", "") or ""), False) for p in (node.inputs or [])
        ):
            raise ReverseGraphCodeError(
                f"数据依赖要求提前生成流程节点：{node.category}/{node.title}；该图在当前策略下无法稳定反向"
            )

        self._emit_node_statement(
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )

    def _flow_target(self, src_node_id: str, src_port: str) -> Optional[Tuple[str, str]]:
        return self.flow_out_by_port.get((str(src_node_id), str(src_port)))

    def _pick_single_flow_successor(self, node_id: str) -> Optional[Tuple[str, str]]:
        outs = list(self.flow_out.get(str(node_id), []) or [])
        if not outs:
            return None
        if len(outs) != 1:
            node = self.model.nodes.get(node_id)
            title = getattr(node, "title", "") if node is not None else node_id
            raise ReverseGraphCodeError(f"节点存在多条流程出边但不是结构化控制流节点：{title}")
        _src_port, dst_node, dst_port = outs[0]
        return dst_node, dst_port

    def _can_reach(self, start: str, target: str) -> bool:
        return target in self._bfs_distances(start)

    def _bfs_distances(self, start: str) -> Dict[str, int]:
        start_id = str(start)
        dist: Dict[str, int] = {}
        q = deque([(start_id, 0)])
        while q:
            node_id, d = q.popleft()
            if node_id in dist:
                continue
            dist[node_id] = d
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                # break 视为终止：不把“跳出循环”当作可继续的后继
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append((dst_node, d + 1))
        return dist

    def _find_join_for_branches(
        self,
        *,
        branch_starts: List[Optional[Tuple[str, str]]],
        stop_node_id: Optional[str],
    ) -> Optional[str]:
        # 收集“可继续”的起点：排除 break 与 None
        starts: List[str] = []
        for item in branch_starts:
            if item is None:
                continue
            node_id, dst_port = item
            if dst_port == "跳出循环":
                continue
            if stop_node_id and node_id == stop_node_id:
                continue
            starts.append(str(node_id))
        if len(starts) < 2:
            return None

        dist_maps = [self._bfs_distances(s) for s in starts]
        reach_count: Dict[str, int] = {}
        for dm in dist_maps:
            for node_id in dm.keys():
                reach_count[node_id] = reach_count.get(node_id, 0) + 1

        candidates = [node_id for node_id, c in reach_count.items() if c >= 2]
        if not candidates:
            return None

        def sort_key(node_id: str) -> Tuple[int, int, int, str]:
            counts = reach_count.get(node_id, 0)
            dists = [dm.get(node_id, 10**9) for dm in dist_maps]
            return (-counts, max(dists), sum(dists), node_id)

        return sorted(candidates, key=sort_key)[0]

    def _expr_for_required_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        node = self.model.nodes.get(node_id)
        if node is None:
            raise ReverseGraphCodeError("节点不存在")
        source = self.data_in_edge.get((node_id, port_name))
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            if expr is None:
                raise ReverseGraphCodeError(f"无法解析数据来源变量：{node.title}.{port_name}")
            return expr
        # 常量输入不支持：GraphCodeParser 的 if/match 语义需要变量来源，避免生成无输入的控制节点
        raise ReverseGraphCodeError(f"控制流节点缺少数据来源：{node.title}.{port_name}")

    def _expr_for_optional_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        node = self.model.nodes.get(node_id)
        if node is None:
            return ""
        source = self.data_in_edge.get((node_id, port_name))
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            return expr or ""
        if port_name in (node.input_constants or {}):
            return format_constant((node.input_constants or {}).get(port_name))
        return ""

    def _expr_for_required_match_subject(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        expr = self._expr_for_required_data_input(
            node_id=node_id,
            port_name=port_name,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )
        if not expr.isidentifier() or keyword.iskeyword(expr):
            raise ReverseGraphCodeError(f"match subject 必须是变量名（Name），但当前为：{expr!r}")
        return expr

    def _render_match_case_pattern(self, port_name: str) -> str:
        name = str(port_name or "").strip()
        if name == "默认":
            return "_"
        # 整数 case：允许负数
        if name and (name.isdigit() or (name.startswith("-") and name[1:].isdigit())):
            return name
        return repr(name)

    def _unique_var_name(self, base: str, used: set[str]) -> str:
        candidate = make_valid_identifier(base or "") or "var"
        if keyword.iskeyword(candidate):
            candidate = f"{candidate}_var"
        while candidate in used:
            candidate = f"{candidate}_1"
        used.add(candidate)
        return candidate


def _pick_call_name_for_node(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    node_name_index: Dict[str, str],
    call_name_candidates_by_identity: Dict[int, List[str]],
) -> str:
    # 优先：title 若可直接作为调用名且能命中 name_index，且映射到同一 NodeDef
    title = str(getattr(node, "title", "") or "").strip()
    if title and title.isidentifier() and (not keyword.iskeyword(title)):
        mapped_key = node_name_index.get(title)
        if mapped_key is not None:
            mapped_def = node_library.get(mapped_key)
            if mapped_def is node_def:
                return title

    identity = id(node_def)
    candidates = call_name_candidates_by_identity.get(identity) or []
    if not candidates:
        raise ReverseGraphCodeError(
            f"节点 {node.category}/{node.title} 缺少可调用名（title 不可用且未找到别名键）"
        )
    return candidates[0]


def _finalize_output_var_names(raw_names: Sequence[str], *, used: set[str]) -> List[str]:
    finalized: List[str] = []
    for raw in raw_names:
        candidate = make_valid_identifier(raw or "")
        if not candidate or candidate == "_":
            candidate = "var"
        while candidate in used or keyword.iskeyword(candidate):
            candidate = f"{candidate}_1"
        used.add(candidate)
        finalized.append(candidate)
    return finalized

