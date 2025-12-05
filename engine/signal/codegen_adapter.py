from __future__ import annotations

from typing import Any, Dict, List, Tuple

from engine.graph.models import GraphModel, NodeModel
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    SIGNAL_NAME_PORT_NAME,
    is_flow_port,
)
from engine.signal.binding_service import get_default_signal_binding_service, SignalBindingService


class SignalCodegenAdapter:
    """信号节点代码生成适配器。

    职责：
    - 统一处理图中【发送信号】/【监听信号】节点与运行时 GameRuntime.emit_signal /
      register_event_handler 之间的映射；
    - 屏蔽 GraphModel.metadata["signal_bindings"] 的细节，为可执行代码生成器提供
      “事件名 / emit 调用片段”的高层接口。
    """

    def __init__(self, binding_service: SignalBindingService | None = None) -> None:
        self._binding_service = binding_service or get_default_signal_binding_service()

    def is_signal_send_node(self, node: NodeModel) -> bool:
        return getattr(node, "title", "") == SIGNAL_SEND_NODE_TITLE

    def is_signal_listen_node(self, node: NodeModel) -> bool:
        return getattr(node, "title", "") == SIGNAL_LISTEN_NODE_TITLE

    def get_event_name_for_node(
        self,
        graph_model: GraphModel,
        event_node_id: str,
    ) -> str:
        """根据事件节点与绑定信息推导 register_event_handler 使用的事件名。

        - 普通事件节点：直接使用节点标题；
        - 监听信号节点：优先使用绑定的 signal_id，缺失时回退到节点标题。
        """
        node = graph_model.nodes.get(event_node_id)
        if node is None:
            return ""
        title = getattr(node, "title", "") or ""
        if title != SIGNAL_LISTEN_NODE_TITLE:
            return title
        bound_signal_id = self._binding_service.get_node_signal_id(graph_model, event_node_id)
        if bound_signal_id:
            return bound_signal_id
        return title

    def generate_send_signal_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        input_params: Dict[str, str],
    ) -> List[str]:
        """为【发送信号】节点生成统一的 emit_signal 调用代码行。

        约定：
        - 事件名 = signal_id（来自 GraphModel.metadata["signal_bindings"]），
          若未绑定则回退为“信号名”输入端常量/表达式；
        - 目标实体来自“目标实体”输入端，缺省时回退为 self.owner_entity；
        - 其余非静态输入端作为参数字典并入事件上下文。
        """
        lines: List[str] = []

        bound_signal_id = self._binding_service.get_node_signal_id(graph_model, node.id) or ""
        if bound_signal_id:
            signal_id_expr = f'"{bound_signal_id}"'
        else:
            signal_id_expr = input_params.get(SIGNAL_NAME_PORT_NAME, '""')

        target_entity_expr = input_params.get("目标实体", "self.owner_entity")

        entries: List[str] = []
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
        for param_name, param_value in input_params.items():
            if param_name in static_inputs:
                continue
            entries.append(f'"{param_name}": {param_value}')
        params_expr = "{ " + ", ".join(entries) + " }" if entries else "{}"

        lines.append(
            f"self.game.emit_signal({signal_id_expr}, params={params_expr}, target_entity={target_entity_expr})"
        )
        return lines

    def build_listen_signal_output_mapping(
        self,
        event_node: NodeModel,
        use_event_kwargs: bool,
        event_param_names: List[str],
    ) -> Dict[Tuple[str, str], str]:
        """为监听信号事件节点构建“端口 → Python 表达式”的初始映射。

        - use_event_kwargs=True 时：从事件上下文中按端口名取值；
        - 否则：按 `event_param_names` 顺序将数据输出端口映射到方法参数。
        """
        mapping: Dict[Tuple[str, str], str] = {}

        if use_event_kwargs and getattr(event_node, "title", "") == SIGNAL_LISTEN_NODE_TITLE:
            for output_port in event_node.outputs:
                if is_flow_port(event_node, output_port.name, True):
                    continue
                param_name = output_port.name.replace(":", "").strip()
                if not param_name:
                    continue
                mapping[(event_node.id, output_port.name)] = f'event_kwargs.get("{param_name}")'
            return mapping

        data_index = 0
        for output_port in event_node.outputs:
            if is_flow_port(event_node, output_port.name, True):
                continue
            if data_index >= len(event_param_names):
                break
            param_name = event_param_names[data_index]
            if param_name:
                mapping[(event_node.id, output_port.name)] = param_name
            data_index += 1
        return mapping


