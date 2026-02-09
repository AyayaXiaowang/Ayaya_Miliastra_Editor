# UI 图形项模块

## 目录用途
存放节点图编辑器的图形项类（QGraphicsItem 子类），负责场景中各元素的渲染与交互。

## 当前状态
- **端口图形项** (`port_item.py`)：
  - `PortGraphicsItem`：端口显示、虚拟引脚角标与 Tooltip、高亮着色
  - 为降低大图下的绘制/几何查询开销，端口会在 `_update_tooltip()` 阶段缓存“是否暴露为虚拟引脚/引脚名”，`paint()` 与 `boundingRect()` 直接复用缓存，避免在高频路径中反复调用 `find_virtual_pin_for_port(...)`。
  - LOD：当 `settings.GRAPH_LOD_ENABLED=True` 且缩放低于端口阈值 `settings.GRAPH_LOD_PORT_MIN_SCALE`（默认 0.30=30%）时，端口与角标将不再绘制；同时 `shape()` 返回空路径，避免出现“端口不可见但仍可被点击/命中”的交互错觉，用于提升超大图缩放/平移流畅度。
  - 虚拟引脚相关的上下文获取/右键菜单/映射清理统一委托给 `app.ui.graph.virtual_pin_ui_service`，端口项自身只关心“是否暴露/显示什么标签”这类简单状态
  - 使用 UI 层的撤销/重做命令（`app.ui.graph.graph_undo`）对删除连线、删除端口等操作进行封装，确保引擎仅处理模型变更
  - `BranchPortValueEdit`：多分支节点的分支匹配值编辑框（内联重命名），重命名操作委托 `RenamePortCommand`，统一更新模型、连线与 UI。

