from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from engine.graph.models import EdgeModel, GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.utils.graph.graph_algorithms import (
    group_nodes_by_event,
    group_nodes_by_event_with_topo_order,
)
from engine.utils.name_utils import make_valid_identifier


def group_by_event(
    graph_model: GraphModel,
    include_data_dependencies: bool = False,
) -> Dict[str, List[str]]:
    """统一的事件分组入口。

    - include_data_dependencies: 是否将数据依赖节点纳入事件流成员集合。
    - 直接委托 `engine.utils.graph.graph_algorithms.group_nodes_by_event`。
    """
    return group_nodes_by_event(graph_model, include_data_dependencies=include_data_dependencies)


def group_by_event_with_topo_order(
    graph_model: GraphModel,
    include_data_dependencies: bool = False,
) -> Dict[str, List[str]]:
    """事件分组（拓扑有序）统一入口。"""
    return group_nodes_by_event_with_topo_order(
        graph_model, include_data_dependencies=include_data_dependencies
    )


def format_constant(raw_value: Any) -> str:
    """将常量值格式化为合法的 Python 字面量字符串。

    规则：
    - 已包裹引号的字符串原样返回
    - None/True/False 原样返回
    - 纯数字（整数/浮点）原样返回
    - 容器字面量 ([{() 开头且成对闭合) 原样返回
    - 其他一律按字符串处理，使用双引号包裹，并转义内部双引号与反斜杠
    """
    s = str(raw_value).strip()
    if not s:
        return '""'

    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s

    if s in {"None", "True", "False"}:
        return s

    # 保留特定表达式（由上层注入的标识）
    if s == "self.owner_entity":
        return s

    body = s.lstrip('+-')
    is_int = body.isdigit()
    is_float = False
    if not is_int:
        parts = body.split('.')
        is_float = (
            len(parts) == 2 and
            all(part.isdigit() for part in parts if part != '') and
            any(part != '' for part in parts)
        )
    if is_int or is_float:
        return s

    if (s.startswith('[') and s.endswith(']')) or (s.startswith('{') and s.endswith('}')) or (s.startswith('(') and s.endswith(')')):
        return s

    escaped = s.replace('\\', r'\\').replace('"', r'\"')
    return f'"{escaped}"'


def collect_input_params(
    node: NodeModel,
    graph_model: GraphModel,
    var_mapping: Dict[Tuple[str, str], str],
) -> Dict[str, str]:
    """收集节点的数据输入参数，返回 {参数名: 参数值代码字符串}。

    - 跳过流程端口
    - 有连线则使用变量映射
    - 无连线则使用 node.input_constants；若缺省则使用空字符串
    - 可变参数端口保持端口名（如 "0~99"、"0","1"），供上层选择按位置/关键字生成
    """
    params: Dict[str, str] = {}
    data_inputs = [p for p in node.inputs if not is_flow_port(node, p.name, False)]

    data_input_index = _get_data_input_edge_index(graph_model)
    per_node_inputs = data_input_index.get(node.id, {})

    for port in data_inputs:
        connected_edge = per_node_inputs.get(port.name)
        if connected_edge is not None:
            source_key = (connected_edge.src_node, connected_edge.src_port)
            mapped = var_mapping.get(source_key)
            params[port.name] = mapped if mapped is not None else '"unknown"'
            continue

        if port.name in node.input_constants:
            raw_value = node.input_constants[port.name]
            params[port.name] = format_constant(raw_value)
        else:
            params[port.name] = '""'

    return params


def render_call_expression(func_name: str, primary_arg: str, extra_args: Iterable[str]) -> str:
    """统一的函数调用字符串生成工具（过滤空参数并保持顺序）。"""
    args = [primary_arg]
    args.extend(arg for arg in extra_args if arg)
    args_str = ", ".join(args)
    return f"{func_name}({args_str})"


