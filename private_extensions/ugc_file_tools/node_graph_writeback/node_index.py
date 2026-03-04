from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.node_graph_semantics.layout import SortedNode as _SortedNode

from .composite_id_map import map_composite_id_to_node_type_id_int


_STRUCT_NODE_TITLES: set[str] = {"拼装结构体", "拆分结构体", "修改结构体"}
_GRAPH_SCOPE_MASK: int = 0xFF800000
_SERVER_SCOPE_PREFIX: int = 0x40000000
_CLIENT_SCOPE_PREFIX: int = 0x40800000
_SIGNAL_NAME_PORT: str = "信号名"
_SIGNAL_ID_META_KEY: str = "__signal_id"
_SEND_SIGNAL_TITLE: str = "发送信号"
_LISTEN_SIGNAL_TITLE: str = "监听信号"
_SEND_TO_SERVER_SIGNAL_TITLE: str = "向服务器节点图发送信号"


def _extract_struct_id_from_graph_node_payload(node_payload: Dict[str, Any]) -> Optional[int]:
    input_constants = node_payload.get("input_constants")
    if isinstance(input_constants, dict):
        for key in ("__struct_id", "struct_id", "struct_def_id"):
            raw = input_constants.get(key)
            if isinstance(raw, int):
                return int(raw)
            if isinstance(raw, str):
                text = raw.strip()
                if text.isdigit():
                    return int(text)
    return None


def _resolve_signal_specific_type_id_from_graph_node_payload(
    *,
    node_title: str,
    node_payload: Dict[str, Any],
    signal_send_node_def_id_by_signal_name: Optional[Dict[str, int]],
    signal_listen_node_def_id_by_signal_name: Optional[Dict[str, int]],
    signal_server_node_def_id_by_signal_name: Optional[Dict[str, int]],
) -> Optional[int]:
    """
    当信号节点使用静态 META 绑定（存在 __signal_id + 常量“信号名”）时，
    为写回侧提供“signal-specific runtime type_id”：

    口径说明（对照可玩真源 `.gil` / after_game 导出）：
    - signal entry 中保存的 send/listen/server id **就是** NodeGraph 节点实例的 `node_type_id_int`；
      常见位于 0x4000xxxx（server）/0x4080xxxx（client）号段。
    - 写回侧应直接使用该 id；不应再额外 OR “提升位”生成 0x6000xxxx/0x6080xxxx，
      否则会产出“能渲染但运行时分发口径不一致”的坏图。
    """
    # 事件节点兼容：GraphModel 中“监听信号事件节点”常表现为：
    # - node_def_ref.kind = event
    # - outputs 含 “信号来源实体”
    # - title 可能是信号名（或仍为 “监听信号”），真实信号名优先来自 node_def_ref.key
    #
    # 对齐真源 `.gil`：当 base `.gil` 已提供 signal_name -> listen_id 映射时，该节点应写为 signal-specific runtime_id。
    node_def_ref = node_payload.get("node_def_ref")
    if isinstance(node_def_ref, dict):
        kind = str(node_def_ref.get("kind") or "").strip().lower()
        if kind == "event":
            outputs = node_payload.get("outputs")
            if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                key_name = str(node_def_ref.get("key") or "").strip()
                title_name = str(node_title).strip()
                signal_name = key_name or (title_name if title_name != _LISTEN_SIGNAL_TITLE else "")
                if signal_name != "" and isinstance(signal_listen_node_def_id_by_signal_name, dict):
                    v = signal_listen_node_def_id_by_signal_name.get(str(signal_name))
                    if isinstance(v, int) and int(v) > 0:
                        return int(v)

    if str(node_title) not in {_SEND_SIGNAL_TITLE, _LISTEN_SIGNAL_TITLE, _SEND_TO_SERVER_SIGNAL_TITLE}:
        return None

    input_constants = node_payload.get("input_constants")
    if not isinstance(input_constants, dict):
        return None

    signal_name_raw = input_constants.get(_SIGNAL_NAME_PORT)
    signal_name = str(signal_name_raw).strip() if isinstance(signal_name_raw, str) else ""
    if signal_name == "":
        return None

    if str(node_title) == _SEND_SIGNAL_TITLE and isinstance(signal_send_node_def_id_by_signal_name, dict):
        v = signal_send_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            return int(v)
    if str(node_title) == _LISTEN_SIGNAL_TITLE and isinstance(signal_listen_node_def_id_by_signal_name, dict):
        v = signal_listen_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            return int(v)
    if str(node_title) == _SEND_TO_SERVER_SIGNAL_TITLE and isinstance(signal_server_node_def_id_by_signal_name, dict):
        v = signal_server_node_def_id_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) > 0:
            return int(v)
    return None


