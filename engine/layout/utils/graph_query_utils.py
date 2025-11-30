"""
图查询工具函数模块

提供图结构查询、节点判断、边统计等工具函数。
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set, List, Union, Callable, Dict, Tuple, TYPE_CHECKING

from engine.graph.models import GraphModel, NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.configs.settings import settings
from ..core.constants import (
    NODE_HEIGHT_DEFAULT,
    UI_NODE_HEADER_HEIGHT,
    UI_ROW_HEIGHT,
    UI_NODE_PADDING,
    UI_HEADER_EXTRA,
    UI_CATEGORY_EXTRA_HEIGHT,
    CATEGORY_EVENT,
    CATEGORY_FLOW_CTRL,
    TITLE_MULTI_BRANCH,
    PORT_EXIT_LOOP,
    ORDER_MAX_FALLBACK,
)
from engine.nodes.node_registry import get_node_registry
DEFAULT_MAX_CHAINS_PER_NODE = 64
DEFAULT_MAX_CHAINS_PER_START = 256
DEFAULT_MAX_CHAINS_PER_BLOCK = 800


@dataclass(frozen=True)
class ChainTraversalBudget:
    max_per_block: int
    max_per_node: int
    max_per_start: int


@dataclass(frozen=True)
class ChainPathsResult:
    paths: List[Tuple[List[str], Optional[str], bool]]
    exhausted: bool = False


def get_chain_traversal_budget() -> ChainTraversalBudget:
    max_per_block = getattr(settings, "LAYOUT_MAX_CHAIN_PLACEMENTS_PER_BLOCK", DEFAULT_MAX_CHAINS_PER_BLOCK)
    if not isinstance(max_per_block, int) or max_per_block <= 0:
        max_per_block = DEFAULT_MAX_CHAINS_PER_BLOCK

    max_per_node = getattr(settings, "LAYOUT_MAX_CHAINS_PER_NODE", DEFAULT_MAX_CHAINS_PER_NODE)
    if not isinstance(max_per_node, int) or max_per_node <= 0:
        max_per_node = DEFAULT_MAX_CHAINS_PER_NODE

    max_per_start = getattr(settings, "LAYOUT_MAX_CHAINS_PER_START", DEFAULT_MAX_CHAINS_PER_START)
    if not isinstance(max_per_start, int) or max_per_start <= 0:
        max_per_start = DEFAULT_MAX_CHAINS_PER_START

    return ChainTraversalBudget(
        max_per_block=max_per_block,
        max_per_node=max_per_node,
        max_per_start=max_per_start,
    )



if TYPE_CHECKING:
    from ..core.layout_context import LayoutContext


def _make_pure_data_checker(model: GraphModel) -> Callable[[str], bool]:
    def _checker(node_id: str) -> bool:
        return is_pure_data_node(node_id, model)

    return _checker


def _resolve_data_in_edges_fetcher(
    model: GraphModel,
    custom_fetcher: Optional[Callable[[str], List]] = None,
) -> Callable[[str], List]:
    if custom_fetcher:
        return custom_fetcher

    def _default_fetch(node_id: str) -> List:
        dst_node = model.nodes.get(node_id)
        if not dst_node:
            return []
        edges: List = []
        for edge in model.edges.values():
            if edge.dst_node != node_id:
                continue
            dst_port = dst_node.get_input_port(edge.dst_port)
            if dst_port and not is_flow_port_name(dst_port.name):
                edges.append(edge)
        return edges

    return _default_fetch


def build_chain_signature(
    nodes_list: List[str],
    src_flow_id: Optional[str],
    is_flow_origin: bool,
    extra: Optional[Tuple[Any, ...]] = None,
) -> Tuple[Any, ...]:
    """统一的链条签名，用于去重，可附加额外上下文。"""
    base = (tuple(nodes_list), src_flow_id if is_flow_origin else None, bool(is_flow_origin))
    if extra:
        return base + extra
    return base


def _deduplicate_paths(
    path_list: List[Tuple[List[str], Optional[str], bool]]
) -> List[Tuple[List[str], Optional[str], bool]]:
    seen: Set[Tuple[Any, ...]] = set()
    deduped: List[Tuple[List[str], Optional[str], bool]] = []
    for nodes_list, src_flow_id, is_flow_origin in path_list:
        signature = build_chain_signature(nodes_list, src_flow_id, is_flow_origin)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append((nodes_list, src_flow_id, is_flow_origin))
    return deduped


def build_edge_indices(
    model: GraphModel,
) -> Tuple[Dict[str, List], Dict[str, List], Dict[str, List], Dict[str, List]]:
    """
    构建流程/数据边的输入输出索引，供布局上下文与块上下文复用。

    Returns:
        (flow_out_by_node, flow_in_by_node, data_out_by_node, data_in_by_node)
    """
    flow_out_by_node: Dict[str, List] = {}
    flow_in_by_node: Dict[str, List] = {}
    data_out_by_node: Dict[str, List] = {}
    data_in_by_node: Dict[str, List] = {}
    if not model:
        return flow_out_by_node, flow_in_by_node, data_out_by_node, data_in_by_node

    for edge in model.edges.values():
        src_id = edge.src_node
        dst_id = edge.dst_node
        dst_node = model.nodes.get(dst_id)
        if not dst_node:
            continue
        dst_port = dst_node.get_input_port(edge.dst_port)
        is_flow_target = bool(dst_port and is_flow_port_name(dst_port.name))

        if is_flow_target:
            flow_out_by_node.setdefault(src_id, []).append(edge)
            flow_in_by_node.setdefault(dst_id, []).append(edge)
        else:
            data_out_by_node.setdefault(src_id, []).append(edge)
            data_in_by_node.setdefault(dst_id, []).append(edge)

    return flow_out_by_node, flow_in_by_node, data_out_by_node, data_in_by_node


def get_ordered_flow_out_edges(
    layout_context: "LayoutContext",
    node_id: str,
) -> List[Tuple[str, str]]:
    """根据端口顺序返回节点的流程输出边。"""
    if layout_context is None:
        return []
    edges = layout_context.get_out_flow_edges(node_id)
    if not edges:
        return []
    ordered = sorted(
        edges,
        key=lambda edge: layout_context.get_output_port_index(node_id, edge.src_port),
    )
    result: List[Tuple[str, str]] = []
    for edge in ordered:
        if getattr(edge, "dst_node", None):
            result.append((edge.src_port, edge.dst_node))
    return result


# ==================== 数据链遍历工具（通用复用） ====================

def collect_data_chain_paths(
    model: GraphModel,
    start_data_id: str,
    flow_id_set: Set[str],
    skip_data_ids: Set[str] = None,
    get_data_in_edges_func: Callable = None,
    include_skip_node_as_terminus: bool = False,
    layout_context: Optional["LayoutContext"] = None,
    shared_cache: Optional[Dict[str, List[Tuple[List[str], Optional[str], bool]]]] = None,
    budget: Optional[ChainTraversalBudget] = None,
    max_results: Optional[int] = None,
) -> ChainPathsResult:
    """
    收集从指定数据节点出发的所有可能路径（支持多条链共享节点）
    
    通用数据链遍历函数，可被布局、代码生成、分析等模块复用。
    
    优化（方案C）：使用记忆化避免重复计算，并应用限流防止指数爆炸。
    
    Args:
        model: 图模型
        start_data_id: 起始数据节点ID
        flow_id_set: 流程节点ID集合
        skip_data_ids: 跨块边界节点集合（可选）
        get_data_in_edges_func: 获取数据输入边的函数（可选，若未提供则全图扫描）
        include_skip_node_as_terminus: 若为True，遇到skip_data_ids节点时将其作为链的终点返回（触发复制逻辑）；
                                        若为False，遇到skip_data_ids节点时停止搜索不包含该节点（默认）
        shared_cache: 可选的跨起点记忆化结果缓存，允许不同起点复用相同子问题的路径结果
        
    Returns:
        路径列表: [(链节点序列, 上游流程ID, 是否为流程起源链), ...]
        - 链节点序列：从消费者到上游的节点ID列表
        - 上游流程ID：若链起源于流程输出，则为该流程节点ID
        - 是否为流程起源链：True表示链终止于流程输出
    """
    skip_data_ids = skip_data_ids or set()
    traversal_budget = budget or get_chain_traversal_budget()
    memo: Dict[str, List[Tuple[List[str], Optional[str], bool]]] = (
        shared_cache if shared_cache is not None else {}
    )
    is_pure_node = _make_pure_data_checker(model)
    get_data_in_edges = _resolve_data_in_edges_fetcher(model, get_data_in_edges_func)

    exhausted_due_to_limits = False

    def _fallback_input_port_index(node_obj: Optional[NodeModel], port_name: str) -> int:
        if not node_obj:
            return 10**6
        for index, port in enumerate(node_obj.inputs):
            if port.name == port_name:
                return index
        return 10**6

    def _collect_recursive(data_id: str, visiting: Set[str]) -> List[Tuple[List[str], Optional[str], bool]]:
        nonlocal exhausted_due_to_limits
        """递归收集路径（优化：记忆化 + 限流）"""
        if data_id in visiting:
            return []
        if not is_pure_node(data_id):
            return []
        # 跨块边界处理
        if data_id in skip_data_ids:
            if include_skip_node_as_terminus:
                # 作为链的终点返回（触发复制逻辑）
                return [([data_id], None, False)]
            else:
                # 不继续搜索，不包含该节点
                return []

        # 优化（方案C）：检查记忆化缓存
        if data_id in memo:
            return memo[data_id]

        visiting.add(data_id)
        data_node_obj = model.nodes.get(data_id)
        upstream_edges_raw = get_data_in_edges(data_id)
        upstream_edges: List = list(upstream_edges_raw) if upstream_edges_raw else []

        # 按端口顺序排序（兼容 copy-on-write 代理）
        if data_node_obj and upstream_edges:
            if layout_context is not None:
                upstream_edges = sorted(
                    upstream_edges,
                    key=lambda edge: layout_context.get_input_port_index(data_node_obj.id, edge.dst_port),
                )
            else:
                upstream_edges = sorted(
                    upstream_edges,
                    key=lambda edge: _fallback_input_port_index(data_node_obj, edge.dst_port),
                )

        # 终止条件1（修正）：若存在"流程→数据"的上游边，记录其来源，但仍需展开其余纯数据上游
        flow_sources: List[Tuple[str, int]] = []
        for edge in upstream_edges:
            if edge.src_node in flow_id_set:
                if data_node_obj and layout_context is not None:
                    port_index = layout_context.get_input_port_index(data_node_obj.id, edge.dst_port)
                else:
                    port_index = _fallback_input_port_index(data_node_obj, edge.dst_port)
                flow_sources.append((edge.src_node, port_index))

        chosen_flow_src: Optional[str] = None
        is_flow_origin_here: bool = False
        if flow_sources:
            flow_sources.sort(key=lambda pair: pair[1])
            chosen_flow_src = flow_sources[0][0]
            is_flow_origin_here = True

        # 收集所有上游纯数据节点的路径（端口公平 + 轮转合并）
        all_paths: List[Tuple[List[str], Optional[str], bool]] = []

        # 预计算每条上游输入边的子路径列表（保持端口序）
        per_input_subpaths: List[List[Tuple[List[str], Optional[str], bool]]] = []
        for edge in upstream_edges:
            # 仅考虑纯数据上游
            upstream_id = edge.src_node
            if upstream_id in flow_id_set:
                continue
            if not is_pure_node(upstream_id):
                continue
            # 跨块边界：
            # - 当 include_skip_node_as_terminus=True 时，将边界节点作为链的叶子一并返回，
            #   使边界节点本身仍然参与链编号与调试信息（便于跨块复制场景查看完整链条）；
            # - 当 include_skip_node_as_terminus=False 时，遇到 skip 节点即终止且不纳入结果。
            if upstream_id in skip_data_ids:
                if include_skip_node_as_terminus:
                    per_input_subpaths.append([([data_id, upstream_id], None, False)])
                continue

            subpaths = _collect_recursive(upstream_id, visiting)
            if subpaths:
                subpaths = _deduplicate_paths(subpaths)
            # 将子路径改写为当前起点前缀
            prefixed: List[Tuple[List[str], Optional[str], bool]] = []
            for nodes_list, src_flow_id, is_flow_origin in subpaths:
                prefixed.append(([data_id] + nodes_list, src_flow_id, is_flow_origin))
            per_input_subpaths.append(prefixed)

        # 若没有可展开的纯数据上游：
        # - 若存在流程来源，则以当前节点为终点，保留流程来源信息
        # - 否则，以自身为终止路径（与既有逻辑一致）
        if not per_input_subpaths:
            result = [([data_id], chosen_flow_src, is_flow_origin_here)]
            visiting.remove(data_id)
            memo[data_id] = result
            return result

        max_per_node = traversal_budget.max_per_node
        min_per_input = getattr(settings, "LAYOUT_MIN_PATHS_PER_INPUT", 1)
        if min_per_input < 0:
            min_per_input = 0

        # Phase 1: 端口公平预分配
        if min_per_input > 0:
            for sublist in per_input_subpaths:
                take_count = min(min_per_input, len(sublist))
                for index in range(take_count):
                    nodes_list, src_flow_id, is_flow_origin = sublist[index]
                    # 若本节点存在流程来源，则覆盖来源与标记
                    if is_flow_origin_here and chosen_flow_src is not None:
                        all_paths.append((nodes_list, chosen_flow_src, True))
                    else:
                        all_paths.append(sublist[index])
                    if max_per_node > 0 and len(all_paths) >= max_per_node:
                        exhausted_due_to_limits = True
                        break
                if max_per_node > 0 and len(all_paths) >= max_per_node:
                    exhausted_due_to_limits = True
                    break

        # Phase 2: 轮转合并其余路径
        if max_per_node <= 0 or len(all_paths) < max_per_node:
            pointers = [min_per_input for _ in per_input_subpaths]
            exhausted = False
            while not exhausted:
                progressed = False
                for index, sublist in enumerate(per_input_subpaths):
                    pointer = pointers[index]
                    if pointer < len(sublist):
                        nodes_list, src_flow_id, is_flow_origin = sublist[pointer]
                        if is_flow_origin_here and chosen_flow_src is not None:
                            all_paths.append((nodes_list, chosen_flow_src, True))
                        else:
                            all_paths.append(sublist[pointer])
                        pointers[index] = pointer + 1
                        progressed = True
                        if max_per_node > 0 and len(all_paths) >= max_per_node:
                            exhausted = True
                            exhausted_due_to_limits = True
                            break
                if not progressed:
                    exhausted = True

        # 终止条件2：若最终仍为空（极端情况），回退为自身
        if not all_paths:
            all_paths = [([data_id], None, False)]

        all_paths = _deduplicate_paths(all_paths)

        visiting.remove(data_id)
        # 优化（方案C）：缓存结果
        memo[data_id] = all_paths
        return all_paths

    # 收集路径
    result = _collect_recursive(start_data_id, set())

    budget_exhausted = exhausted_due_to_limits

    per_start_limit = traversal_budget.max_per_start
    if per_start_limit > 0 and len(result) > per_start_limit:
        budget_exhausted = True
        result = result[:per_start_limit]

    if max_results is not None and max_results > 0 and len(result) > max_results:
        budget_exhausted = True
        result = result[:max_results]

    return ChainPathsResult(paths=result, exhausted=budget_exhausted)


def collect_upstream_data_closure(
    model: GraphModel,
    start_data_id: str,
    skip_data_ids: Set[str] = None,
    get_data_in_edges_func: Callable = None,
    respect_skip_ids: bool = True,
) -> List[str]:
    """
    收集从指定节点出发的完整上游闭包（所有纯数据上游，直到遇到流程口停止）
    
    通用上游闭包收集函数，用于复制场景或依赖分析。
    
    Args:
        model: 图模型
        start_data_id: 起始数据节点ID
        skip_data_ids: 跨块边界节点集合（可选）
        get_data_in_edges_func: 获取数据输入边的函数（可选）
        respect_skip_ids: 是否将 skip_data_ids 视为递归边界；
            - True：遇到 skip 节点立即终止
            - False：忽略 skip 限制，继续穿透以获取完整闭包

    Returns:
        上游闭包节点ID列表（不包括起始节点本身）
    """
    skip_data_ids = skip_data_ids or set()
    is_pure_node = _make_pure_data_checker(model)
    get_data_in_edges = _resolve_data_in_edges_fetcher(model, get_data_in_edges_func)

    def _collect_recursive(data_id: str, visited: Set[str]) -> List[str]:
        """递归收集上游闭包"""
        if data_id in visited:
            return []
        if not is_pure_node(data_id):
            return []

        visited.add(data_id)
        closure_nodes = []

        upstream_edges = get_data_in_edges(data_id)

        for edge in upstream_edges:
            upstream_id = edge.src_node

            # 遇到流程口停止
            if not is_pure_node(upstream_id):
                continue

            # 按需尊重跨块边界
            if respect_skip_ids and upstream_id in skip_data_ids:
                continue

            # 收集上游节点
            closure_nodes.append(upstream_id)

            # 递归收集上游的上游
            sub_closure = _collect_recursive(upstream_id, visited)
            closure_nodes.extend(sub_closure)

        return closure_nodes

    return _collect_recursive(start_data_id, set())


# ==================== 事件元数据辅助 ====================

def build_event_title_lookup(model: GraphModel) -> Dict[str, Optional[str]]:
    """
    构建事件节点 ID 到标题的映射，优先使用 GraphModel.event_flow_order / event_flow_titles。
    """
    lookup: Dict[str, Optional[str]] = {}
    order_list = list(getattr(model, "event_flow_order", []) or [])
    title_list = list(getattr(model, "event_flow_titles", []) or [])
    max_titles = len(title_list)

    for index, node_id in enumerate(order_list):
        if index < max_titles:
            lookup[node_id] = title_list[index]

    return lookup


def resolve_event_title(
    model: GraphModel,
    event_node_id: str,
    *,
    fallback_title: Optional[str] = None,
    title_lookup: Optional[Dict[str, Optional[str]]] = None,
) -> Optional[str]:
    """
    统一解析事件节点标题：先查映射，再回退到显式入参或节点自身 title。
    """
    lookup_source = title_lookup or build_event_title_lookup(model)
    if event_node_id in lookup_source:
        candidate = lookup_source[event_node_id]
        if candidate is not None:
            return candidate

    if fallback_title is not None:
        return fallback_title

    node = model.nodes.get(event_node_id)
    if node is not None:
        node_title = getattr(node, "title", None)
        if node_title is not None:
            return node_title

    return None


# ==================== 节点排序工具 ====================

def get_node_order_key(node: NodeModel) -> Tuple[int, str]:
    """
    获取节点的稳定排序键
    
    Args:
        node: 节点对象
        
    Returns:
        (source_lineno, node_id) 元组，用于稳定排序
    """
    lineno = getattr(node, "source_lineno", 0)
    lineno_key = lineno if isinstance(lineno, int) and lineno > 0 else ORDER_MAX_FALLBACK
    return (lineno_key, node.id)


# ==================== 与 UI 完全一致的高度估算（统一真源） ====================
_LAYOUT_WORKSPACE_ROOT: Optional[Path] = None
_NODE_REGISTRY = None
_ENTITY_INPUTS_BY_NAME: Optional[Dict[str, Set[str]]] = None
_VARIADIC_MIN_ARGS: Optional[Dict[str, int]] = None


def set_layout_workspace_root(workspace_path: Path) -> None:
    """
    注入布局工具可用的 workspace 根目录，并在路径变化时重置相关缓存。
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")
    resolved = workspace_path.resolve()
    global _LAYOUT_WORKSPACE_ROOT, _NODE_REGISTRY, _ENTITY_INPUTS_BY_NAME, _VARIADIC_MIN_ARGS
    if _LAYOUT_WORKSPACE_ROOT == resolved and _NODE_REGISTRY is not None:
        return
    _LAYOUT_WORKSPACE_ROOT = resolved
    _NODE_REGISTRY = None
    _ENTITY_INPUTS_BY_NAME = None
    _VARIADIC_MIN_ARGS = None


