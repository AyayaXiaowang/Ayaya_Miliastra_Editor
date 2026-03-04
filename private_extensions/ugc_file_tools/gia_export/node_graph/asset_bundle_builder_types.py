from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True, slots=True)
class GiaAssetBundleGraphExportHints:
    """
    GraphModel(JSON) → `.gia`(AssetBundle/NodeGraph) 导出参数（对齐开源 NodeEditorPack 的 `utils/protobuf/gia.proto`）。

    当前阶段（优先保证“可导出 + 尽量贴近开源工具口径”）：
    - 仅导出 NodeGraph（dependencies 暂空）
    - PinSignature 的 ShellIndex/KernelIndex 优先对齐 NodeEditorPack `utils/node_data/data.json`；缺失时回退到 GraphModel 的端口顺序
    - 数据类型口径复用 server VarType（与 GIL 写回一致）；client graph 会做一层 ServerTypeId→ClientTypeId 的映射
    """

    graph_id_int: int
    graph_name: str
    graph_scope: str  # "server" | "client"
    resource_class: str  # 例如 "ENTITY_NODE_GRAPH" / "BOOLEAN_FILTER_GRAPH"
    graph_generater_root: Path
    # Graph_Generater NodeDef canonical key（node_library key）→ node_id(int)
    # 说明：导出侧禁止用 title 定位节点类型；GraphModel(JSON) 必须携带 node_def_ref 作为唯一真源。
    node_type_id_by_node_def_key: Dict[str, int]

    export_uid: int = 0
    # Root.gameVersion / AssetBundle.engine_version（真源口径：6.3.0 起引入/调整部分节点与信号相关结构）
    game_version: str = "6.3.0"

    # 可选：信号定义映射（来自“基底存档 .gil”）。
    # key: signal_name, value: send_node_def_id_int（即 0x600000xx，真源生成的 send node_def）
    #
    # 用途：
    # - 导出 `.gia` 时为 Send_Signal 的 META pin（Kind=5）写入 PinSignature.source_ref，
    #   避免在不同存档环境中出现“信号名串号”（例如显示成别的信号）。
    signal_send_node_def_id_by_signal_name: Dict[str, int] | None = None

    # 可选：信号节点端口索引映射（来自“基底存档 .gil”）。
    #
    # 用途：
    # - 为 Send_Signal 写入 PinInstance.compositePinIndex（field 7），让编辑器在首次打开时即可补齐动态端口；
    # - 与 source_ref 配合，避免“需要手动刷新端口”的体验问题。
    signal_send_signal_name_port_index_by_signal_name: Dict[str, int] | None = None
    signal_send_param_port_indices_by_signal_name: Dict[str, List[int]] | None = None
    # 可选：信号参数 VarType 映射（用于无 base `.gil` 时，仍能把常量按正确 VarType 写入）。
    # key: signal_name, value: [var_type_int...]（按参数顺序）
    signal_send_param_var_type_ids_by_signal_name: Dict[str, List[int]] | None = None

    # 可选：监听信号（Monitor_Signal）映射（自包含 bundle 或基底 `.gil` 提供）。
    # 用途：
    # - 导出 `.gia` 时为 Listen_Signal(300001) 写入 META pins（Kind=5/6）时，使用 compositePinIndex 对齐真源端口索引；
    # - 当命中 node_def_id(0x600000xx) 时，将 runtime_id 替换为对应 listen_node_def_id，并将 kind 设为 22001。
    listen_node_def_id_by_signal_name: Dict[str, int] | None = None
    listen_signal_name_port_index_by_signal_name: Dict[str, int] | None = None
    listen_param_port_indices_by_signal_name: Dict[str, List[int]] | None = None

    # 可选：将“信号 node_def GraphUnits”等 dependencies 一并打包进输出 `.gia`（AssetBundle.field_2）。
    # 用于导入到空存档时仍能自动展开信号端口（自包含）。
    extra_dependency_graph_units: List[Dict[str, Any]] | None = None
    # 可选：写入 primary_resource(GraphUnit) 的 relatedIds（GraphUnit.field_2），与 extra_dependency_graph_units 配合。
    graph_related_ids: List[Dict[str, Any]] | None = None

    # 可选：导出节点图 `.gia` 时，自动将“复合节点定义（NodeInterface + CompositeGraph）”打包进 dependencies。
    # 目标：使导出的 `.gia` 在导入到空存档时也能正常展开/解析复合节点（自包含）。
    include_composite_nodes: bool = True

    # 节点坐标缩放（工程化展示用，不影响逻辑语义）：
    # - GraphModel(JSON) 的 node.payload.pos 为 Graph_Generater 画布坐标系；
    # - 导出 `.gia` 时会对 x/y 同步乘以该系数，再进行 X 轴居中偏移；
    # - 默认 2.0 为历史经验值：不缩放时在真源编辑器中更容易显得“过于紧凑”（节点/连线更拥挤）。
    node_pos_scale: float = 2.0

