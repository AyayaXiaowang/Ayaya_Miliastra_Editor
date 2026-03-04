from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Set, Tuple


SEND_SIGNAL_NODE_TYPE_ID: int = 300000
LISTEN_SIGNAL_NODE_TYPE_ID: int = 300001
SERVER_SEND_SIGNAL_NODE_TYPE_ID: int = 300002
SIGNAL_NAME_PORT: str = "信号名"


def is_send_signal_node_type(node_type_id_int: int) -> bool:
    return int(node_type_id_int) == int(SEND_SIGNAL_NODE_TYPE_ID)


def is_listen_signal_node_type(node_type_id_int: int) -> bool:
    return int(node_type_id_int) == int(LISTEN_SIGNAL_NODE_TYPE_ID)


def is_server_send_signal_node_type(node_type_id_int: int) -> bool:
    """
    向服务器节点图发送信号（Send_Signal_To_Server, type_id=300002）。
    """
    return int(node_type_id_int) == int(SERVER_SEND_SIGNAL_NODE_TYPE_ID)


def should_use_send_signal_meta_binding(
    *,
    node_type_id_int: int | None,
    graph_node_id: str,
    send_signal_nodes_with_signal_name_in_edge: Set[str],
) -> bool:
    """
    Send_Signal(300000) 的“信号名静态绑定”启用条件：
    - 仅对 Send_Signal 节点生效
    - 且该节点的“信号名”端口不存在 data 入边（否则视为动态信号名）
    """
    if not isinstance(node_type_id_int, int):
        return False
    if not is_send_signal_node_type(int(node_type_id_int)):
        return False
    return str(graph_node_id) not in set(send_signal_nodes_with_signal_name_in_edge or set())


def should_use_listen_signal_meta_binding(
    *,
    node_type_id_int: int | None,
    graph_node_id: str,
    listen_signal_nodes_with_signal_name_in_edge: Set[str],
) -> bool:
    if not isinstance(node_type_id_int, int):
        return False
    if not is_listen_signal_node_type(int(node_type_id_int)):
        return False
    return str(graph_node_id) not in set(listen_signal_nodes_with_signal_name_in_edge or set())


def should_use_server_send_signal_meta_binding(
    *,
    node_type_id_int: int | None,
    graph_node_id: str,
    server_send_signal_nodes_with_signal_name_in_edge: Set[str],
) -> bool:
    """
    Send_Signal_To_Server(300002) 的“信号名静态绑定”启用条件：
    - 仅对向服务器节点图发送信号节点生效
    - 且该节点的“信号名”端口不存在 data 入边（否则视为动态信号名）
    """
    if not isinstance(node_type_id_int, int):
        return False
    if not is_server_send_signal_node_type(int(node_type_id_int)):
        return False
    return str(graph_node_id) not in set(server_send_signal_nodes_with_signal_name_in_edge or set())


def map_send_signal_inparam_indices_for_dst_port(
    *,
    dst_data_inputs: Sequence[str],
    dst_port: str,
    use_meta_binding: bool,
    dst_title: str,
) -> Tuple[int, int, int]:
    """
    将 GraphModel 的 dst_port 映射为 `.gia` 的 IN_PARAM pin index（shell/kernel）。

    对齐现有导出器行为：
    - 启用 META binding 时：信号名不占用 IN_PARAM 编号空间，参数从 0 开始连续编号。
    - 禁用时：按 dst_data_inputs 的原始顺序编号（后续由调用方决定是否用 NodeEditorPack 的索引覆盖）。
    """
    port = str(dst_port)
    if not bool(use_meta_binding):
        slot = int(list(dst_data_inputs).index(port))
        return slot, slot, slot

    if port.strip() == SIGNAL_NAME_PORT:
        raise ValueError("Send_Signal 的 '信号名' 端口不应存在 data edge（应为字符串常量或由 META pins 绑定）。")

    filtered = [str(p) for p in dst_data_inputs if str(p).strip() != SIGNAL_NAME_PORT]
    if port not in filtered:
        raise ValueError(
            "Send_Signal dst_port 在过滤掉 '信号名' 后未找到："
            f"dst={dst_title!r}.{port!r} inputs={filtered!r}"
        )
    slot = int(filtered.index(port))
    return slot, slot, slot