- **节点图形项** (`node_item.py`)：
  - `NodeGraphicsItem`：节点显示、标题栏渲染、端口布局、常量编辑控件管理、变参/多分支"+"按钮
  - 端口行附带 `PortSettingsButton`（小齿轮）：点击可查看端口类型；输入/输出侧分别在标签旁与右侧端口圆点左侧定位，并在 `paint()` 中为按钮预留文本绘制空间，避免遮挡
  - 负责节点的绘制（标题栏渐变、内容区、圆角矩形、选中高亮）
  - 支持画布内搜索（Ctrl+F）的“命中描边”：通过 `set_search_highlighted(True/False)` 仅绘制额外描边，不影响选中态与撤销语义。
  - `_flow_in/_flow_out` 仅代表命名为 **“流程入/流程出”** 的主流程入口/出口端口；其余流程端口（如“跳出循环/循环体/循环完成/是/否/默认”）按普通端口参与布局与查找，避免多流程端口节点（例如“有限循环”）在按“流程入”查找/高亮时指向错误端口。
  - 节点移动时仅通过 `SceneInteractionMixin` 明确提供的钩子（`on_node_item_position_change_started/changed`）通知场景，真正的模型位置更新与撤销记录由 `GraphScene`/命令对象负责；图形项自身不直接读写 `GraphScene` 内部状态或 `NodeModel.pos`。
  - `itemChange()` 中的移动起点记录逻辑需要兼容 Qt 在构造/挂载早期触发回调的情况：通过 `getattr(self, "_moving_started", False)` 读取状态，避免字段尚未初始化时报错。
  - `_layout_ports()` 采用多步管线：
    - `_collect_edges_for_update()`：从 `GraphScene.get_edges_for_node()` 收集需要在布局后刷新端点的连线，避免对全图连线做扫描。
    - `_reset_ports_and_controls()`：清理旧的端口 `QGraphicsItem` 与常量编辑控件，重置内部缓存与流程口引用。
    - `_collect_connected_input_ports()`：优先通过 `GraphScene.get_edges_for_node()`（邻接索引）收集已连线的输入端口名，复杂度为 O(度数)，避免大图下对 `scene.edge_items` 做 O(E) 全量扫描；当场景启用“批量边渲染层”（无 per-edge item）时，会改走 `GraphScene.get_batched_edge_ids_for_node()` + `model.edges` 推导连接关系，同样保持 O(度数)。
    - `_create_font_metrics()` / `_compute_node_width()`：使用统一字体度量，根据左右端口标签宽度计算节点主体宽度（字体选择通过 `app.ui.foundation.fonts` 统一按平台兜底；控件换行后不再参与节点宽度估算）。
    - `_compute_node_rect_and_rows()`：依据 `InputPortLayoutPlan.total_input_rows/input_plus_rows` 与输出端口数量，计算节点矩形高度与内容行数，规则与 `engine.layout.utils.graph_query_utils.estimate_node_height_ui_exact_*` 保持一致。
  - `_layout_input_ports_and_controls()`：按照 `build_input_port_layout_plan()` 生成的 `render_inputs/row_index_by_port/control_row_index_by_port` 渲染输入端口与常量编辑控件（文本/布尔/三维向量），并记录 `_input_row_index_map` 与 `_control_positions` 以便 `paint()` 与验证高亮使用；端口行的紧凑程度统一由 `engine.layout.internal.constants.UI_ROW_HEIGHT` 控制（UI 与布局层共用），通过收敛行高与减少硬编码偏移来降低控件上下留白；端口类型到具体编辑控件的映射集中在 `app.ui.widgets.constant_editors.create_constant_editor_for_port` 中，节点图形项本身不再硬编码 `"实体" / "三维向量" / "布尔值"` 等业务含义。
  - 行内常量控件虚拟化（大图性能）：当 `settings.GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED=True` 时，节点默认只绘制“输入框外观 + 占位文本”，不常驻创建 `QGraphicsProxyWidget`；用户点击占位区域后按需 `materialize_inline_constant_editor(port_name)` 创建真实控件，退出编辑后由控件与节点协作立即释放，显著降低超大图的控件数量与重绘开销。
  - 缩放分级渲染（LOD）：当 `settings.GRAPH_LOD_ENABLED=True` 时，节点会根据缩放比例自动隐藏端口标签/常量占位文本/验证感叹号等细节；标题栏类别渐变始终保留，但标题文字在缩放低于 `settings.GRAPH_LOD_NODE_TITLE_MIN_SCALE` 时默认不再绘制（通常已不可读且绘制成本很高），仅对“选中/搜索命中”的节点保留文字，保证大图缩放/平移流畅且仍可定位关键节点。
  - 端口与端口“⚙查看类型”按钮也会跟随 LOD：当缩放低于“节点细节阈值”时自动隐藏，避免在鸟瞰视角出现大量小图标噪音与额外绘制成本。
  - 节点图形项在需要判断端口类型（例如选择常量编辑控件类型）时，统一走 `app.ui.graph.items.port_type_resolver.resolve_effective_port_type_for_scene`（展示级有效类型解析），与任务清单/端口类型气泡共用同一套规则来源，避免 `input_types/output_types` 被常量字符串污染导致画布展示类型漂移。
    - 画布侧会在 `GraphScene` 上复用 `_SceneExecutor`（NodeDef 获取适配器），并配合 `app.automation.ports.port_type_resolver` 的 `GraphModel+edges_revision` 缓存避免为每个端口重复构建有效类型 resolver，降低大图打开/端口布局阶段的 UI 线程阻塞风险。
    - `_layout_output_ports_and_branch_controls()`：布局输出端口，统一使用 `port_type_system.is_flow_port_with_context()` 判定流程口；在多分支节点上为每个分支输出准备隐藏的 `BranchPortValueEdit`，放置在标签左侧。
    - `_update_edges_after_layout()`：根据新的端口图形项，刷新相关连线的 `src/dst` 引用并调用 `update_path()`，解决“连线连到虚空点”的问题；若场景启用批量边层，则会在布局结束后调用 `GraphScene.update_batched_edges_for_node_ids(...)` 刷新批量边几何。
    - `_layout_add_port_button()`：在非只读场景下，为变参输入节点/多分支节点布置“+”按钮（左下/右下），位置计算与布局估算规则保持一致。
    - basic blocks 背景：端口布局完成后会通知场景标记所属块矩形 dirty，保证块背景能正确框住“可变尺寸节点”（例如拼装列表）且无需在 `drawBackground` 中每帧全量扫描。