def _build_graph_node_id_maps(
    *,
    sorted_nodes: List[_SortedNode],
    name_to_type_id: Dict[str, int],
    node_def_key_to_type_id: Optional[Dict[str, int]] = None,
    struct_node_type_id_by_title_and_struct_id: Optional[Dict[str, Dict[int, int]]] = None,
    signal_send_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    prefer_signal_specific_type_id: bool = False,
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, str], Dict[str, Dict[str, Any]]]:
    node_id_int_by_graph_node_id: Dict[str, int] = {}
    node_type_id_by_graph_node_id: Dict[str, int] = {}
    node_title_by_graph_node_id: Dict[str, str] = {}
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]] = {}

    for index, (_y, _x, title, node_id, node_payload) in enumerate(sorted_nodes, start=1):
        if title == "":
            raise ValueError(f"graph node missing title: id={node_id!r}")
        type_id_int: Optional[int] = None
        type_id_locked_by_signal_binding = False

        # 优先：按 GraphModel.node_def_ref.key 取 type_id（与 GIA 导出链路一致；避免仅靠 title 映射导致 type_id 漂移）。
        if node_def_key_to_type_id is not None and isinstance(node_payload, dict):
            node_def_ref = node_payload.get("node_def_ref")
            if isinstance(node_def_ref, dict):
                kind = str(node_def_ref.get("kind") or "").strip().lower()
                key = str(node_def_ref.get("key") or "").strip()
                if kind == "builtin" and key != "":
                    mapped = node_def_key_to_type_id.get(key)
                    if isinstance(mapped, int) and int(mapped) > 0:
                        type_id_int = int(mapped)

                # 工程化：signal listen 事件节点（GraphModel: kind=event, title/key=信号名）不在 title→type_id 映射表中。
                # 兜底：先回退到通用 runtime（server: 300001=监听信号）；若后续能解析到 base `.gil` 的
                # “signal_name -> listen_id” 映射，会再提升为 signal-specific runtime_id（对齐真源）。
                # 因此：当事件节点看起来是“信号事件”（输出含 信号来源实体）时，先回退到 监听信号 type_id。
                if type_id_int is None and kind == "event":
                    outputs = node_payload.get("outputs")
                    if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                        mapped_listen = name_to_type_id.get(_LISTEN_SIGNAL_TITLE)
                        if isinstance(mapped_listen, int) and int(mapped_listen) > 0:
                            type_id_int = int(mapped_listen)

        # fallback：按 title 映射（历史兼容）
        if type_id_int is None:
            mapped2 = name_to_type_id.get(title)
            if isinstance(mapped2, int):
                type_id_int = int(mapped2)
        if not isinstance(type_id_int, int):
            composite_id = ""
            node_def_ref = None
            if isinstance(node_payload, dict):
                composite_id = str(node_payload.get("composite_id") or "").strip()
                node_def_ref = node_payload.get("node_def_ref")
            kind = str(node_def_ref.get("kind") or "").strip().lower() if isinstance(node_def_ref, dict) else ""
            if composite_id == "" and kind == "composite" and isinstance(node_def_ref, dict):
                composite_id = str(node_def_ref.get("key") or "").strip()
            if composite_id != "" or kind == "composite":
                # 复合节点：type_id 不来自 node_type_semantic_map，而是由 composite_id 稳定映射到 0x4000xxxx。
                resolved_id = map_composite_id_to_node_type_id_int(composite_id or str(title))
                type_id_int = int(resolved_id)
            else:
                raise KeyError(f"node_type_semantic_map 未覆盖该节点（无法写回 GIL）：{title!r}")

        if isinstance(node_payload, dict):
            # NOTE:
            # - 写回中一旦 base `.gil` 能提供“信号名 -> node_def_id(0x4000xxxx/0x4080xxxx)”映射，
            #   则信号节点实例的 type_id 应直接写为对应的 send/listen/server id（对齐 after_game 真源）。
            signal_type_id = _resolve_signal_specific_type_id_from_graph_node_payload(
                node_title=str(title),
                node_payload=node_payload,
                signal_send_node_def_id_by_signal_name=signal_send_node_def_id_by_signal_name,
                signal_listen_node_def_id_by_signal_name=signal_listen_node_def_id_by_signal_name,
                signal_server_node_def_id_by_signal_name=signal_server_node_def_id_by_signal_name,
            )
            if isinstance(signal_type_id, int) and int(signal_type_id) > 0:
                # signal-specific type_id（常见 0x4000xxxx/0x4080xxxx）不要求模板库覆盖：
                # 当模板库缺失样本时会走“最小合成节点”分支，仍可写出可用节点（NodeProperty + pins/records）。
                type_id_int = int(signal_type_id)
                type_id_locked_by_signal_binding = True

        # 防错：当 node_def_ref 命中后得到“图ID风格”的 type_id（0x4000_0000 / 0x4080_0000 前缀）时，
        # 优先回退到稳定的 title→type_id 映射，避免把 graph/signal 实例 id 误写为节点类型 id。
        # 该问题会导致写回后端口槽位解释错误（表现为“信号/端口连接错位”）。
        mapped_by_title = name_to_type_id.get(title)
        type_id_scope_prefix = int(type_id_int) & int(_GRAPH_SCOPE_MASK)
        if (
            (not bool(type_id_locked_by_signal_binding))
            and
            isinstance(mapped_by_title, int)
            and int(mapped_by_title) > 0
            and type_id_scope_prefix in {_SERVER_SCOPE_PREFIX, _CLIENT_SCOPE_PREFIX}
            and int(mapped_by_title) != int(type_id_int)
        ):
            type_id_int = int(mapped_by_title)

        # 结构体节点：部分真源样本中会出现“每个 struct_id 对应一套独立 node_type_id”的 node_def；
        # 但在 test2 的真源图中，节点本体仍可能使用通用 type_id（例如 修改结构体=300004）。
        # 因此这里采用“可选覆盖”：若 base gil 能解析到 (title, struct_id)->type_id，则覆盖；否则保留通用映射。
        if (
            struct_node_type_id_by_title_and_struct_id is not None
            and str(title) in _STRUCT_NODE_TITLES
            and isinstance(node_payload, dict)
        ):
            struct_id_int = _extract_struct_id_from_graph_node_payload(node_payload)
            if isinstance(struct_id_int, int):
                by_struct = struct_node_type_id_by_title_and_struct_id.get(str(title)) or {}
                resolved = by_struct.get(int(struct_id_int))
                if isinstance(resolved, int):
                    type_id_int = int(resolved)
        node_id_int_by_graph_node_id[node_id] = int(index)
        node_type_id_by_graph_node_id[node_id] = int(type_id_int)
        node_title_by_graph_node_id[node_id] = title
        if not isinstance(node_payload, dict):
            raise TypeError("sorted_nodes 中的 node_payload 必须是 dict")
        graph_node_by_graph_node_id[node_id] = node_payload

    return node_id_int_by_graph_node_id, node_type_id_by_graph_node_id, node_title_by_graph_node_id, graph_node_by_graph_node_id