@dataclass(frozen=True, slots=True)
class SendSignalBindingPlan:
    """
    Send_Signal(300000) 的导出计划（用于让导出逻辑“按计划生成”，避免散落 if/临时变量）。
    """

    use_meta_binding: bool
    signal_name: str | None

    # base `.gil` 映射：signal_name -> send_node_def_id(0x600000xx)
    send_node_def_id_int: int | None

    # base `.gil` 映射：信号名端口 / 参数端口的 compositePinIndex（PinInstance.field_7）
    signal_name_port_index: int | None
    param_port_indices: List[int] | None

    # 自包含 / 项目存档信号规格提供的参数 VarType 映射（按参数顺序）
    param_var_type_ids: List[int] | None

    @property
    def skip_input_ports(self) -> Set[str]:
        return {SIGNAL_NAME_PORT} if bool(self.use_meta_binding) else set()

    @property
    def has_meta_pin(self) -> bool:
        return bool(self.use_meta_binding) and isinstance(self.signal_name, str) and self.signal_name.strip() != ""

    def data_inputs_without_flow(self, *, input_ports: Sequence[str]) -> List[str]:
        """
        返回“数据输入端口列表”（已按 META binding 规则剔除 '信号名'）。

        注意：调用方仍需先在外部过滤掉 flow ports。
        """
        ports = [str(p) for p in input_ports]
        if not bool(self.use_meta_binding):
            return ports
        return [p for p in ports if str(p).strip() != SIGNAL_NAME_PORT]

    def override_param_var_type(self, *, param_index: int, fallback_var_type_int: int) -> int:
        if not bool(self.use_meta_binding):
            return int(fallback_var_type_int)
        vts = self.param_var_type_ids
        if isinstance(vts, list) and 0 <= int(param_index) < len(vts) and isinstance(vts[int(param_index)], int):
            return int(vts[int(param_index)])
        return int(fallback_var_type_int)

    def param_composite_pin_index(self, *, param_index: int, fallback_index: int) -> int:
        """
        IN_PARAM pin 的 compositePinIndex（PinInstance.field_7）：
        - 有基底映射：按基底端口索引写入
        - 无映射：回退复用导出的 IN_PARAM pin index（保证首次导入仍能补齐动态参数端口）
        """
        indices = self.param_port_indices
        if isinstance(indices, list) and 0 <= int(param_index) < len(indices) and isinstance(indices[int(param_index)], int):
            return int(indices[int(param_index)])
        return int(fallback_index)

    def meta_pin_composite_index(self) -> int:
        """
        META pin 的 compositePinIndex（PinInstance.field_7）。

        规则对齐现有导出器：
        - 优先使用 signal_name_port_index
        - 否则若有 param_port_indices：用 min(param_indices)-1 推断信号名端口
        - 否则兜底为 0
        """
        if isinstance(self.signal_name_port_index, int):
            return int(self.signal_name_port_index)
        if isinstance(self.param_port_indices, list) and self.param_port_indices:
            vals = [int(x) for x in self.param_port_indices if isinstance(x, int)]
            if vals:
                return int(min(vals) - 1)
        return 0


