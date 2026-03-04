# ugc_file_tools/gia_export/node_graph 目录说明

## 目录用途
- 存放“节点图 `.gia`（AssetBundle/NodeGraph）导出”的核心实现（对齐 NodeEditorPack 的 `gia.proto`）。
- 与 `node_graph_writeback/` 解耦：本目录只负责 `.gia` 导出；`.gil` 节点图写回仍由 `ugc_file_tools/node_graph_writeback/` 负责。

## 当前状态
- 对外稳定入口：`asset_bundle_builder.py`（门面/re-export）。
- GraphModel(JSON) → `.gia` 主流程（orchestration + builders）：
  - `asset_bundle_builder_graph_builder.py`：组装上下文并调度各 builder（落盘/报告）。
  - `asset_bundle_builder_graph_context.py`：导出上下文构建（NodeDef 定位、edges 分桶、类型快照补齐等）。
  - `asset_bundle_builder_node_instances.py`：节点实例与 pins/VarBase/Concrete 构造。
  - `asset_bundle_builder_connections.py`：flow/data 连接聚合与索引视图。
  - `asset_bundle_builder_positions.py`：节点坐标缩放与 X 轴居中偏移（仅影响展示分布）。
- 画像/补齐：
  - `asset_bundle_builder_node_editor_pack.py`：NodeEditorPack `data.json` 画像读取与 pin 工具。
  - `asset_bundle_builder_nep_pin_filler.py`：按画像补齐缺失 pins（稳定端口结构）。
- 复合节点：`asset_bundle_builder_composite.py` 支持复合节点自包含导出（NodeInterface + CompositeGraph）。
- 交付边界（含复合子图）：在把 GraphModel→NodeGraph 写入 bundle 之前，会对顶层图与复合子图分别做端口类型标准化与 `gap_report`，只要存在任意非流程端口仍处于“泛型家族/容器占位(字典/列表)”就 fail-fast 并输出报告，避免在 pins/VarBase 构造阶段以更难定位的异常形式爆栈。
- 端口类型/VarType/Concrete 的规则统一复用 `ugc_file_tools/contracts/` 与 `ugc_file_tools/node_graph_semantics/`（导出/写回单一真源）。
  - 字典端口（VarType=27）必须具备 K/V 类型信息；当 GraphModel 类型文本缺失时，允许从 NodeEditorPack `TypeExpr(D<...>)` 提取 K/V 作为真源证据补齐（缺失则 fail-fast）。
  - 复合节点 NodeInterface 的 data pins type_info 必须包含 widget_type(field_1)；Vec3(三维向量, VarType=12) 的 widget_type 为 7，缺失会导致编辑器/游戏侧不生成可编辑输入控件。

## 注意事项
- NodeDef 定位唯一真源为 GraphModel(JSON) 的 `node_def_ref`（builtin→canonical key；composite→composite_id）；导出侧禁止通过 `title` 反查节点类型/节点定义。
- GraphModel 的事件入口节点（`node_def_ref.kind="event"`）需要映射回真实 NodeDef（按约定口径统一处理），避免把“事件实例 key/信号名”误当作 NodeDef key。
- 当 GraphModel 类型快照缺失或保持泛型时，优先使用 NodeEditorPack 画像作为兜底证据，避免导出后导入出现端口错位/类型退化。
- 字典端口（VarType=27）的 K/V 类型证据链优先级：GraphModel 具体类型文本（别名字典）→ 常量默认值推断 → NodeEditorPack `TypeExpr(D<...>)` → 端口名携带语义（如 `字典_字符串到整数`）→ **节点级类型 Plan（从同节点键/值端口/连线推断得到的 dict(K,V)）**；缺失则 fail-fast 抛错。
 - `node_def_ref.kind="event"` 的事件节点：当 GraphModel 以 `category=事件节点,title=<信号名>` 表达“监听信号事件”时，builtin key 不存在；导出侧需回退到 `事件节点/监听信号` NodeDef（让后续 signal binding/端口补齐继续生效）。
  - 对 event 节点：信号名通常不经由 `信号名` 端口常量/入边提供；导出侧会从 `node_def_ref.key`（或 title）注入到 `input_constants['信号名']`，供 META pins 绑定计划使用。
- fail-fast：不使用 `try/except`；跨模块复用必须走公开 API（无下划线）。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

