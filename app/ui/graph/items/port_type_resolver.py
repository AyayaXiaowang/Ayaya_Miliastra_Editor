from __future__ import annotations

"""画布端口类型展示：GraphScene 适配器。

本模块不包含推断规则本身，只负责把 GraphScene/NodeModel 适配到
`app.automation.ports.port_type_resolver.resolve_effective_port_type_for_model`。

这样可确保画布端口与 Todo/自动化侧共享同一套“有效类型推断”规则，避免多处维护漂移。
"""

from typing import Any

from engine.type_registry import TYPE_FLOW

# 画布/预览端口类型展示必须与 Todo、graph_cache 写回共用同一口径：
# 统一走 app 层 facade，其底层委托 engine.graph.port_type_effective_resolver（单一真源）。
from app.automation.ports.port_type_resolver import resolve_effective_port_type_for_model


class _SceneExecutor:
    """最小 executor 适配器：把 GraphScene 的 get_node_def 能力转成推断工具需要的接口。"""

    def __init__(self, scene: object) -> None:
        self._scene = scene

    def get_node_def_for_model(self, model_node: Any) -> Any:
        getter = getattr(self._scene, "get_node_def", None)
        return getter(model_node) if callable(getter) else None

    def log(self, message: str, log_callback=None) -> None:
        # 画布类型展示默认不输出日志；仅满足推断工具接口契约
        if callable(log_callback):
            log_callback(str(message))


def resolve_effective_port_type_for_scene(
    scene: object,
    node_model: Any,
    port_name: str,
    *,
    is_input: bool,
    is_flow: bool,
) -> str:
    """解析画布端口当前图里的“有效类型”（尽量具体；失败则回退）。

    优先级（大体）：
    - overrides（显式中文类型注解）
    - 端口类型快照（非泛型）
    - 字典别名推导（针对“拼装字典”等典型泛型节点）
    - 输入常量推断（仅输入侧，且仅在声明为泛型家族时用于补全）
    - 连线推断（必要时覆盖低可信的字符串推断）
    - 声明类型 / 泛型兜底
    """
    if is_flow:
        return TYPE_FLOW

    graph_model = getattr(scene, "model", None)
    if graph_model is None or node_model is None:
        raise ValueError("GraphScene 缺少 GraphModel 或 NodeModel：无法解析端口有效类型。")

    # 性能关键：端口布局/绘制阶段会频繁解析端口类型。
    # 若每次都新建 executor，会导致下层“有效类型 resolver”缓存无法命中（按 executor 身份隔离）。
    cached_executor = getattr(scene, "_effective_port_type_scene_executor", None)
    if not isinstance(cached_executor, _SceneExecutor) or getattr(cached_executor, "_scene", None) is not scene:
        cached_executor = _SceneExecutor(scene)
        setattr(scene, "_effective_port_type_scene_executor", cached_executor)
    executor = cached_executor
    return resolve_effective_port_type_for_model(
        port_name=port_name,
        node_model=node_model,
        graph_model=graph_model,
        executor=executor,
        is_input=is_input,
        is_flow=is_flow,
        default_when_unknown="泛型",
        fail_on_generic=True,
    )


__all__ = ["resolve_effective_port_type_for_scene"]


