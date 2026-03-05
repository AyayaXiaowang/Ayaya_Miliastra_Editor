from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Sequence, Mapping
from collections import defaultdict
from datetime import datetime
import re

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.graph.models import GraphModel, NodeModel, PortModel
from engine.graph.common import (
    is_flow_port,
    FLOW_PORT_PLACEHOLDER,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    get_builtin_anchor_titles_for_client_graph,
    STRUCT_NODE_TITLES,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_SPLIT_STATIC_INPUTS,
    STRUCT_SPLIT_STATIC_OUTPUTS,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_BUILD_STATIC_OUTPUTS,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_MODIFY_STATIC_OUTPUTS,
    STRUCT_NAME_PORT_NAME,
)
from importlib import import_module
from engine.nodes.port_name_rules import get_dynamic_port_type
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.graph.utils.metadata_extractor import apply_graph_path_inference, extract_metadata_from_code
from engine.graph.utils.ast_utils import is_class_structure_format
from engine.graph.utils.comment_extractor import extract_comments, associate_comments_to_nodes
from engine.graph.code_to_graph_orchestrator import CodeToGraphParser
from engine.graph.composite.param_usage_tracker import ParamUsageTracker
from engine.graph.ir.ast_scanner import find_graph_class
from engine.graph.semantic import GraphSemanticPass
from engine.utils.name_utils import dedupe_preserve_order
from engine.utils.source_text import read_text
from engine.utils.workspace import (
    get_injected_workspace_root_or_none,
    looks_like_workspace_root,
    resolve_workspace_root,
)
from engine.graph.utils.graph_code_rewrite_config import build_graph_code_rewrite_config
from engine.graph.utils.list_literal_rewriter import rewrite_graph_code_list_literals
from engine.graph.utils.dict_literal_rewriter import rewrite_graph_code_dict_literals
from engine.graph.utils.syntax_sugar_rewriter import rewrite_graph_code_syntax_sugars


"""节点图代码（Graph Code）解析工具集。

提供从类结构 Python 文件到 `GraphModel` 的解析能力，委托 `CodeToGraphParser` 和 utils 工具。
设计为**静态建模 + 校验**组件：只关心“用哪些节点、如何连线、元数据和注释”，不会执行节点实际业务逻辑，主要用于给 AI / 开发者提供可验证的节点图代码接口。
"""


# ============================================================================
# 验证函数
# ============================================================================