def build_send_signal_binding_plan(
    *,
    graph_node_id: str,
    node_type_id_int: int,
    input_constants: Mapping[str, object],
    send_signal_nodes_with_signal_name_in_edge: Set[str],
    signal_send_node_def_id_by_signal_name: Dict[str, int] | None,
    signal_send_signal_name_port_index_by_signal_name: Dict[str, int] | None,
    signal_send_param_port_indices_by_signal_name: Dict[str, List[int]] | None,
    signal_send_param_var_type_ids_by_signal_name: Dict[str, List[int]] | None,
    node_index_int: int,
) -> SendSignalBindingPlan:
    """
    构造 Send_Signal 的导出计划。

    注意：
    - 若启用 META binding（信号名无 data 入边），则要求 input_constants['信号名'] 为非空字符串；
      否则 fail-fast，避免导出后信号绑定不稳定。
    """
    if not is_send_signal_node_type(int(node_type_id_int)):
        return SendSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            send_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
            param_var_type_ids=None,
        )

    use_meta = should_use_send_signal_meta_binding(
        node_type_id_int=int(node_type_id_int),
        graph_node_id=str(graph_node_id),
        send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge or set()),
    )

    if not bool(use_meta):
        return SendSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            send_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
            param_var_type_ids=None,
        )

    const_signal_name = input_constants.get(SIGNAL_NAME_PORT)
    if not (isinstance(const_signal_name, str) and str(const_signal_name).strip()):
        raise ValueError(
            "Send_Signal 节点的 '信号名' 端口无入边时必须提供字符串常量（用于 META pins 绑定）："
            f"node_index={int(node_index_int)} graph_node_id={str(graph_node_id)!r} input_constants keys={sorted(list(input_constants.keys()))!r}"
        )
    signal_name = str(const_signal_name).strip()

    send_node_def_id_int: int | None = None
    if isinstance(signal_send_node_def_id_by_signal_name, dict):
        v = signal_send_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            send_node_def_id_int = int(v)

    signal_name_port_index: int | None = None
    if isinstance(signal_send_signal_name_port_index_by_signal_name, dict):
        v = signal_send_signal_name_port_index_by_signal_name.get(str(signal_name))
        if isinstance(v, int):
            signal_name_port_index = int(v)
    if not isinstance(signal_name_port_index, int):
        signal_name_port_index = 0

    param_port_indices: List[int] | None = None
    if isinstance(signal_send_param_port_indices_by_signal_name, dict):
        v = signal_send_param_port_indices_by_signal_name.get(str(signal_name))
        if isinstance(v, list):
            param_port_indices = [int(x) for x in v if isinstance(x, int)]

    param_var_type_ids: List[int] | None = None
    if isinstance(signal_send_param_var_type_ids_by_signal_name, dict):
        v = signal_send_param_var_type_ids_by_signal_name.get(str(signal_name))
        if isinstance(v, list):
            param_var_type_ids = [int(x) for x in v if isinstance(x, int)]

    return SendSignalBindingPlan(
        use_meta_binding=True,
        signal_name=str(signal_name),
        send_node_def_id_int=send_node_def_id_int,
        signal_name_port_index=int(signal_name_port_index) if isinstance(signal_name_port_index, int) else 0,
        param_port_indices=param_port_indices,
        param_var_type_ids=param_var_type_ids,
    )


@dataclass(frozen=True, slots=True)
class ListenSignalBindingPlan:
    """
    Listen_Signal(300001) 的导出计划（与 Send_Signal 类似：META pins 绑定 + 对齐 node_def_id/compositePinIndex）。
    """

    use_meta_binding: bool
    signal_name: str | None

    listen_node_def_id_int: int | None
    signal_name_port_index: int | None
    param_port_indices: List[int] | None

    @property
    def skip_input_ports(self) -> Set[str]:
        return {SIGNAL_NAME_PORT} if bool(self.use_meta_binding) else set()

    @property
    def has_meta_pin(self) -> bool:
        return bool(self.use_meta_binding) and isinstance(self.signal_name, str) and self.signal_name.strip() != ""

    def meta_pin_composite_index(self) -> int:
        if isinstance(self.signal_name_port_index, int):
            return int(self.signal_name_port_index)
        if isinstance(self.param_port_indices, list) and self.param_port_indices:
            vals = [int(x) for x in self.param_port_indices if isinstance(x, int)]
            if vals:
                return int(min(vals) - 1)
        return 0