def finalize_output_var_names(
    raw_names: Sequence[str],
    *,
    used_names: Optional[Set[str]] = None,
    counter: Optional[VarNameCounter] = None,
) -> List[str]:
    """规范化并去重输出变量名，必要时回退到统一生成策略。"""
    reserve = used_names if used_names is not None else set()
    finalized: List[str] = []
    for raw in raw_names:
        candidate = make_valid_identifier(raw or "")
        if not candidate or candidate == "_":
            candidate = _fallback_var_name(counter)
        while candidate in reserve:
            candidate = _fallback_var_name(counter, base=candidate)
        reserve.add(candidate)
        finalized.append(candidate)
    return finalized


def _fallback_var_name(counter: Optional[VarNameCounter], base: Optional[str] = None) -> str:
    if counter is not None:
        return generate_unique_var_name(counter)
    seed = base or "value"
    return f"{seed}_var"


def _get_data_input_edge_index(graph_model: GraphModel) -> Dict[str, Dict[str, EdgeModel]]:
    cache = getattr(graph_model, "_cached_data_input_edges", None)
    cache_version = getattr(graph_model, "_cached_data_input_edges_version", None)
    current_version = len(graph_model.edges)

    if cache is not None and cache_version == current_version:
        return cache

    index: Dict[str, Dict[str, EdgeModel]] = {}
    for edge in graph_model.edges.values():
        dst_node = graph_model.nodes.get(edge.dst_node)
        if dst_node is None:
            continue
        if is_flow_port(dst_node, edge.dst_port, False):
            continue
        per_node = index.setdefault(edge.dst_node, {})
        per_node.setdefault(edge.dst_port, edge)

    setattr(graph_model, "_cached_data_input_edges", index)
    setattr(graph_model, "_cached_data_input_edges_version", current_version)
    return index


class VarNameCounter:
    """简单的递增计数器，用于生成唯一变量名。"""

    def __init__(self, start: int = 0) -> None:
        if start < 0:
            raise ValueError("start must be non-negative")
        self._value = int(start)

    def next(self) -> int:
        self._value += 1
        return self._value


def generate_unique_var_name(counter: VarNameCounter) -> str:
    """统一的 var_ 命名策略。"""
    return f"var_{counter.next()}"


def choose_output_var_names(
    node: NodeModel,
    output_ports: List[Any],
    *,
    prefer_custom_names: bool = True,
    fallback: str = "port_name",  # "port_name" | "generated"
    counter: Optional[VarNameCounter] = None,
) -> List[str]:
    """为数据输出端口选择变量名。

    - prefer_custom_names=True 时优先使用 `node.custom_var_names`（支持 list 或 dict[name->var] 两种约定）
    - fallback:
        - "port_name": 使用端口名
        - "generated": 使用统一的 var_ 生成（要求提供 counter）
    """
    names: List[str] = []
    custom_map: Dict[str, str] = {}
    if hasattr(node, 'custom_var_names') and node.custom_var_names:
        if isinstance(node.custom_var_names, dict):
            custom_map = {str(k): str(v) for k, v in node.custom_var_names.items()}
        elif isinstance(node.custom_var_names, list):
            # list 对应输出序号
            for idx, port in enumerate(output_ports):
                if idx < len(node.custom_var_names):
                    custom_map[str(getattr(port, 'name', str(idx)))] = str(node.custom_var_names[idx])

    for idx, port in enumerate(output_ports):
        port_name = getattr(port, 'name', f"out_{idx}")
        chosen: Optional[str] = None
        if prefer_custom_names and port_name in custom_map:
            chosen = custom_map[port_name]
        if chosen is None:
            if fallback == "port_name":
                chosen = port_name
            elif fallback == "generated":
                if counter is None:
                    raise ValueError("counter is required when fallback='generated'")
                chosen = generate_unique_var_name(counter)
            else:
                raise ValueError("invalid fallback option")
        names.append(chosen)

    return names