def _resolve_workspace_root() -> Path:
    if _LAYOUT_WORKSPACE_ROOT is not None:
        return _LAYOUT_WORKSPACE_ROOT
    return Path(__file__).resolve().parents[3]


def _ensure_node_registry() -> None:
    global _NODE_REGISTRY, _ENTITY_INPUTS_BY_NAME, _VARIADIC_MIN_ARGS
    if _NODE_REGISTRY is not None and _ENTITY_INPUTS_BY_NAME is not None and _VARIADIC_MIN_ARGS is not None:
        return
    workspace_root = _resolve_workspace_root()
    _NODE_REGISTRY = get_node_registry(workspace_root, include_composite=True)
    _ENTITY_INPUTS_BY_NAME = _NODE_REGISTRY.get_entity_input_params_by_func()
    _VARIADIC_MIN_ARGS = _NODE_REGISTRY.get_variadic_min_args()


def _is_variadic_input_node(node_obj: NodeModel) -> bool:
    _ensure_node_registry()
    assert _VARIADIC_MIN_ARGS is not None
    node_name = getattr(node_obj, "title", "") or ""
    return node_name in _VARIADIC_MIN_ARGS


def _is_entity_input_port(node_obj: NodeModel, port_name: str) -> bool:
    _ensure_node_registry()
    assert _ENTITY_INPUTS_BY_NAME is not None
    node_name = getattr(node_obj, "title", "") or ""
    ports = _ENTITY_INPUTS_BY_NAME.get(node_name)
    if ports is None:
        return False
    return str(port_name) in ports