def validate_graph_model(
    model: GraphModel,
    virtual_pin_mappings: Optional[Dict[Tuple[str, str], bool]] = None,
    *,
    workspace_path: Optional[Path] = None,
    node_library: Optional[Dict[str, NodeDef]] = None,
) -> List[str]:
    """验证图的完整性（简化版本）
    
    Args:
        model: 节点图模型
        virtual_pin_mappings: 虚拟引脚映射 {(node_id, port_name): is_input}
                             用于复合节点编辑器，标记哪些端口已暴露为虚拟引脚
        workspace_path: 工作区路径（可选，未提供 node_library 时用于加载节点库）
        node_library: 预加载的节点库（可选，避免重复加载）
    
    Returns:
        错误列表
    """
    errors: List[str] = []
    virtual_pin_mappings = virtual_pin_mappings or {}
    
    # 获取节点库（用于端口类型查询）
    if node_library is None:
        workspace = workspace_path
        if workspace is None:
            injected_root = get_injected_workspace_root_or_none()
            if injected_root is not None and looks_like_workspace_root(injected_root):
                workspace = injected_root
            else:
                workspace = resolve_workspace_root(start_paths=[Path(__file__).resolve()])
        registry = get_node_registry(workspace)
        node_library = registry.get_library()

    # 规约为 dict（避免 Optional 分支在后续逻辑中反复判空）
    node_library = dict(node_library or {})
    scope_text = str((getattr(model, "metadata", None) or {}).get("graph_type") or "").strip().lower()

    # 端口类型覆盖（GraphModel.metadata.port_type_overrides）：
    # - 由 Graph Code 注解、结构体/字典推断、以及布局增强（如【获取局部变量】relay）写入；
    # - 结构校验在判定“枚举端口连线”等强约束时必须优先考虑覆盖，
    #   否则会出现“增强布局插入 relay 后 UI 报错，但源码自检通过”的口径漂移。
    from engine.graph.port_type_effective_resolver import build_port_type_overrides, resolve_override_type_for_node_port

    port_type_overrides = build_port_type_overrides(model)
    
    incoming_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    incoming_edges_by_port: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    for edge in model.edges.values():
        incoming_counts[edge.dst_node][edge.dst_port] += 1
        incoming_edges_by_port[(edge.dst_node, edge.dst_port)].append(edge)

    def _resolve_node_def(node: NodeModel) -> Optional[NodeDef]:
        """从 node_library 中解析 NodeDef（唯一真源：node.node_def_ref）。"""
        node_def_ref = getattr(node, "node_def_ref", None)
        if node_def_ref is None:
            raise ValueError(f"节点缺少 node_def_ref：{getattr(node, 'category', '')}/{getattr(node, 'title', '')}")

        kind = str(getattr(node_def_ref, "kind", "") or "").strip()
        key = str(getattr(node_def_ref, "key", "") or "").strip()
        if kind == "builtin":
            found = node_library.get(key)
            if found is None:
                raise KeyError(f"node_library 中未找到 builtin NodeDef：{key}")
            return found
        if kind == "composite":
            # key 为 composite_id：禁止通过 title/name 模糊匹配
            for _, node_def in node_library.items():
                if not getattr(node_def, "is_composite", False):
                    continue
                if str(getattr(node_def, "composite_id", "") or "") == key:
                    return node_def
            raise KeyError(f"node_library 中未找到 composite NodeDef（composite_id={key}）")
        if kind == "event":
            # 事件入口：默认不在节点库中；端口类型由 GraphModel/overrides 承载。
            #
            # 但存在一类“事件节点以 event kind 承载稳定事件名”的模型：
            # - node.title/category 仍对应一个内置事件节点（例如【监听信号】），用于 UI 展示与端口集合；
            # - node_def_ref.key 则保留“真实事件名/信号名”，用于 round-trip 与导出链路的稳定定位。
            #
            # 在这类模型中，允许通过 `category/title -> builtin_key` 的确定性映射解析 NodeDef，
            # 以便复用节点库中的端口类型定义（尤其是静态输出端口类型），避免误报“端口类型仍为泛型”。
            category_text = str(getattr(node, "category", "") or "").strip()
            title_text = str(getattr(node, "title", "") or "").strip()
            if category_text and title_text:
                builtin_key = f"{category_text}/{title_text}"
                found = node_library.get(builtin_key)
                if found is not None:
                    return found
            return None

        raise ValueError(f"非法 node_def_ref.kind：{kind!r}")

    def _edge_span_text(src: NodeModel, dst: NodeModel) -> str:
        src_lo = getattr(src, "source_lineno", 0) or 0
        src_hi = getattr(src, "source_end_lineno", 0) or 0
        dst_lo = getattr(dst, "source_lineno", 0) or 0
        dst_hi = getattr(dst, "source_end_lineno", 0) or 0
        lo_candidates = [x for x in [src_lo, dst_lo] if isinstance(x, int) and x > 0]
        hi_candidates = [x for x in [src_hi or src_lo, dst_hi or dst_lo] if isinstance(x, int) and x > 0]
        if lo_candidates and hi_candidates:
            span_lo = min(lo_candidates)
            span_hi = max(hi_candidates)
            return f" (第{span_lo}~{span_hi}行)"
        return " (第?~?行)"

    # ------------------------------------------------------------------------
    # 结构一致性：边引用的端口必须存在于节点端口集合中
    #
    # 背景：
    # - Graph Code 允许作者写关键字参数；但对“非动态端口节点”，若传入了不存在的关键字参数，
    #   IR 建模可能仍会生成 data-edge（dst_port=该关键字），而 NodeModel.inputs 并不会包含该端口；
    # - 写回/导出阶段会在更深处以 ValueError 暴露（例如 dst_port 不在 dst_node.inputs），定位成本很高；
    # - 因此在 validate_graph_model 阶段应 fail-fast，把错误提升为“节点图结构错误”，并带上行范围。
    # ------------------------------------------------------------------------

    def _extract_port_names(ports: Sequence[PortModel]) -> set[str]:
        names: set[str] = set()
        for p in list(ports or []):
            name = str(getattr(p, "name", "") or "").strip()
            if name:
                names.add(name)
        return names

    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        dst_node = model.nodes.get(edge.dst_node)
        if not src_node or not dst_node:
            continue

        src_output_names = _extract_port_names(list(getattr(src_node, "outputs", []) or []))
        dst_input_names = _extract_port_names(list(getattr(dst_node, "inputs", []) or []))

        # flow placeholder 在 UI/序列化层可作为“自动选择流程端口”的占位符；不作为“端口不存在”处理
        # 逐边输出更精确的行范围：同一条边可能同时缺 src/dst 端口
        span_text = _edge_span_text(src_node, dst_node)
        if edge.src_port != FLOW_PORT_PLACEHOLDER and edge.src_port not in src_output_names:
            errors.append(
                "边引用的源端口不存在："
                f"节点 {src_node.category}/{src_node.title} 的输出端口 '{edge.src_port}' 不在节点 outputs 中；"
                f"可用 outputs={sorted(src_output_names)}{span_text}"
            )
        if edge.dst_port != FLOW_PORT_PLACEHOLDER and edge.dst_port not in dst_input_names:
            errors.append(
                "边引用的目标端口不存在："
                f"节点 {dst_node.category}/{dst_node.title} 的输入端口 '{edge.dst_port}' 不在节点 inputs 中；"
                f"可用 inputs={sorted(dst_input_names)}{span_text}"
            )

    def _node_span_text(node: NodeModel) -> str:
        lo = getattr(node, "source_lineno", 0) or 0
        hi = getattr(node, "source_end_lineno", 0) or lo
        if isinstance(lo, int) and lo > 0 and isinstance(hi, int) and hi >= lo:
            return f" (第{lo}~{hi}行)"
        return " (第?~?行)"

    def _get_port_type(node: NodeModel, node_def: NodeDef, port_name: str, *, is_input: bool) -> str:
        """安全获取端口类型：优先 overrides → 显式类型 → 动态类型 → 流程兜底 → 空字符串。"""
        # 流程端口优先判定（避免 overrides 误污染流程语义）
        if is_flow_port_name(str(port_name)):
            return "流程"

        # overrides：仅返回“非空、非泛型、非流程”的覆盖类型；否则返回空字符串
        override_type = resolve_override_type_for_node_port(
            port_type_overrides,
            str(getattr(node, "id", "") or ""),
            str(port_name),
        )
        if override_type:
            return str(override_type).strip()

        type_dict = node_def.input_types if is_input else node_def.output_types
        if port_name in type_dict:
            return str(type_dict.get(port_name, "") or "").strip()
        inferred = get_dynamic_port_type(
            str(port_name),
            dict(type_dict or {}),
            str(getattr(node_def, "dynamic_port_type", "") or ""),
        )
        if inferred:
            return str(inferred).strip()
        return ""

    def _normalize_enum_candidates(value: Any) -> List[str]:
        if not isinstance(value, list) or not value:
            return []
        return [str(x) for x in value if str(x).strip() != ""]
    
    def _is_flow(node: NodeModel, port_name: str, is_source: bool) -> bool:
        return is_flow_port_with_context(node, port_name, is_source, node_library)
    
    # 有效类型推断（GraphModel 级单一真源）：用于校验“泛型是否已实例化为具体类型”
    from engine.graph.port_type_effective_resolver import EffectivePortTypeResolver, is_generic_type_name

    effective_type_resolver = EffectivePortTypeResolver(
        model,
        node_def_resolver=_resolve_node_def,
        port_type_overrides=port_type_overrides,
    )

    # 规则：具体节点图中，不允许任何“数据端口”的有效类型仍为泛型家族。
    # - 无论是否连线/是否提供常量，只要该端口存在于图中，就必须被实例化为具体类型；
    # - 目的：避免画布出现“泛型”这种“类型集合”占位，强制作者在代码编写期通过
    #   连线/常量/类型注解（port_type_overrides）把每一次使用实例化为确定类型。
    #
    # 注意：
    # - 仅检查数据端口（流程端口跳过）；
    # - 该规则比“仅对已绑定端口检查”更严格，会推动 Graph Code 写法在生成期就把类型补齐。
    unresolved_ports: set[tuple[str, str, bool]] = set()
    for node in model.nodes.values():
        node_id = str(getattr(node, "id", "") or "")
        if not node_id:
            continue
        for port in (node.inputs or []):
            port_name = str(getattr(port, "name", "") or "")
            if not port_name or _is_flow(node, port_name, False):
                continue
            effective = effective_type_resolver.resolve(node_id, port_name, is_input=True)
            if is_generic_type_name(effective):
                unresolved_ports.add((node_id, port_name, True))
        for port in (node.outputs or []):
            port_name = str(getattr(port, "name", "") or "")
            if not port_name or _is_flow(node, port_name, True):
                continue
            effective = effective_type_resolver.resolve(node_id, port_name, is_input=False)
            if is_generic_type_name(effective):
                unresolved_ports.add((node_id, port_name, False))

    for node_id, port_name, is_input in sorted(unresolved_ports):
        node = model.nodes.get(node_id)
        if node is None:
            continue
        direction = "输入端" if is_input else "输出端"
        effective = effective_type_resolver.resolve(node_id, port_name, is_input=is_input)
        display = effective or "（未知）"
        errors.append(
            f"端口类型未实例化（仍为泛型）：节点 {node.category}/{node.title} 的{direction} '{port_name}'({display}){_node_span_text(node)}"
        )

    # 检查端口类型匹配：流程端口不能连接到数据端口
    # 说明：使用集中式的上下文感知判定，覆盖"多分支"等语义特殊节点。

    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        dst_node = model.nodes.get(edge.dst_node)

        if not src_node or not dst_node:
            continue

        span_text = _edge_span_text(src_node, dst_node)

        # 判断源端口和目标端口的类型（结合节点上下文和节点库定义）
        src_is_flow = _is_flow(src_node, edge.src_port, True)
        dst_is_flow = _is_flow(dst_node, edge.dst_port, False)

        # 流程端口和数据端口不能互连
        if src_is_flow != dst_is_flow:
            src_type = "流程端口" if src_is_flow else "数据端口"
            dst_type = "流程端口" if dst_is_flow else "数据端口"
            errors.append(
                f"端口类型不匹配：{src_node.title}.{edge.src_port}({src_type}) → "
                f"{dst_node.title}.{edge.dst_port}({dst_type}){span_text}"
            )
            continue

        # 数据端口：禁止“仍为泛型家族”的连线（必须在具体图里实例化为明确类型）
        if (not src_is_flow) and (not dst_is_flow):
            src_effective = effective_type_resolver.resolve(str(edge.src_node), str(edge.src_port), is_input=False)
            dst_effective = effective_type_resolver.resolve(str(edge.dst_node), str(edge.dst_port), is_input=True)
            if is_generic_type_name(src_effective) or is_generic_type_name(dst_effective):
                src_display = src_effective or "（未知）"
                dst_display = dst_effective or "（未知）"
                errors.append(
                    "数据端口类型未实例化（仍为泛型）："
                    f"{src_node.title}.{edge.src_port}({src_display}) → "
                    f"{dst_node.title}.{edge.dst_port}({dst_display}){span_text}"
                )
                continue

        # 枚举端口校验（仅对数据端口）：
        # - 枚举输入端口禁止连接非枚举类型；
        # - 若目标枚举输入端口声明了候选集合（input_enum_options），则要求来源枚举集合一致。
        if (not src_is_flow) and (not dst_is_flow):
            src_def = _resolve_node_def(src_node)
            dst_def = _resolve_node_def(dst_node)
            if src_def is not None and dst_def is not None:
                dst_port_type = _get_port_type(dst_node, dst_def, edge.dst_port, is_input=True)
                if dst_port_type == "枚举":
                    src_port_type = _get_port_type(src_node, src_def, edge.src_port, is_input=False)
                    if src_port_type != "枚举":
                        src_type_display = src_port_type or "（未知）"
                        errors.append(
                            f"枚举输入端口禁止连接非枚举：{src_node.title}.{edge.src_port}({src_type_display}) → "
                            f"{dst_node.title}.{edge.dst_port}(枚举){span_text}"
                        )
                        continue

                    src_candidates = _normalize_enum_candidates(
                        (getattr(src_def, "output_enum_options", {}) or {}).get(edge.src_port)
                    )
                    dst_candidates = _normalize_enum_candidates(
                        (getattr(dst_def, "input_enum_options", {}) or {}).get(edge.dst_port)
                    )
                    if src_candidates and dst_candidates and set(src_candidates) != set(dst_candidates):
                        src_display = "、".join(src_candidates)
                        dst_display = "、".join(dst_candidates)
                        errors.append(
                            "枚举端口候选集合不匹配："
                            f"{src_node.title}.{edge.src_port}(允许：{src_display}) → "
                            f"{dst_node.title}.{edge.dst_port}(允许：{dst_display}){span_text}"
                        )
    
    for node in model.nodes.values():
        # 流程入口校验（事件节点除外）
        if node.category != '事件节点':
            incoming = incoming_counts.get(node.id, {})
            for port in node.inputs:
                if _is_flow(node, port.name, False) and port.name != '跳出循环':
                    in_count = incoming.get(port.name, 0)
                    is_virtual_pin = virtual_pin_mappings.get((node.id, port.name), False)
                    if in_count == 0 and not is_virtual_pin:
                        lo = getattr(node, 'source_lineno', 0)
                        hi = getattr(node, 'source_end_lineno', 0) or lo
                        span_text = f" (第{lo}~{hi}行)" if isinstance(lo, int) and lo > 0 else " (第?~?行)"
                        errors.append(f"节点 {node.category}/{node.title} 的流程入口 '{port.name}' 未连接{span_text}")
        
        incoming = incoming_counts.get(node.id, {})
        for port in node.inputs:
            if not _is_flow(node, port.name, False):
                has_incoming_edge = incoming.get(port.name, 0) > 0
                has_constant_value = port.name in node.input_constants
                is_virtual_pin = virtual_pin_mappings.get((node.id, port.name), False)
                if not (has_incoming_edge or has_constant_value or is_virtual_pin):
                    # 结构体节点（拆分/拼装/修改）：
                    # UI 中允许通过“结构体绑定元数据”或“已出现动态字段端口”来隐式确定结构体，
                    # 此时源码未显式传入“结构体名”也应视为已配置，避免误报缺线。
                    if (
                        getattr(node, "title", "") in STRUCT_NODE_TITLES
                        and port.name == STRUCT_NAME_PORT_NAME
                    ):
                        bound = getattr(model, "get_node_struct_binding", None)
                        has_binding = False
                        if callable(bound):
                            payload = bound(node.id)
                            has_binding = isinstance(payload, dict) and bool(payload)

                        if has_binding:
                            continue

                        # 若存在任一“非静态输入端口”（字段端口），也视为已绑定结构体。
                        static_inputs = set()
                        if getattr(node, "title", "") == STRUCT_MODIFY_NODE_TITLE:
                            static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
                        elif getattr(node, "title", "") == STRUCT_BUILD_NODE_TITLE:
                            static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
                        elif getattr(node, "title", "") == STRUCT_SPLIT_NODE_TITLE:
                            static_inputs = set(STRUCT_SPLIT_STATIC_INPUTS)

                        has_dynamic_field_port = any(
                            (getattr(p, "name", "") not in static_inputs)
                            and (not _is_flow(node, getattr(p, "name", ""), False))
                            for p in (node.inputs or [])
                        )
                        if has_dynamic_field_port:
                            continue

                    lo = getattr(node, 'source_lineno', 0)
                    hi = getattr(node, 'source_end_lineno', 0) or lo
                    span_text = f" (第{lo}~{hi}行)" if isinstance(lo, int) and lo > 0 else " (第?~?行)"
                    errors.append(f"节点 {node.category}/{node.title} 的输入端 \"{port.name}\" 缺少数据来源{span_text}")

                # 输入端已绑定（连线/常量/虚拟引脚）：其有效类型必须可确定，禁止仍为泛型
                if has_incoming_edge or has_constant_value or is_virtual_pin:
                    effective = effective_type_resolver.resolve(str(node.id), str(port.name), is_input=True)
                    if is_generic_type_name(effective):
                        display = effective or "（未知）"
                        errors.append(
                            f"输入端口类型未实例化（仍为泛型）：节点 {node.category}/{node.title} 的输入端 '{port.name}'({display}){_node_span_text(node)}"
                        )

    # 输出端被消费（存在数据出边）：其有效类型必须可确定，禁止仍为泛型
    outgoing_data_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        if src_node is None:
            continue
        if _is_flow(src_node, edge.src_port, True):
            continue
        outgoing_data_counts[str(edge.src_node)][str(edge.src_port)] += 1
    for node in model.nodes.values():
        out_counts = outgoing_data_counts.get(str(node.id), {})
        for port in (node.outputs or []):
            if _is_flow(node, port.name, True):
                continue
            if out_counts.get(str(port.name), 0) <= 0:
                continue
            effective = effective_type_resolver.resolve(str(node.id), str(port.name), is_input=False)
            if is_generic_type_name(effective):
                display = effective or "（未知）"
                errors.append(
                    f"输出端口类型未实例化（仍为泛型）：节点 {node.category}/{node.title} 的输出端 '{port.name}'({display}){_node_span_text(node)}"
                )

    # 枚举输入常量校验：
    # - 当枚举输入端口未接线时，若存在常量则必须为字符串；
    # - 若节点定义声明了 input_enum_options，则常量值必须落在候选集合内。
    for node in model.nodes.values():
        node_def = _resolve_node_def(node)
        if node_def is None:
            continue
        # enum.equals 走“动态绑定”校验（见下方），避免在这里重复报错
        if str(getattr(node_def, "semantic_id", "") or "").strip() == "enum.equals":
            continue

        for port in (node.inputs or []):
            if _is_flow(node, port.name, False):
                continue
            if incoming_counts.get(node.id, {}).get(port.name, 0) > 0:
                continue
            if port.name not in (node.input_constants or {}):
                continue

            port_type = _get_port_type(node, node_def, port.name, is_input=True)
            if port_type != "枚举":
                continue

            value = (node.input_constants or {}).get(port.name)
            if not isinstance(value, str):
                errors.append(
                    f"枚举输入端口常量类型非法：节点 {node.category}/{node.title} 的输入端 '{port.name}' "
                    f"期望字符串枚举值，但实际为 {type(value).__name__}{_node_span_text(node)}"
                )
                continue

            candidates = _normalize_enum_candidates(
                (getattr(node_def, "input_enum_options", {}) or {}).get(port.name)
            )
            if candidates and value not in candidates:
                allowed_display = "、".join(candidates)
                errors.append(
                    f"枚举字面量不在候选集合内：节点 {node.category}/{node.title} 的输入端 '{port.name}' "
                    f"期望枚举值之一（{allowed_display}），实际为 '{value}'{_node_span_text(node)}"
                )

    # enum.equals（动态枚举候选集合绑定）：
    # 若任一枚举输入端口连线来源可确定枚举候选集合，则要求该节点所有枚举输入端口共享同一集合；
    # 未接线的枚举输入端口若使用常量，则常量值必须落在该集合内。
    for node in model.nodes.values():
        node_def = _resolve_node_def(node)
        if node_def is None:
            continue
        if str(getattr(node_def, "semantic_id", "") or "").strip() != "enum.equals":
            continue

        enum_ports = [
            str(port_name)
            for port_name, port_type in (getattr(node_def, "input_types", {}) or {}).items()
            if str(port_type) == "枚举"
        ]
        if not enum_ports:
            continue

        # 收集“已接线的枚举输入端口”来源候选集合
        port_to_candidates: Dict[str, List[str]] = {}
        for port_name in enum_ports:
            edges = list(incoming_edges_by_port.get((node.id, port_name), []) or [])
            if not edges:
                continue
            if len(edges) > 1:
                errors.append(
                    f"枚举输入端口存在多条数据连线：节点 {node.category}/{node.title} 的输入端 '{port_name}' "
                    f"当前有 {len(edges)} 条输入连线，无法确定枚举候选集合{_node_span_text(node)}"
                )
                continue
            edge = edges[0]
            src_node = model.nodes.get(getattr(edge, "src_node", ""))
            if src_node is None:
                continue
            src_def = _resolve_node_def(src_node)
            if src_def is None:
                continue

            src_type = _get_port_type(src_node, src_def, getattr(edge, "src_port", ""), is_input=False)
            if src_type != "枚举":
                src_type_display = src_type or "（未知）"
                errors.append(
                    f"枚举输入端口禁止连接非枚举：{src_node.title}.{edge.src_port}({src_type_display}) → "
                    f"{node.title}.{port_name}(枚举){_edge_span_text(src_node, node)}"
                )
                continue

            candidates = _normalize_enum_candidates(
                (getattr(src_def, "output_enum_options", {}) or {}).get(getattr(edge, "src_port", ""))
            )
            if candidates:
                port_to_candidates[port_name] = candidates

        unique_sets = {frozenset(v) for v in port_to_candidates.values() if v}
        if len(unique_sets) > 1:
            details = "；".join(
                f"{p}=允许：{'、'.join(cands)}"
                for p, cands in sorted(port_to_candidates.items(), key=lambda item: item[0])
            )
            errors.append(
                f"枚举候选集合不一致：节点 {node.category}/{node.title} 要求其枚举输入端口使用同一枚举集合，但当前为：{details}{_node_span_text(node)}"
            )
            continue

        if not unique_sets:
            # 无法从连线来源推断候选集合：保持宽松，不在结构层报错（交给 UI 或作者自行选择连线来源）
            continue

        group_set = next(iter(unique_sets))
        # 保持候选集合展示顺序尽量稳定：优先采用“最小端口名”的原始候选顺序，回退为排序后的集合。
        group_candidates: List[str] = []
        for p in sorted(port_to_candidates.keys()):
            cands = list(port_to_candidates.get(p) or [])
            if cands and frozenset(cands) == group_set:
                group_candidates = cands
                break
        if not group_candidates:
            group_candidates = sorted([str(x) for x in group_set if str(x).strip() != ""])
        for port_name in enum_ports:
            if incoming_counts.get(node.id, {}).get(port_name, 0) > 0:
                continue
            if port_name not in (node.input_constants or {}):
                continue
            value = (node.input_constants or {}).get(port_name)
            if not isinstance(value, str):
                errors.append(
                    f"枚举输入端口常量类型非法：节点 {node.category}/{node.title} 的输入端 '{port_name}' "
                    f"期望字符串枚举值，但实际为 {type(value).__name__}{_node_span_text(node)}"
                )
                continue
            if value not in group_candidates:
                allowed_display = "、".join(group_candidates)
                errors.append(
                    f"枚举字面量不在候选集合内：节点 {node.category}/{node.title} 的输入端 '{port_name}' "
                    f"期望枚举值之一（{allowed_display}），实际为 '{value}'{_node_span_text(node)}"
                )
    
    return errors