# 统一流程端口判定入口（优先上下文，回退名称匹配）
def is_flow_port(node: Optional[Any], port_name: str, is_source: bool) -> bool:
    """
    统一的流程端口判定：
    - 若提供了 node（具备 title/inputs/outputs 等属性），优先使用上下文感知判定；
    - 否则回退到基于名称的快速判定。
    """
    if node is not None:
        return is_flow_port_with_context(node, port_name, is_source)
    return is_flow_port_name(port_name)


# 统一：Python 类型 ↔ 引脚类型 映射（供解析/生成双向使用）
PYTHON_TYPE_TO_PIN_TYPE: Dict[str, str] = {
    "float": "浮点数",
    "int": "整数",
    "str": "字符串",
    "bool": "布尔值",
    "list": "列表",
    "dict": "字典",
}
PIN_TYPE_TO_PYTHON_TYPE: Dict[str, str] = {v: k for k, v in PYTHON_TYPE_TO_PIN_TYPE.items()}


def validate_pin_type_annotation(type_name: str, allow_python_builtin: bool = False) -> str:
    """验证端口类型标注是否合法
    
    规则：
    - 优先接受中文端口类型（整数、浮点数、字符串、布尔值、实体、三维向量等）
    - 可选接受Python内置类型（int、float、str等），会自动转换为中文类型
    - 未识别的类型回退为"泛型"
    
    Args:
        type_name: 类型名称
        allow_python_builtin: 是否允许Python内置类型（True时自动转换）
        
    Returns:
        规范化的端口类型名称
        
    Raises:
        ValueError: 当不允许Python内置类型但使用了时
    """
    from engine.configs.rules.datatype_rules import BASE_TYPES, LIST_TYPES
    
    # 允许的中文类型集合
    allowed_types: set = set(BASE_TYPES.keys()) | set(LIST_TYPES.keys())
    allowed_types.update({"泛型", "字典", "列表", "泛型列表", "流程"})
    
    type_name = type_name.strip()
    # 严禁旧称与 Any（从源头掐灭）
    if type_name in {"通用", "Any", "any", "ANY"}:
        raise ValueError(f"不支持的类型标注 '{type_name}'：请使用“泛型”")
    
    # 已是中文类型，直接返回
    if type_name in allowed_types:
        return type_name
    
    # Python内置类型处理
    if type_name in PYTHON_TYPE_TO_PIN_TYPE:
        if allow_python_builtin:
            return PYTHON_TYPE_TO_PIN_TYPE[type_name]
        raise ValueError(
            f"不支持的类型标注 '{type_name}'：复合节点应使用中文端口类型"
            f"（如：整数/浮点数/字符串/布尔值/字典/列表/泛型/…）"
        )
    
    # 未识别的类型，回退为"泛型"
    return "泛型"
    

def node_name_index_from_library(node_library: Dict[str, NodeDef]) -> Dict[str, str]:
    """统一的节点名称“同义/别名”索引构建。

    规则：
    - key 形如 \"类别/节点名\"
    - 节点名原样→索引
    - 若节点名中包含'/'，同时收录：去掉斜杠 的别名
    - 注意：仅按第一个'/'分割类别；名称部分可能继续包含'/'（如“激活/关闭*”）
    """
    index: Dict[str, str] = {}
    for full_key in node_library.keys():
        if '/' in full_key:
            category, node_name = full_key.split('/', 1)
            _ = category  # 占位，强调此处确实分割但不使用左侧
            index[node_name] = full_key
            if '/' in node_name:
                index.setdefault(node_name.replace('/', ''), full_key)
    return index