def estimate_node_height_ui_exact_with_context(context, node_id: str) -> float:
    """
    与 UI 完全一致的节点高度估算（需要上下文以判断连线与端口类型）。

    规则对齐 ui/graph_scene.py::_layout_ports：
    - 输入端口：每个端口占1行
      · 若为非流程端口 且 未连线 且 端口类型非“实体”，再加1行（控件行）
    - 变参输入节点：左侧“+”按钮再占1行
    - 输出端口：每个端口占1行；多分支节点右侧“+”按钮再占1行
    - 高度：total_h = (max_rows * ROW_HEIGHT + NODE_PADDING) + (ROW_HEIGHT + UI_HEADER_EXTRA) + NODE_PADDING
    """
    if context is None or not hasattr(context, "model"):
        return NODE_HEIGHT_DEFAULT
    node_obj = context.model.nodes.get(node_id)
    if not node_obj:
        return NODE_HEIGHT_DEFAULT

    connected_input_ports: Set[str] = set()
    for edge in context.get_data_in_edges(node_id):
        if edge.dst_port:
            connected_input_ports.add(str(edge.dst_port))

    return _estimate_node_height_from_structure(node_obj, connected_input_ports)


def estimate_node_height_ui_exact_for_model(model: GraphModel, node_or_obj: Union[NodeModel, str]) -> float:
    """
    与 UI 完全一致的高度估算（仅依赖 GraphModel，不依赖布局上下文）。
    用于纯数据图布局等无法提供 BlockLayoutContext 的场景。
    """
    if model is None:
        return NODE_HEIGHT_DEFAULT
    if isinstance(node_or_obj, str):
        node_obj = model.nodes.get(node_or_obj)
    else:
        node_obj = node_or_obj
    if not node_obj:
        return NODE_HEIGHT_DEFAULT

    connected_input_ports: Set[str] = set()
    for edge in model.edges.values():
        if edge.dst_node == node_obj.id and edge.dst_port:
            connected_input_ports.add(str(edge.dst_port))

    return _estimate_node_height_from_structure(node_obj, connected_input_ports)