- 端口行索引/控件换行逻辑直接复用 `engine.layout.utils.graph_query_utils.build_input_port_layout_plan`，与布局层保持一份规则来源；调用时显式传入 `GraphScene.layout_registry_context`（LayoutRegistryContext），不再依赖任何隐式 workspace_root 或全局缓存。
  - 支持虚拟引脚节点与复合节点的特殊标题栏颜色。
  - 根据节点类别（事件/查询/执行/流程控制等）应用不同渐变色。
  - 拖动节点或通过命令移动节点时，通过 `GraphScene` 维护的“节点 → 连线”邻接索引，仅刷新与该节点相连的连线，避免在大图中遍历所有连线。
  - 暴露 `iter_all_ports()/get_port_by_name()`，供场景高亮与 `NodeDetailOverlay` 复用一套端口查找逻辑。
  - 选中状态的高亮采用基于主色系的描边与外发光，视觉上与全局“主色渐变选中高亮”保持一致；节点内部内容区使用深灰半透明底色，与深色画布和网格形成柔和对比，不透明度由 `engine.configs.settings.settings.GRAPH_NODE_CONTENT_ALPHA` 控制（默认 0.7）。

- **连线图形项** (`edge_item.py`)：
  - `EdgeGraphicsItem`：贝塞尔曲线连线渲染与选中高亮（流程边/数据边不同配色与线宽）。
  - 为减少误触，连线命中/选择区域不完全依赖 Qt 默认实现：通过重写 `shape()`，用可调的 stroker 宽度收敛“可选中区域”，使其更贴近视觉线条（不影响实际绘制线宽）。
  - LOD 降级：低倍率缩放时会隐藏非高亮/非选中的连线，并在 `shape()` 中对非高亮/非选中连线返回空命中区域，显著降低超大图下的绘制与 hit-test 成本；缩放提示通过 `GraphScene.view_scale_hint` 注入（由视图同步）。

- **端口设置按钮** (`port_settings_button.py`)：
  - `PortSettingsButton`：轻量的 QGraphicsItem 自绘小按钮（⚙），点击后在画布内弹出 `PortTypePopupItem` 气泡展示端口类型（非模态）；同一时间只保留一个气泡，再次点击同一端口会收起
  - 类型展示统一委托 `port_type_resolver.resolve_effective_port_type_for_scene`（GraphScene 适配器，展示级推断、不落盘）：其底层逻辑由 `app.automation.ports.port_type_resolver.resolve_effective_port_type_for_model` 提供，保证画布与 Todo/自动化侧共享同一套有效类型推断；流程端口固定显示“流程”
  - LOD：低倍率缩放时会自动隐藏（节点只保留标题栏与标题文本），避免在超大图鸟瞰时密集出现小按钮影响观感与性能。
  - 命中测试：低倍率下 `shape()` 返回空路径，避免按钮不可见时仍可被点击。

- **端口类型气泡** (`port_type_popup_item.py`)：
  - `PortTypePopupItem`：画布内轻量提示气泡（QGraphicsItem 自绘），用于展示端口类型等短文本；不响应鼠标事件以避免遮挡端口/连线交互
  - 端口类型解析统一通过 `app.ui.graph.items.port_type_resolver.resolve_effective_port_type_for_scene` 适配到 `app.automation.ports.port_type_resolver.resolve_effective_port_type_for_model`（引擎侧 EffectivePortTypeResolver 单一真源），避免预览/节点图库/任务清单出现“同一端口不同类型口径”的漂移；画布展示在 fail-closed 场景下会拒绝“泛型家族”占位类型（直接抛错），防止类型缺失被静默掩盖。