# ============================================================================
# 节点图代码解析器
# ============================================================================

class GraphParseError(Exception):
    """解析错误"""
    def __init__(self, message: str, line_number: Optional[int] = None):
        self.message = message
        self.line_number = line_number
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.line_number:
            return f"第{self.line_number}行: {self.message}"
        return self.message


class GraphCodeParser:
    """节点图代码解析器 - 从类结构 Python 文件解析节点图"""
    
    def __init__(
        self,
        workspace_path: Path,
        node_library: Optional[Dict[str, NodeDef]] = None,
        verbose: bool = False,
        *,
        strict: bool = True,
    ):
        """初始化解析器
        
        Args:
            workspace_path: 工作区根目录（workspace_root）
            node_library: 可选的节点库（如果为None，则自动加载）
            verbose: 是否输出详细日志
            strict: 严格模式（fail-closed）。启用后：
                - 语法糖重写阶段的任何 issue 都会导致解析直接失败；
                - IR 解析阶段的“语义不可可靠建模”的错误会导致解析失败；
                - 结构校验（validate_graph_model）报告的任何错误会导致解析失败；
              目标是“要么正确产图，要么报错”，避免静默生成错误节点图。
        """
        self.workspace_path = workspace_path
        self.verbose = verbose
        self.strict = bool(strict)
        if node_library is not None:
            self.node_library = node_library
        else:
            registry = get_node_registry(workspace_path, include_composite=True)
            self.node_library = registry.get_library()
        self._code_parser = CodeToGraphParser(
            self.node_library,
            verbose=self.verbose,
            workspace_path=self.workspace_path,
        )
        # 信号定义仓库：用于在 register_handlers 中接受“信号名”或 signal_id，并统一解析为 ID。
        # 使用延迟导入避免在引擎初始化早期引入 `engine.signal` → `engine.validate` → `engine.graph` 的循环依赖。
        self._signal_repo = None
    
    def parse_file(
        self,
        code_file: Path,
        *,
        tree: Optional[ast.Module] = None,
        assume_tree_already_rewritten: bool = False,
    ) -> Tuple[GraphModel, Dict[str, Any]]:
        """解析节点图代码文件为 GraphModel 和元数据
        
        Args:
            code_file: 文件路径
            tree: 可选的预解析 AST（通常用于 validate 阶段复用已改写的 AST，避免重复改写）
            assume_tree_already_rewritten: 若为 True，则假设传入/缓存的 AST 已完成语法糖归一化改写，解析器不会再次调用 rewrite_graph_code_*。
            
        Returns:
            (GraphModel, metadata字典)
            
        Raises:
            GraphParseError: 解析失败时抛出
        """
        # 文件路径用于错误信息
        file_path_str = str(code_file)
        
        # 1. 读取文件内容
        # 兼容 Windows 常见的 UTF-8 BOM，避免 ast.parse 因 U+FEFF 失败
        code = read_text(code_file)
        
        # 2. 仅支持类结构格式（虚拟挂载架构）。判定失败直接报错。
        if not is_class_structure_format(code):
            raise GraphParseError(
                f"当前节点图文件不符合类结构 Python 格式。文件: {file_path_str}"
            )
        # 新格式：类结构（虚拟挂载架构）
        return self._parse_class_structure(
            code,
            code_file,
            tree=tree,
            assume_tree_already_rewritten=assume_tree_already_rewritten,
        )
    
    def _parse_class_structure(
        self,
        code: str,
        code_file: Path,
        *,
        tree: Optional[ast.Module] = None,
        assume_tree_already_rewritten: bool = False,
    ) -> Tuple[GraphModel, Dict[str, Any]]:
        """解析类结构格式的节点图，委托CodeToGraphParser
        
        Args:
            code: 源代码
            code_file: 文件路径
            tree: 可选的预解析 AST
            assume_tree_already_rewritten: 若为 True，则跳过语法糖归一化改写（用于 validate 复用 ctx.ast_cache）
            
        Returns:
            (GraphModel, metadata)
        """
        # 1. 提取元数据（优先，供 scope-aware 的语法糖改写使用）
        metadata_obj = extract_metadata_from_code(code)
        apply_graph_path_inference(metadata_obj, file_path=code_file)
        scope = str((metadata_obj.graph_type or metadata_obj.scope or "server") or "server").strip().lower()

        assume_tree_already_rewritten_flag = bool(assume_tree_already_rewritten)
        if assume_tree_already_rewritten_flag and self.strict:
            raise GraphParseError(
                "严格模式下不支持 assume_tree_already_rewritten=True；"
                "请让解析器自行执行语法糖改写以收集 issue 并保证 fail-closed 行为一致。"
            )

        if tree is None:
            tree = ast.parse(code)
        if not isinstance(tree, ast.Module):
            raise TypeError("GraphCodeParser 仅支持 ast.Module 作为 tree")

        syntax_rewrite_issues: Sequence[object] = []
        list_literal_rewrite_issues: Sequence[object] = []
        dict_literal_rewrite_issues: Sequence[object] = []

        if not assume_tree_already_rewritten_flag:
            rewrite_config = build_graph_code_rewrite_config(is_composite=False)

            # 1.0 常见语法糖：下标读取/len/比较/and-or/+= 等，解析前统一改写为等价节点调用。
            # 额外：普通节点图允许启用“共享复合节点语法糖”（仅 server），
            # 例如：整数列表切片、sum/any/all、三元表达式等，会被改写为共享复合节点实例方法调用。
            # 注意：该改写为“纯语法等价转换”，不写回源码；非法写法由验证层报错。
            tree, syntax_rewrite_issues = rewrite_graph_code_syntax_sugars(
                tree,
                scope=scope,
                enable_shared_composite_sugars=rewrite_config.enable_shared_composite_sugars,
            )

            # 1.1 列表字面量语法糖：在类方法体内允许 `[...]`，解析前统一改写为【拼装列表】节点调用。
            # 注意：该改写为“纯语法等价转换”，不写回源码；若出现空列表/超长列表等非法写法，
            # 校验层会报告错误，解析层仅尽力生成图模型以供 UI/工具定位。
            tree, list_literal_rewrite_issues = rewrite_graph_code_list_literals(
                tree,
                max_elements=rewrite_config.max_list_literal_elements,
            )
            # 1.2 字典字面量语法糖：在类方法体内允许 `{k: v}`，解析前统一改写为【拼装字典】节点调用。
            # 注意：该改写为“纯语法等价转换”，不写回源码；若出现空字典/超长/展开等非法写法，
            # 校验层会报告错误，解析层仅尽力生成图模型以供 UI/工具定位。
            tree, dict_literal_rewrite_issues = rewrite_graph_code_dict_literals(
                tree,
                max_pairs=rewrite_config.max_dict_literal_pairs,
            )

        if self.strict:
            strict_messages: List[str] = []

            def _append_rewrite_issue(issues: Sequence[object]) -> None:
                for issue in list(issues or []):
                    code_text = str(getattr(issue, "code", "") or "").strip()
                    message_text = str(getattr(issue, "message", "") or "").strip()
                    node = getattr(issue, "node", None)
                    line_no = getattr(node, "lineno", None) if node is not None else None
                    line_prefix = f"第{int(line_no)}行: " if isinstance(line_no, int) and line_no > 0 else ""
                    if code_text:
                        strict_messages.append(f"{line_prefix}{code_text}: {message_text or '<no message>'}")
                    else:
                        strict_messages.append(f"{line_prefix}{message_text or '<no message>'}")

            _append_rewrite_issue(syntax_rewrite_issues)
            _append_rewrite_issue(list_literal_rewrite_issues)
            _append_rewrite_issue(dict_literal_rewrite_issues)

            if strict_messages:
                raise GraphParseError(
                    f"严格模式：检测到不支持/不可归一化的语法糖写法，已拒绝解析：\n"
                    f"文件: {str(code_file.resolve())}\n"
                    + "\n".join(f"- {msg}" for msg in strict_messages)
                )
        metadata = {
            "graph_id": metadata_obj.graph_id,
            "graph_name": (metadata_obj.graph_name or "未命名节点图"),
            "graph_type": (metadata_obj.graph_type or "server"),
            "folder_path": metadata_obj.folder_path,
            "description": metadata_obj.description,
            "graph_variables": metadata_obj.graph_variables,
            "dynamic_ports": metadata_obj.dynamic_ports,
        }
        
        graph_name = metadata.get("graph_name", "未命名节点图")
        
        # 2. 委托CodeToGraphParser解析
        graph_model = self._code_parser.parse_code(
            code,
            graph_name,
            tree=tree,
            scope=scope,
            folder_path=str(metadata_obj.folder_path or ""),
        )

        # 2.0 关键：在 strict 模式执行结构校验（validate_graph_model）前，
        # 必须先把 docstring/代码元数据同步到 GraphModel，否则会出现口径漂移：
        # - graph_type 未写入时，节点库查找可能错过 `#{scope}` 变体；
        # - graph_variables 未写入时，【设置节点图变量】的 变量值 类型无法从变量表反推，
        #   结构校验会误报“泛型未实例化”并导致 strict fail-closed 中断批量导出。
        graph_model.metadata["parsed_from_class_structure"] = True
        graph_model.metadata["graph_type"] = metadata.get("graph_type", "server")
        graph_model.metadata["folder_path"] = str(metadata.get("folder_path", "") or "")
        if metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]

        # 2.1 写入源文件路径（相对 workspace_root），供语义 pass 按资源根作用域做迁移归一。
        workspace_root = self.workspace_path.resolve()
        code_path = code_file.resolve()
        root_parts = workspace_root.parts
        path_parts = code_path.parts
        relative_str = ""
        if len(path_parts) >= len(root_parts) and path_parts[: len(root_parts)] == root_parts:
            tail_parts = path_parts[len(root_parts) :]
            if tail_parts:
                relative_str = "/".join(tail_parts)
            else:
                relative_str = code_path.name
        else:
            # 不在工作区下时，保存文件名以避免绝对路径
            relative_str = code_path.name
        graph_model.metadata["source_file"] = relative_str
        graph_model.metadata["parsed_at"] = datetime.now().isoformat()

        # 2.2 语义元数据统一生成（单点写入）：signal_bindings/struct_bindings + 变量名迁移归一等。
        GraphSemanticPass.apply(model=graph_model)

        if self.strict:
            ir_errors = graph_model.metadata.get("ir_errors")
            if isinstance(ir_errors, list) and any(str(x or "").strip() for x in ir_errors):
                messages = [str(x) for x in ir_errors if str(x or "").strip()]
                raise GraphParseError(
                    f"严格模式：IR 解析检测到无法可靠建模的写法，已拒绝解析：\n"
                    f"文件: {str(code_file.resolve())}\n"
                    + "\n".join(f"- {msg}" for msg in messages)
                )

            structure_errors = validate_graph_model(
                graph_model,
                workspace_path=self.workspace_path,
                node_library=self.node_library,
            )
            if structure_errors:
                raise GraphParseError(
                    f"严格模式：图结构校验未通过，已拒绝解析：\n"
                    f"文件: {str(code_file.resolve())}\n"
                    + "\n".join(f"- {msg}" for msg in structure_errors)
                )
        
        # 3. 设置元数据到GraphModel（补齐展示字段；graph_type/graph_variables 已在 strict 校验前写入）
        graph_model.graph_id = metadata.get("graph_id", graph_model.graph_id)
        graph_model.graph_name = graph_name
        graph_model.description = metadata.get("description", "")
        graph_model.metadata["parsed_from_class_structure"] = True
        graph_model.metadata["graph_type"] = metadata.get("graph_type", "server")
        graph_model.metadata["folder_path"] = str(metadata.get("folder_path", "") or "")

        # client 节点图：对齐“新建图模板”自带锚点节点坐标（平移整张图），避免自动布局把锚点偏移后
        # 导致 UI 自动化在“跳过创建锚点节点”时无法正确校准与定位。
        graph_type_text = str(graph_model.metadata.get("graph_type", "") or "").strip().lower()
        folder_path_text = str(graph_model.metadata.get("folder_path", "") or "")
        if graph_type_text == "client" and folder_path_text:
            anchor_titles = get_builtin_anchor_titles_for_client_graph(folder_path=folder_path_text)
            if anchor_titles:
                primary_anchor_title = str(anchor_titles[0] or "")
                anchor_node = None
                for node in graph_model.nodes.values():
                    if getattr(node, "title", "") == primary_anchor_title:
                        anchor_node = node
                        break
                if anchor_node is not None:
                    anchor_x = float(anchor_node.pos[0])
                    anchor_y = float(anchor_node.pos[1])
                    dx = 0.0 - anchor_x
                    dy = 0.0 - anchor_y
                    if (dx != 0.0) or (dy != 0.0):
                        for node in graph_model.nodes.values():
                            node.pos = (float(node.pos[0]) + dx, float(node.pos[1]) + dy)
        
        # 同步 docstring/代码中的图变量（保持与上方 strict 前同步逻辑一致；非 strict 路径也需要）
        if metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]
        
        # 6. 提取并关联注释
        associate_comments_to_nodes(code, graph_model)
        
        if self.verbose:
            print(f"[OK] 成功解析节点图: {graph_name}")
            print(f"  节点数: {len(graph_model.nodes)}, 连线数: {len(graph_model.edges)}")
        
        return graph_model, metadata
    
    def _apply_constant_bindings_from_code(
        self,
        tree: ast.Module,
        graph_model: GraphModel,
    ) -> None:
        """从 Graph Code 中的常量变量声明推导节点输入常量。

        约定：
        - 支持形如 `变量名: "类型" = <常量>` 或 `变量名 = <常量>` 的简单常量变量；
        - 常量变量仅在作为节点调用参数时生效：不再通过连线提供数据来源，
          而是直接写入对应节点的 `input_constants[端口名]`。
        """
        if not isinstance(tree, ast.Module):
            return

        graph_class = find_graph_class(tree)
        if graph_class is None:
            return

        all_nodes: List[NodeModel] = list(graph_model.nodes.values())
        if not all_nodes:
            return

        # 收集模块顶层的简单常量声明（AnnAssign/Assign，右值为字面量），
        # 例如：地点/配置等命名常量，供事件方法体内引用时回填到节点输入常量。
        global_const_values: Dict[str, str] = {}
        for top_stmt in tree.body:
            if isinstance(top_stmt, ast.AnnAssign):
                target = getattr(top_stmt, "target", None)
                value = getattr(top_stmt, "value", None)
                if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
                    name_text = target.id.strip()
                    if name_text != "":
                        global_const_values[name_text] = str(value.value)
            elif isinstance(top_stmt, ast.Assign):
                targets = list(getattr(top_stmt, "targets", []) or [])
                value = getattr(top_stmt, "value", None)
                if len(targets) == 1 and isinstance(targets[0], ast.Name) and isinstance(value, ast.Constant):
                    name_text = targets[0].id.strip()
                    if name_text != "":
                        global_const_values[name_text] = str(value.value)

        node_library = self.node_library
        node_name_index = getattr(self._code_parser, "node_name_index", None)
        if node_name_index is None:
            from engine.graph.common import node_name_index_from_library

            node_name_index = node_name_index_from_library(node_library)

        for item in graph_class.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if not item.name.startswith("on_"):
                continue

            stmts: List[ast.stmt] = list(item.body or [])
            if not stmts:
                continue

            method_lineno = getattr(item, "lineno", 0) or 0
            method_end_lineno = getattr(item, "end_lineno", method_lineno) or method_lineno
            if not isinstance(method_lineno, int) or method_lineno <= 0:
                continue
            if not isinstance(method_end_lineno, int) or method_end_lineno < method_lineno:
                method_end_lineno = method_lineno

            method_nodes: List[NodeModel] = []
            for node in all_nodes:
                node_start = getattr(node, "source_lineno", 0) or 0
                node_end = getattr(node, "source_end_lineno", node_start) or node_start
                if not isinstance(node_start, int) or node_start <= 0:
                    continue
                if not isinstance(node_end, int) or node_end < node_start:
                    node_end = node_start
                if node_end < method_lineno or node_start > method_end_lineno:
                    continue
                method_nodes.append(node)

            if not method_nodes:
                continue

            tracker = ParamUsageTracker(
                param_names=[],
                node_name_index=node_name_index,
                node_library=node_library,
                verbose=self.verbose,
                state_attr_to_param=None,
            )

            # 预填充模块级命名常量，使其在调用参数中可被视为常量变量。
            if global_const_values:
                for var_name, const_val in global_const_values.items():
                    if var_name not in tracker.const_var_values:
                        tracker.const_var_values[var_name] = const_val

            tracker.collect_constants(stmts)
            if not tracker.const_var_values:
                continue

            tracker.backfill_constants_to_nodes(stmts, method_nodes)