def build_listen_signal_binding_plan(
    *,
    graph_node_id: str,
    node_type_id_int: int,
    input_constants: Mapping[str, object],
    listen_signal_nodes_with_signal_name_in_edge: Set[str],
    listen_node_def_id_by_signal_name: Dict[str, int] | None,
    listen_signal_name_port_index_by_signal_name: Dict[str, int] | None,
    listen_param_port_indices_by_signal_name: Dict[str, List[int]] | None,
    node_index_int: int,
) -> ListenSignalBindingPlan:
    if not is_listen_signal_node_type(int(node_type_id_int)):
        return ListenSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            listen_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
        )

    use_meta = should_use_listen_signal_meta_binding(
        node_type_id_int=int(node_type_id_int),
        graph_node_id=str(graph_node_id),
        listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge or set()),
    )
    if not bool(use_meta):
        return ListenSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            listen_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
        )

    const_signal_name = input_constants.get(SIGNAL_NAME_PORT)
    if not (isinstance(const_signal_name, str) and str(const_signal_name).strip()):
        raise ValueError(
            "监听信号 节点的 '信号名' 端口无入边时必须提供字符串常量（用于 META pins 绑定）："
            f"node_index={int(node_index_int)} graph_node_id={str(graph_node_id)!r} input_constants keys={sorted(list(input_constants.keys()))!r}"
        )
    signal_name = str(const_signal_name).strip()

    listen_node_def_id_int: int | None = None
    if isinstance(listen_node_def_id_by_signal_name, dict):
        v = listen_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            listen_node_def_id_int = int(v)

    signal_name_port_index: int | None = None
    if isinstance(listen_signal_name_port_index_by_signal_name, dict):
        v = listen_signal_name_port_index_by_signal_name.get(str(signal_name))
        if isinstance(v, int):
            signal_name_port_index = int(v)
    if not isinstance(signal_name_port_index, int):
        signal_name_port_index = 0

    param_port_indices: List[int] | None = None
    if isinstance(listen_param_port_indices_by_signal_name, dict):
        v = listen_param_port_indices_by_signal_name.get(str(signal_name))
        if isinstance(v, list):
            param_port_indices = [int(x) for x in v if isinstance(x, int)]

    return ListenSignalBindingPlan(
        use_meta_binding=True,
        signal_name=str(signal_name),
        listen_node_def_id_int=listen_node_def_id_int,
        signal_name_port_index=int(signal_name_port_index),
        param_port_indices=param_port_indices,
    )


@dataclass(frozen=True, slots=True)
class ServerSendSignalBindingPlan:
    """
    Send_Signal_To_Server(300002) 的导出/写回计划（与 Send_Signal 类似：META pins 绑定 + 对齐 node_def_id/compositePinIndex）。
    """

    use_meta_binding: bool
    signal_name: str | None

    server_send_node_def_id_int: int | None
    signal_name_port_index: int | None
    param_port_indices: List[int] | None

    # 自包含 / 项目存档信号规格提供的参数 VarType 映射（按参数顺序）
    param_var_type_ids: List[int] | None

    @property
    def skip_input_ports(self) -> Set[str]:
        return {SIGNAL_NAME_PORT} if bool(self.use_meta_binding) else set()

    @property
    def has_meta_pin(self) -> bool:
        return bool(self.use_meta_binding) and isinstance(self.signal_name, str) and self.signal_name.strip() != ""

    def data_inputs_without_flow(self, *, input_ports: Sequence[str]) -> List[str]:
        ports = [str(p) for p in input_ports]
        if not bool(self.use_meta_binding):
            return ports
        return [p for p in ports if str(p).strip() != SIGNAL_NAME_PORT]

    def override_param_var_type(self, *, param_index: int, fallback_var_type_int: int) -> int:
        if not bool(self.use_meta_binding):
            return int(fallback_var_type_int)
        vts = self.param_var_type_ids
        if isinstance(vts, list) and 0 <= int(param_index) < len(vts) and isinstance(vts[int(param_index)], int):
            return int(vts[int(param_index)])
        return int(fallback_var_type_int)

    def param_composite_pin_index(self, *, param_index: int, fallback_index: int) -> int:
        indices = self.param_port_indices
        if isinstance(indices, list) and 0 <= int(param_index) < len(indices) and isinstance(indices[int(param_index)], int):
            return int(indices[int(param_index)])
        return int(fallback_index)

    def meta_pin_composite_index(self) -> int:
        if isinstance(self.signal_name_port_index, int):
            return int(self.signal_name_port_index)
        if isinstance(self.param_port_indices, list) and self.param_port_indices:
            vals = [int(x) for x in self.param_port_indices if isinstance(x, int)]
            if vals:
                return int(min(vals) - 1)
        return 0