@dataclass(frozen=True)
class InputPortLayoutPlan:
    render_inputs: List[str]
    row_index_by_port: Dict[str, int]
    control_row_index_by_port: Dict[str, int]
    total_input_rows: int
    input_plus_rows: int

    @property
    def total_rows_with_plus(self) -> int:
        return self.total_input_rows + self.input_plus_rows


def build_input_port_layout_plan(
    node_obj: NodeModel,
    connected_input_ports: Set[str],
) -> InputPortLayoutPlan:
    """
    计算输入端口的渲染顺序与行索引布局计划（与 UI/布局共用）。
    """
    if not node_obj:
        return InputPortLayoutPlan([], {}, {}, 0, 0)

    is_variadic = _is_variadic_input_node(node_obj)
    render_input_names: List[str] = []
    for port in node_obj.inputs:
        port_name = str(port.name)
        is_flow = is_flow_port_name(port_name)
        if is_variadic and ("~" in port_name) and (not is_flow):
            continue
        render_input_names.append(port_name)

    row_index_by_port: Dict[str, int] = {}
    control_row_index_by_port: Dict[str, int] = {}
    current_row = 0

    for port_name in render_input_names:
        row_index_by_port[port_name] = current_row
        current_row += 1

        needs_control_row = (
            not is_flow_port_name(port_name)
            and port_name not in connected_input_ports
            and not _is_entity_input_port(node_obj, port_name)
        )
        if needs_control_row:
            control_row_index_by_port[port_name] = current_row
            current_row += 1

    total_input_rows = current_row
    input_plus_rows = 1 if is_variadic else 0

    return InputPortLayoutPlan(
        render_inputs=render_input_names,
        row_index_by_port=row_index_by_port,
        control_row_index_by_port=control_row_index_by_port,
        total_input_rows=total_input_rows,
        input_plus_rows=input_plus_rows,
    )


