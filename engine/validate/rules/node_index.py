from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import keyword

from engine.nodes.node_registry import get_node_registry
from engine.nodes.constants import ALLOWED_SCOPES


def _expand_aliases(names: Set[str]) -> Set[str]:
    if not names:
        return set()
    alias: Set[str] = set(names)
    for name in list(names):
        if "/" in name:
            alias.add(name.replace("/", ""))
    return alias


def _is_safe_call_name(name: str) -> bool:
    text = str(name or "").strip()
    return bool(text) and text.isidentifier() and (not keyword.iskeyword(text))


def _split_name_scope(name_part: str) -> Tuple[str, Optional[str]]:
    """拆分 `名称#scope` → (名称, scope)；若无 `#` 则 scope 为 None。"""
    text = str(name_part or "")
    if "#" not in text:
        return text, None
    base, suffix = text.split("#", 1)
    return base, (suffix or None)


def _iter_callable_nodes(
    lib: Dict[str, object],
    *,
    scope_text: str,
) -> List[Tuple[str, object]]:
    """从节点库中抽取“可在 Graph Code 中以函数调用出现”的节点名列表。

    约定：
    - callable 名称取自节点库 key 的 “名称部分”（`类别/名称` → `名称`），因为 Graph Code 调用无法携带类别前缀；
    - 若存在 `名称#scope` 变体键：在对应 scope 下，将其映射回可调用名 `名称`（Graph Code 不写 `#scope`）。
    - 同名冲突时优先级：`名称#scope`（匹配当前 scope）优先于 `名称`。
    """
    chosen: Dict[str, Tuple[int, object]] = {}
    for full_key, node_def in (lib.items() if isinstance(lib, dict) else []):
        if not isinstance(full_key, str) or "/" not in full_key:
            continue
        if not hasattr(node_def, "is_available_in_scope"):
            continue
        if not bool(getattr(node_def, "is_available_in_scope")(scope_text)):
            continue
        _, name_part = full_key.split("/", 1)
        base_name, scope_suffix = _split_name_scope(name_part)
        if not _is_safe_call_name(base_name):
            continue

        # 仅接受：无后缀，或后缀与当前 scope 匹配（其它 scope 的变体在本 scope 下不可调用）
        if scope_suffix is None:
            priority = 1
        elif scope_suffix == scope_text:
            priority = 2
        else:
            continue

        existing = chosen.get(base_name)
        if existing is None or priority > existing[0]:
            chosen[base_name] = (priority, node_def)

    result: List[Tuple[str, object]] = [(name, pair[1]) for name, pair in chosen.items()]
    return result


@lru_cache(maxsize=8)
def callable_node_defs_by_name(
    workspace: Path,
    scope: str,
    *,
    include_composite: bool = True,
) -> Dict[str, object]:
    """返回 {可调用名: NodeDef} 映射（按 scope 规约 `名称#scope` 变体）。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"
    registry = get_node_registry(workspace, include_composite=bool(include_composite))
    lib = registry.get_library()
    mapping: Dict[str, object] = {}
    for call_name, node_def in _iter_callable_nodes(lib, scope_text=scope_text):
        mapping[str(call_name)] = node_def
    return mapping


@lru_cache(maxsize=8)
def node_function_names(workspace: Path, scope: str) -> Set[str]:
    """返回指定作用域下可用的节点函数名集合（含复合节点）。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for call_name, _ in _iter_callable_nodes(lib, scope_text=scope_text):
        names.add(call_name)
    return names


@lru_cache(maxsize=8)
def boolean_node_names(workspace: Path, scope: str) -> Set[str]:
    """返回指定作用域下“输出包含布尔类型”的节点名称集合。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for call_name, node_def in _iter_callable_nodes(lib, scope_text=scope_text):
        for _, port_type in (getattr(node_def, "output_types", {}) or {}).items():
            if isinstance(port_type, str) and ("布尔" in port_type):
                names.add(call_name)
                break
    return names


@lru_cache(maxsize=8)
def flow_node_names(workspace: Path, scope: str) -> Set[str]:
    """返回指定作用域下包含流程端口的节点名称集合。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for call_name, node_def in _iter_callable_nodes(lib, scope_text=scope_text):
        input_types = getattr(node_def, "input_types", {}) or {}
        output_types = getattr(node_def, "output_types", {}) or {}
        has_flow = (
            any((isinstance(t, str) and ("流程" in t)) for t in input_types.values())
            or any((isinstance(t, str) and ("流程" in t)) for t in output_types.values())
            or ("流程入" in (getattr(node_def, "inputs", []) or []))
            or ("流程出" in (getattr(node_def, "outputs", []) or []))
        )
        if has_flow:
            names.add(call_name)
    return names