def build_server_send_signal_binding_plan(
    *,
    graph_node_id: str,
    node_type_id_int: int,
    input_constants: Mapping[str, object],
    server_send_signal_nodes_with_signal_name_in_edge: Set[str],
    server_send_node_def_id_by_signal_name: Dict[str, int] | None,
    server_send_signal_name_port_index_by_signal_name: Dict[str, int] | None,
    server_send_param_port_indices_by_signal_name: Dict[str, List[int]] | None,
    signal_param_var_type_ids_by_signal_name: Dict[str, List[int]] | None,
    node_index_int: int,
) -> ServerSendSignalBindingPlan:
    if not is_server_send_signal_node_type(int(node_type_id_int)):
        return ServerSendSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            server_send_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
            param_var_type_ids=None,
        )

    use_meta = should_use_server_send_signal_meta_binding(
        node_type_id_int=int(node_type_id_int),
        graph_node_id=str(graph_node_id),
        server_send_signal_nodes_with_signal_name_in_edge=set(server_send_signal_nodes_with_signal_name_in_edge or set()),
    )
    if not bool(use_meta):
        return ServerSendSignalBindingPlan(
            use_meta_binding=False,
            signal_name=None,
            server_send_node_def_id_int=None,
            signal_name_port_index=None,
            param_port_indices=None,
            param_var_type_ids=None,
        )

    const_signal_name = input_constants.get(SIGNAL_NAME_PORT)
    if not (isinstance(const_signal_name, str) and str(const_signal_name).strip()):
        raise ValueError(
            "向服务器节点图发送信号 节点的 '信号名' 端口无入边时必须提供字符串常量（用于 META pins 绑定）："
            f"node_index={int(node_index_int)} graph_node_id={str(graph_node_id)!r} input_constants keys={sorted(list(input_constants.keys()))!r}"
        )
    signal_name = str(const_signal_name).strip()

    server_node_def_id_int: int | None = None
    if isinstance(server_send_node_def_id_by_signal_name, dict):
        v = server_send_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            server_node_def_id_int = int(v)

    signal_name_port_index: int | None = None
    if isinstance(server_send_signal_name_port_index_by_signal_name, dict):
        v = server_send_signal_name_port_index_by_signal_name.get(str(signal_name))
        if isinstance(v, int):
            signal_name_port_index = int(v)
    if not isinstance(signal_name_port_index, int):
        signal_name_port_index = 0

    param_port_indices: List[int] | None = None
    if isinstance(server_send_param_port_indices_by_signal_name, dict):
        v = server_send_param_port_indices_by_signal_name.get(str(signal_name))
        if isinstance(v, list):
            param_port_indices = [int(x) for x in v if isinstance(x, int)]

    param_var_type_ids: List[int] | None = None
    if isinstance(signal_param_var_type_ids_by_signal_name, dict):
        v = signal_param_var_type_ids_by_signal_name.get(str(signal_name))
        if isinstance(v, list):
            param_var_type_ids = [int(x) for x in v if isinstance(x, int)]

    return ServerSendSignalBindingPlan(
        use_meta_binding=True,
        signal_name=str(signal_name),
        server_send_node_def_id_int=server_node_def_id_int,
        signal_name_port_index=int(signal_name_port_index),
        param_port_indices=param_port_indices,
        param_var_type_ids=param_var_type_ids,
    )

