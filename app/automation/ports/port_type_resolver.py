from __future__ import annotations

"""port_type_resolver: 面向“展示/只读推断”的端口有效类型解析（无 UI 依赖）。

定位：
- 本模块解决“节点库声明为泛型，但在具体图里可推断出实例化类型”的展示需求；
- 供 UI 画布（GraphScene）与 Todo 任务详情等场景复用，避免各处各写一套推断规则；
- **不落盘、不改 GraphModel**：只负责计算返回值。

类型来源（优先级大体）：
- GraphModel.metadata["port_type_overrides"]（例如变量中文类型注解写入的输出端口覆盖）
- NodeModel.input_types/output_types 快照（非泛型时直接采用）
- 节点特例：拼装字典的 键*/值* 端口按输出字典别名类型收敛
- 输入常量（NodeModel.input_constants）/ 本节点输入派生
- 连线结构推断（入边/出边）
- 声明/动态类型回退

说明：
- 这里的“有效类型”是展示级语义：推断失败允许回退到声明/泛型；
- 调用方可通过 `default_when_unknown` 控制最终兜底文案（例如 UI 用“泛型”，Todo 用“字符串”）。

实现说明：
- 具体推断规则已收敛到引擎侧 `engine.graph.port_type_effective_resolver`，本模块仅保留对外稳定 API
  与对 executor（NodeDef 获取方式）的适配，避免资源层与 UI 层各维护一套推断逻辑。
"""

from dataclasses import dataclass
import weakref
from typing import Any, Dict

from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.graph.port_type_effective_resolver import (
    EffectivePortTypeResolver,
    is_generic_type_name,
)
from engine.type_registry import TYPE_FLOW


@dataclass(frozen=True)
class _EffectivePortTypeResolverCacheEntry:
    edges_revision: int
    resolver: EffectivePortTypeResolver


# GraphModel -> {executor_id: cached_resolver}
#
# 说明：
# - EffectivePortTypeResolver 构造期会扫描全图 edges 并构建入/出边索引；
#   若在画布端口布局中为每个端口都重新构造，会导致启动/大图加载在 UI 线程内长时间阻塞。
# - GraphModel 提供 edges_revision 作为可靠失效条件：当连线发生变化（通过 GraphModel API 或显式 touch）
#   即可安全重建 resolver，避免类型推断使用旧边索引。
_EFFECTIVE_RESOLVER_CACHE: weakref.WeakKeyDictionary[
    GraphModel, dict[int, _EffectivePortTypeResolverCacheEntry]
] = weakref.WeakKeyDictionary()


def resolve_effective_port_type_for_model(
    *,
    port_name: str,
    node_model: NodeModel,
    graph_model: GraphModel,
    executor: Any,
    is_input: bool,
    is_flow: bool = False,
    edge_lookup=None,
    default_when_unknown: str = "泛型",
    fail_on_generic: bool = False,
) -> str:
    """解析端口在当前图中的“有效类型”（尽量具体；失败允许回退）。

    注意：该函数仅用于展示/只读推断；不写回 GraphModel。
    """
    if bool(is_flow):
        return TYPE_FLOW

    port_text = str(port_name or "").strip()
    if port_text == "":
        if bool(fail_on_generic):
            raise ValueError("端口名为空：无法解析有效类型。")
        return default_when_unknown or "泛型"

    node_id = str(getattr(node_model, "id", "") or "").strip()
    if node_id == "":
        if bool(fail_on_generic):
            raise ValueError(f"节点缺少 id：无法解析端口 {port_text!r} 的有效类型。")
        return default_when_unknown or "泛型"

    edges_revision = (
        int(graph_model.get_edges_revision())
        if hasattr(graph_model, "get_edges_revision")
        else int(getattr(graph_model, "_edges_revision", 0) or 0)
    )
    executor_id = int(id(executor)) if executor is not None else 0

    by_executor = _EFFECTIVE_RESOLVER_CACHE.get(graph_model)
    if by_executor is None:
        by_executor = {}
        _EFFECTIVE_RESOLVER_CACHE[graph_model] = by_executor

    cache_entry = by_executor.get(executor_id)
    if cache_entry is not None and int(cache_entry.edges_revision) == edges_revision:
        resolver = cache_entry.resolver
    else:
        # 引擎侧统一推断：保持与 graph_cache 的“有效类型缓存”同口径。
        getter = getattr(executor, "get_node_def_for_model", None) if executor is not None else None

        def _get_node_def(node: NodeModel) -> object:
            return getter(node) if callable(getter) else None

        resolver = EffectivePortTypeResolver(
            graph_model,
            node_def_resolver=_get_node_def,
        )
        by_executor[executor_id] = _EffectivePortTypeResolverCacheEntry(edges_revision=edges_revision, resolver=resolver)

    resolved = resolver.resolve(node_id, port_text, is_input=bool(is_input))
    resolved_text = str(resolved or "").strip()
    if resolved_text:
        if bool(fail_on_generic) and is_generic_type_name(resolved_text):
            title = getattr(node_model, "title", "")
            title_text = str(title) if isinstance(title, str) else ""
            raise ValueError(
                "端口有效类型仍为泛型家族："
                f"node_id={node_id!r} title={title_text!r} port={port_text!r} is_input={bool(is_input)}"
            )
        return resolved_text

    # 最终回退：仅当引擎侧有效类型推断未能给出结果时，才回退到模型快照。
    # 注意：NodeModel 当前约定只包含 input_types/output_types，且该快照可能因常量回填等原因
    # 在展示层表现为“字符串”；因此这里必须放在最后，避免覆盖正确的推断结果。
    snapshot_map = getattr(node_model, "input_types" if is_input else "output_types", {}) or {}
    if isinstance(snapshot_map, dict):
        snapshot_type = str(snapshot_map.get(port_text, "") or "").strip()
        if snapshot_type:
            if bool(fail_on_generic) and is_generic_type_name(snapshot_type):
                title = getattr(node_model, "title", "")
                title_text = str(title) if isinstance(title, str) else ""
                raise ValueError(
                    "端口类型快照仍为泛型家族："
                    f"node_id={node_id!r} title={title_text!r} port={port_text!r} is_input={bool(is_input)}"
                )
            return snapshot_type

    if bool(fail_on_generic):
        title = getattr(node_model, "title", "")
        title_text = str(title) if isinstance(title, str) else ""
        raise ValueError(
            "无法解析端口有效类型："
            f"node_id={node_id!r} title={title_text!r} port={port_text!r} is_input={bool(is_input)}"
        )
    return default_when_unknown or "泛型"


__all__ = [
    "resolve_effective_port_type_for_model",
]