def _estimate_node_height_from_structure(
    node_obj: NodeModel,
    connected_input_ports: Set[str],
) -> float:
    """
    共享的节点高度估算实现：输入节点对象和已连接的输入端口集合。
    """
    if not node_obj:
        return NODE_HEIGHT_DEFAULT

    plan = build_input_port_layout_plan(node_obj, connected_input_ports)
    total_output_rows = len(node_obj.outputs)

    output_plus_rows = 1 if getattr(node_obj, "title", "") == TITLE_MULTI_BRANCH else 0

    max_rows = max(plan.total_rows_with_plus, total_output_rows + output_plus_rows, 1)

    content_height = float(max_rows) * UI_ROW_HEIGHT + UI_NODE_PADDING
    header_height = UI_ROW_HEIGHT + UI_HEADER_EXTRA
    total_height = header_height + content_height + UI_NODE_PADDING
    return float(total_height)


def is_pure_data_node(node_or_id: Union[NodeModel, str], model: Optional[GraphModel] = None) -> bool:
    """
    判断节点是否为纯数据节点（无任何流程端口）
    
    Args:
        node_or_id: 节点对象或节点ID
        model: 图模型（当传入节点ID时需要）
        
    Returns:
        True 如果节点是纯数据节点
    """
    if isinstance(node_or_id, str):
        if model is None:
            raise ValueError("When passing node_id, model parameter is required")
        node = model.nodes.get(node_or_id)
    else:
        node = node_or_id

    if not node:
        return False
    return not any(is_flow_port_name(port.name) for port in node.inputs + node.outputs)