# 流程端口与占位符名称（集中定义，供引擎/UI/自动化复用）
FLOW_PORT_PLACEHOLDER: str = "flow"
# 标准流程输出端口名（节点定义与 UI 展示中的中文名称）
FLOW_OUT_PORT_NAMES: Tuple[str, ...] = ("流程出", "是", "否", "默认", "循环体", "循环完成")
# 标准流程输入端口名（含“跳出循环”等特殊入口）
FLOW_IN_PORT_NAMES: Tuple[str, ...] = ("流程入", "跳出循环")
# 分支类流程端口常见别名（英文/中文混用场景统一收敛到此）
FLOW_BRANCH_PORT_ALIASES: Tuple[str, ...] = ("true", "false", "是", "否", "默认", "循环体", "循环完成")
# 兼容旧代码的聚合常量：包含所有常见流程输出口以及“跳出循环”
FLOW_SPECIAL_OUTPUT_NAMES: Tuple[str, ...] = FLOW_OUT_PORT_NAMES + (FLOW_IN_PORT_NAMES[-1],)


# 分支/循环节点名称集合与判定
BRANCH_NODE_NAMES: Tuple[str, ...] = ("双分支", "多分支")
LOOP_NODE_NAMES: Tuple[str, ...] = ("有限循环", "列表迭代循环")


def is_branch_node_name(node_name: str) -> bool:
    return node_name in BRANCH_NODE_NAMES


def is_loop_node_name(node_name: str) -> bool:
    return node_name in LOOP_NODE_NAMES


# 信号节点标题与静态端口名（集中定义，避免 UI 层散落硬编码）
SIGNAL_SEND_NODE_TITLE: str = "发送信号"
SIGNAL_LISTEN_NODE_TITLE: str = "监听信号"

SIGNAL_SEND_STATIC_INPUTS: Tuple[str, ...] = ("流程入", "目标实体", "信号名")
SIGNAL_LISTEN_STATIC_OUTPUTS: Tuple[str, ...] = ("流程出", "事件源实体", "事件源GUID", "信号来源实体")


# 结构体节点标题与静态端口名（集中定义，便于 UI / 代码生成共享）
STRUCT_SPLIT_NODE_TITLE: str = "拆分结构体"
STRUCT_BUILD_NODE_TITLE: str = "拼装结构体"
STRUCT_MODIFY_NODE_TITLE: str = "修改结构体"

STRUCT_NODE_TITLES: Tuple[str, ...] = (
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
)

# 静态端口合集：便于 UI 在追加动态端口时跳过这些固定入口/出口
STRUCT_SPLIT_STATIC_INPUTS: Tuple[str, ...] = ("结构体实例",)
STRUCT_SPLIT_STATIC_OUTPUTS: Tuple[str, ...] = ()

STRUCT_BUILD_STATIC_INPUTS: Tuple[str, ...] = ()
STRUCT_BUILD_STATIC_OUTPUTS: Tuple[str, ...] = ("结果",)

STRUCT_MODIFY_STATIC_INPUTS: Tuple[str, ...] = ("流程入", "结构体实例")
STRUCT_MODIFY_STATIC_OUTPUTS: Tuple[str, ...] = ("流程出",)


# 选择端口判定（供 UI/自动化复用）
def is_selection_input_port(node: Optional[Any], port_name: str) -> bool:
    """
    判断给定输入端口是否应视为“选择端口”（不可通过连线传入，只保留行内输入控件）。

    约定（逐步扩展）：
    - 【发送信号/监听信号】节点的“信号名”输入端口视为选择端口，只能通过信号选择对话框或行内编辑设置；
      · 该端口不会出现在连线起点/终点的候选集合中；
      · 仍作为普通数据输入参与代码生成，值来源于 `node.input_constants["信号名"]`。
    """
    if node is None:
        return False

    title = getattr(node, "title", "") or ""
    name = str(port_name or "")

    # 信号相关节点：发送信号/监听信号 的“信号名”输入端口
    if title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE) and name == "信号名":
        return True

    return False


# 静音布局调用：统一保存/恢复调试开关
def apply_layout_quietly(graph_model: GraphModel) -> None:
    from engine.layout import layout_by_event_regions
    from engine.configs.settings import settings
    _old = settings.LAYOUT_DEBUG_PRINT
    settings.LAYOUT_DEBUG_PRINT = False
    layout_by_event_regions(graph_model)
    settings.LAYOUT_DEBUG_PRINT = _old


