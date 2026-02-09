from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info


def _resolve_signal_source_entity(game):
    """
    本地测试：为“发送信号”提供默认事件源实体。

    约定：
    - 优先复用名为“自身实体”的默认实体；
    - 若不存在且运行时支持创建 Mock 实体，则创建一次并缓存；
    - 无法获取/创建时返回 None（由下游 handler 自行决定是否依赖实体）。
    """
    cached = getattr(game, "_ayaya_local_sim_signal_source_entity", None)
    if cached is not None:
        return cached

    get_all_entities = getattr(game, "get_all_entities", None)
    if callable(get_all_entities):
        for e in list(get_all_entities()):
            if getattr(e, "name", None) == "自身实体":
                setattr(game, "_ayaya_local_sim_signal_source_entity", e)
                return e

    create_mock_entity = getattr(game, "create_mock_entity", None)
    if callable(create_mock_entity):
        e = create_mock_entity("信号来源实体")
        setattr(game, "_ayaya_local_sim_signal_source_entity", e)
        return e

    return None


@node_spec(
    name="发送信号",
    category="执行节点",
    semantic_id="signal.send",
    inputs=[
        ("流程入", "流程"),
        ("信号名", "字符串"),
    ],
    outputs=[("流程出", "流程")],
    dynamic_port_type="泛型",
    description="向关卡全局发送一个自定义信号，使用前需要先选择对应的信号名，然后才能正确的使用该信号的参数",
    doc_reference="服务器节点/执行节点/执行节点.md",
)
def 发送信号(game, 信号名: str, **kwargs):
    """向关卡全局发送一个自定义信号，使用前需要先选择对应的信号名，然后才能正确的使用该信号的参数。

    说明：
    - 本节点在本地测试（MockRuntime）中需要具备可执行语义，因此直接通过运行时事件系统触发；
    - 信号参数通过动态端口以关键字参数形式传入，原样并入事件上下文；
    - 事件上下文会自动补齐：事件源实体 / 事件源GUID / 信号来源实体。
    """
    signal_name = str(信号名 or "").strip()
    if not signal_name:
        raise ValueError("信号名不能为空")

    source_entity = _resolve_signal_source_entity(game)
    event_kwargs = {
        "事件源实体": source_entity,
        "事件源GUID": 0,
        "信号来源实体": source_entity,
        **dict(kwargs),
    }

    log_info("[发送信号] {}", signal_name)
    game.trigger_event(signal_name, **event_kwargs)