@lru_cache(maxsize=8)
def data_query_node_names(workspace: Path, scope: str) -> Set[str]:
    """返回指定作用域下“查询/运算类”节点名称集合。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for call_name, node_def in _iter_callable_nodes(lib, scope_text=scope_text):
        category = getattr(node_def, "category", "") or ""
        if isinstance(category, str) and (("查询" in category) or ("运算" in category)):
            names.add(call_name)
    return names


@lru_cache(maxsize=8)
def event_node_names(workspace: Path, scope: str) -> Set[str]:
    """返回所有事件节点的名称集合（按节点库中的“事件节点”类别收集）。

    说明：
    - 仅依赖引擎侧节点库，不访问 assets 或 UI；
    - 结果用于代码层校验 register_event_handler 注册的事件名是否存在。
    """
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for _, node_def in lib.items():
        if not node_def.is_available_in_scope(scope_text):
            continue
        category = getattr(node_def, "category", "") or ""
        if isinstance(category, str) and ("事件" in category):
            names.add(node_def.name)
    return _expand_aliases(names)


@lru_cache(maxsize=8)
def variadic_min_args(workspace: Path, scope: str) -> Dict[str, int]:
    """返回指定作用域下可变参数节点的最少实参数要求：{函数名: 最小数量}。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    rules: Dict[str, int] = {}
    for call_name, node_def in _iter_callable_nodes(lib, scope_text=scope_text):
        inputs: List[str] = list(getattr(node_def, "inputs", []) or [])
        if not inputs:
            continue
        variadic_inputs: List[str] = [str(inp) for inp in inputs if "~" in str(inp)]
        if not variadic_inputs:
            continue
        rules[call_name] = 1 if len(variadic_inputs) == 1 else 2
    return rules


@lru_cache(maxsize=8)
def input_types_by_func(workspace: Path, scope: str) -> Dict[str, Dict[str, str]]:
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, str]] = {}
    for call_name, nd in _iter_callable_nodes(lib, scope_text=scope_text):
        result[call_name] = dict(getattr(nd, "input_types", {}) or {})
    return result


@lru_cache(maxsize=8)
def input_generic_constraints_by_func(workspace: Path, scope: str) -> Dict[str, Dict[str, List[str]]]:
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, List[str]]] = {}
    for call_name, nd in _iter_callable_nodes(lib, scope_text=scope_text):
        constraints = getattr(nd, "input_generic_constraints", {}) or {}
        if constraints:
            result[call_name] = {port: list(allowed or []) for port, allowed in constraints.items()}
    return result


@lru_cache(maxsize=8)
def input_enum_options_by_func(workspace: Path, scope: str) -> Dict[str, Dict[str, List[str]]]:
    """按函数名返回输入端口的枚举候选项映射。

    结构：
        {
          "开启定点运动器": {
              "移动方式": ["瞬间移动", "匀速直线运动"],
              "参数类型": ["固定速度", "固定时间"],
          },
          ...
        }
    仅当节点定义中显式声明了 input_enum_options 时才会出现在结果中。
    """
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, List[str]]] = {}
    for call_name, nd in _iter_callable_nodes(lib, scope_text=scope_text):
        options_raw = getattr(nd, "input_enum_options", {}) or {}
        if not isinstance(options_raw, dict) or not options_raw:
            continue
        options_normalized: Dict[str, List[str]] = {}
        for port_name, candidates in options_raw.items():
            if not isinstance(port_name, str) or port_name == "":
                continue
            if isinstance(candidates, list):
                options_normalized[port_name] = [str(c) for c in candidates if str(c)]
        if options_normalized:
            result[call_name] = options_normalized
    return result


@lru_cache(maxsize=8)
def output_types_by_func(workspace: Path, scope: str) -> Dict[str, List[str]]:
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, List[str]] = {}
    for call_name, nd in _iter_callable_nodes(lib, scope_text=scope_text):
        outs: List[str] = []
        for out_name in getattr(nd, "outputs", []) or []:
            outs.append((getattr(nd, "output_types", {}) or {}).get(out_name, ""))
        result[call_name] = outs
    return result


@lru_cache(maxsize=8)
def output_generic_constraints_by_func(workspace: Path, scope: str) -> Dict[str, Dict[str, List[str]]]:
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, List[str]]] = {}
    for call_name, nd in _iter_callable_nodes(lib, scope_text=scope_text):
        constraints = getattr(nd, "output_generic_constraints", {}) or {}
        if constraints:
            result[call_name] = {port: list(allowed or []) for port, allowed in constraints.items()}
    return result


def clear_node_index_caches() -> None:
    node_function_names.cache_clear()
    boolean_node_names.cache_clear()
    flow_node_names.cache_clear()
    data_query_node_names.cache_clear()
    event_node_names.cache_clear()
    variadic_min_args.cache_clear()
    input_types_by_func.cache_clear()
    input_generic_constraints_by_func.cache_clear()
    output_types_by_func.cache_clear()
    output_generic_constraints_by_func.cache_clear()
    input_enum_options_by_func.cache_clear()