def is_flow_output_port(node: NodeModel, port_name: str) -> bool:
    """
    判断一个输出端口是否作为流程口
    
    规则：
    - 常规基于端口名判断
    - 多分支节点：所有输出端口均视为流程口（含动态命名的分支）
    
    Args:
        node: 节点对象
        port_name: 端口名称
        
    Returns:
        True 如果是流程输出端口
    """
    return is_flow_port_name(port_name) or node.title == TITLE_MULTI_BRANCH


def is_data_edge(model: GraphModel, edge) -> bool:
    """
    判断边是否为数据边（目标端口为数据口）
    
    Args:
        model: 图模型
        edge: 边对象
        
    Returns:
        True 如果是数据边
    """
    dst_node = model.nodes.get(edge.dst_node)
    if not dst_node:
        return False
    dst_port = dst_node.get_input_port(edge.dst_port)
    return bool(dst_port and (not is_flow_port_name(dst_port.name)))


def is_jump_out_edge(model: GraphModel, src_node_id: str, dst_node_id: str) -> bool:
    """
    判断是否为"跳出循环"边：存在从 src→dst 的边，且目标端口名为"跳出循环"
    
    Args:
        model: 图模型
        src_node_id: 源节点ID
        dst_node_id: 目标节点ID
        
    Returns:
        True 如果是跳出循环边
    """
    dst_node_obj = model.nodes.get(dst_node_id)
    if not dst_node_obj:
        return False
    for edge in model.edges.values():
        if edge.src_node == src_node_id and edge.dst_node == dst_node_id:
            dst_port_obj = dst_node_obj.get_input_port(edge.dst_port)
            if dst_port_obj and dst_port_obj.name == PORT_EXIT_LOOP:
                return True
    return False