- **大图快速预览图元** (`fast_preview_items.py`)：
  - `FastPreviewNodeGraphicsItem`：仅绘制“节点框 + 标题”，不创建端口与行内常量控件（QGraphicsProxyWidget），用于 500+ 节点级别的大图预览提速；保持 `NodeGraphicsItem` 类型以复用点击/跳转/高亮链路。
  - 快速预览节点同样支持搜索命中描边（复用 `NodeGraphicsItem` 的绘制辅助方法），确保大图下搜索体验一致。
  - `FastPreviewEdgeGraphicsItem`：轻量连线（按节点矩形绘制），不依赖端口图元；提供 `update_path()` 以兼容场景的“节点移动刷新连线”钩子；选中态通过颜色/线宽表达，并屏蔽 Qt 默认的选中虚线框以避免大图下出现巨大选中框；支持 LOD：低倍率下隐藏非选中边，并在 `shape()` 中对非选中边返回空路径以降低命中测试成本（命中形状带缓存，避免频繁 stroker 计算）。
  - 节点级展开：在快速预览模式下，选中节点后可点击右上角小按钮展开该节点（临时创建端口/常量控件用于查看），并对快速预览连线做兼容（避免把预览边的端点替换为端口图元）。
  - 展开态交互收敛：端口仍禁用拖拽连线；行内常量控件在展开态保持“只读但可选中复制”，避免“看起来能改但不会落盘”的误导，同时允许用户复制已配置的常量内容用于复用/排查。

- **批量连线渲染层** (`batched_edge_layer.py`)：
  - `BatchedFastPreviewEdgeLayer`：将大量连线收敛为单一 `QGraphicsItem` 绘制，支持模型级命中（空间网格索引）、选中集合与灰显集合；用于 fast_preview_mode 以及只读超大图预览场景降低 `QGraphicsItem` 数量与遍历开销。
  - `paint()` 会基于 `option.exposedRect` 做视口裁剪，仅迭代可见网格单元内的边，避免平移/缩放时每帧全量遍历所有边。

- **性能插桩（画布性能面板）**：
  - 当 `GraphScene` 挂载 `_perf_monitor`（由 `GraphPerfOverlay` 启用）时，`NodeGraphicsItem/EdgeGraphicsItem/PortGraphicsItem/PortSettingsButton` 以及 fast_preview/批量边层会在 `paint/shape/update_path` 等高频路径按帧聚合记录耗时与调用次数，并追踪“上一帧最慢 N 个图元”，用于精确定位拖拽/缩放卡顿来源；默认未挂载时零开销。

## 注意事项
- 图形项通过 `self.scene()` 动态访问 `GraphScene`，避免循环导入
- 使用 `TYPE_CHECKING` 进行类型标注，运行时不导入 `GraphScene`（在 `node_item.py` 中有时需要运行时导入）
- `NodeGraphicsItem` 的端口布局依赖 `GraphScene` 上下文（例如 `layout_registry_context`），因此**不得在构造函数中布局**；布局由 `GraphScene.add_node_item()` 在 `addItem()` 之后触发，确保 `self.scene()` 可用。
- 端口右键菜单通过 `app.ui.foundation.context_menu_builder.ContextMenuBuilder` 统一构建
- 虚拟引脚对话框在函数体内延迟导入（`from app.ui.dialogs.virtual_pin_dialog import ...`）
- `NodeGraphicsItem` 从 `app.ui.widgets.constant_editors` 导入常量编辑控件，从 `app.ui.graph.items.port_item` 导入端口项
- `AddPortButton`（动态端口添加按钮）在运行时从 `app.ui.dynamic_port_widget` 导入
- 节点、端口、连线及验证高亮使用 `ui/graph/graph_palette.py` 中的固定深色画布调色板（背景与网格、类别色、连线颜色等），不随主题切换改变，保证节点图画布在任何模式下外观一致；如需调整请在该集中常量文件内统一修改，并确认不会破坏既定视觉基调。