def count_outgoing_data_edges(
    model: GraphModel,
    data_node_id: str,
    data_out_index: Optional[dict] = None,
) -> int:
    """
    统计数据节点的输出连线数量（只统计数据连线，非流程）
    
    Args:
        model: 图模型
        data_node_id: 数据节点ID
        data_out_index: 可选的数据输出边索引（key=src_node_id, value=edge列表）
        
    Returns:
        数据输出边数量
    """
    src = model.nodes.get(data_node_id)
    if not src:
        return 0

    # 使用索引（如果提供）
    if data_out_index is not None:
        edges_to_check = data_out_index.get(data_node_id, [])
    else:
        # 回退到全图扫描
        edges_to_check = [edge for edge in model.edges.values() if edge.src_node == data_node_id]

    count = 0
    for edge in edges_to_check:
        dst = model.nodes.get(edge.dst_node)
        if dst:
            dst_port_obj = dst.get_input_port(edge.dst_port)
            if dst_port_obj and not is_flow_port_name(dst_port_obj.name):
                count += 1
    return count


def has_flow_edges(model: GraphModel) -> bool:
    """
    全图是否存在实际的流程连线（源为流程输出且目标为流程输入）
    
    Args:
        model: 图模型
        
    Returns:
        True 如果存在流程边
    """
    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        dst_node = model.nodes.get(edge.dst_node)
        if not src_node or not dst_node:
            continue
        src_port = src_node.get_output_port(edge.src_port)
        dst_port = dst_node.get_input_port(edge.dst_port)
        if src_port and dst_port and is_flow_output_port(src_node, src_port.name) and is_flow_port_name(dst_port.name):
            return True
    return False


def is_flow_edge(model: GraphModel, edge) -> bool:
    """
    判断一条边是否为流程边（兼容复合节点对外流程出口未包含“流程”关键字的命名）。

    判定规则（宽松）：
    - 若目标端口被识别为流程输入（如“流程入/是/否/默认/循环体/循环完成/跳出循环”），视为流程边；
    - 否则回退到：源端口名称规则被识别为流程输出。
    """
    if not edge:
        return False
    src_node = model.nodes.get(edge.src_node)
    dst_node = model.nodes.get(edge.dst_node)
    if not src_node or not dst_node:
        return False
    # 目标为流程输入 → 必然是流程边
    dst_port = dst_node.get_input_port(edge.dst_port)
    if dst_port and is_flow_port_name(dst_port.name):
        return True
    # 回退：源为流程输出 → 流程边
    src_port = src_node.get_output_port(edge.src_port)
    return bool(src_port and is_flow_output_port(src_node, src_port.name))


