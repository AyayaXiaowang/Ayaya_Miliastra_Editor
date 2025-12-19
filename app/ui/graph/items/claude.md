# UI 图形项模块

## 目录用途
存放节点图编辑器的图形项类（QGraphicsItem 子类），负责场景中各元素的渲染与交互。

## 当前状态
- **端口图形项** (`port_item.py`)：
  - `PortGraphicsItem`：端口显示、虚拟引脚角标与 Tooltip、高亮着色
  - 虚拟引脚相关的上下文获取/右键菜单/映射清理统一委托给 `app.ui.graph.virtual_pin_ui_service`，端口项自身只关心“是否暴露/显示什么标签”这类简单状态
  - 使用 UI 层的撤销/重做命令（`app.ui.graph.graph_undo`）对删除连线、删除端口等操作进行封装，确保引擎仅处理模型变更
  - `BranchPortValueEdit`：多分支节点的分支匹配值编辑框（内联重命名），重命名操作委托 `RenamePortCommand`，统一更新模型、连线与 UI。

- **节点图形项** (`node_item.py`)：
  - `NodeGraphicsItem`：节点显示、标题栏渲染、端口布局、常量编辑控件管理、变参/多分支"+"按钮
  - 负责节点的绘制（标题栏渐变、内容区、圆角矩形、选中高亮）
  - 节点移动时仅通过 `SceneInteractionMixin` 明确提供的钩子（`on_node_item_position_change_started/changed`）通知场景，真正的模型位置更新与撤销记录由 `GraphScene`/命令对象负责；图形项自身不直接读写 `GraphScene` 内部状态或 `NodeModel.pos`。
  - `itemChange()` 中的移动起点记录逻辑需要兼容 Qt 在构造/挂载早期触发回调的情况：通过 `getattr(self, "_moving_started", False)` 读取状态，避免字段尚未初始化时报错。
  - `_layout_ports()` 采用多步管线：
    - `_collect_edges_for_update()`：从 `GraphScene.get_edges_for_node()` 收集需要在布局后刷新端点的连线，避免对全图连线做扫描。
    - `_reset_ports_and_controls()`：清理旧的端口 `QGraphicsItem` 与常量编辑控件，重置内部缓存与流程口引用。
    - `_collect_connected_input_ports()`：扫描 `scene.edge_items`，收集所有已连线的输入端口名，为“是否展示行内常量编辑控件”提供依据。
    - `_create_font_metrics()` / `_compute_node_width()`：使用统一字体度量，根据左右端口标签宽度计算节点主体宽度（字体选择通过 `app.ui.foundation.fonts` 统一按平台兜底；控件换行后不再参与节点宽度估算）。
    - `_compute_node_rect_and_rows()`：依据 `InputPortLayoutPlan.total_input_rows/input_plus_rows` 与输出端口数量，计算节点矩形高度与内容行数，规则与 `engine.layout.utils.graph_query_utils.estimate_node_height_ui_exact_*` 保持一致。
    - `_layout_input_ports_and_controls()`：按照 `build_input_port_layout_plan()` 生成的 `render_inputs/row_index_by_port/control_row_index_by_port` 渲染输入端口与常量编辑控件（文本/布尔/三维向量），并记录 `_input_row_index_map` 与 `_control_positions` 以便 `paint()` 与验证高亮使用；端口类型到具体编辑控件的映射集中在 `app.ui.widgets.constant_editors.create_constant_editor_for_port` 中，节点图形项本身不再硬编码 `"实体" / "三维向量" / "布尔值"` 等业务含义。
    - `_layout_output_ports_and_branch_controls()`：布局输出端口，统一使用 `port_type_system.is_flow_port_with_context()` 判定流程口；在多分支节点上为每个分支输出准备隐藏的 `BranchPortValueEdit`，放置在标签左侧。
    - `_update_edges_after_layout()`：根据新的端口图形项，刷新相关连线的 `src/dst` 引用并调用 `update_path()`，解决“连线连到虚空点”的问题。
    - `_layout_add_port_button()`：在非只读场景下，为变参输入节点/多分支节点布置“+”按钮（左下/右下），位置计算与布局估算规则保持一致。
- 端口行索引/控件换行逻辑直接复用 `engine.layout.utils.graph_query_utils.build_input_port_layout_plan`，与布局层保持一份规则来源；调用时显式传入 `GraphScene.layout_registry_context`（LayoutRegistryContext），不再依赖任何隐式 workspace_root 或全局缓存。
  - 支持虚拟引脚节点与复合节点的特殊标题栏颜色。
  - 根据节点类别（事件/查询/执行/流程控制等）应用不同渐变色。
  - 拖动节点或通过命令移动节点时，通过 `GraphScene` 维护的“节点 → 连线”邻接索引，仅刷新与该节点相连的连线，避免在大图中遍历所有连线。
  - 暴露 `iter_all_ports()/get_port_by_name()`，供场景高亮与 `NodeDetailOverlay` 复用一套端口查找逻辑。
  - 选中状态的高亮采用基于主色系的描边与外发光，视觉上与全局“主色渐变选中高亮”保持一致；节点内部内容区使用固定的深灰半透明底色，与深色画布和网格形成柔和对比。

## 注意事项
- 图形项通过 `self.scene()` 动态访问 `GraphScene`，避免循环导入
- 使用 `TYPE_CHECKING` 进行类型标注，运行时不导入 `GraphScene`（在 `node_item.py` 中有时需要运行时导入）
- `NodeGraphicsItem` 的端口布局依赖 `GraphScene` 上下文（例如 `layout_registry_context`），因此**不得在构造函数中布局**；布局由 `GraphScene.add_node_item()` 在 `addItem()` 之后触发，确保 `self.scene()` 可用。
- 端口右键菜单通过 `app.ui.foundation.context_menu_builder.ContextMenuBuilder` 统一构建
- 虚拟引脚对话框在函数体内延迟导入（`from app.ui.dialogs.virtual_pin_dialog import ...`）
- `NodeGraphicsItem` 从 `app.ui.widgets.constant_editors` 导入常量编辑控件，从 `app.ui.graph.items.port_item` 导入端口项
- `AddPortButton`（动态端口添加按钮）在运行时从 `app.ui.dynamic_port_widget` 导入
- 节点、端口、连线及验证高亮使用 `ui/graph/graph_palette.py` 中的固定深色画布调色板（背景与网格、类别色、连线颜色等），不随主题切换改变，保证节点图画布在任何模式下外观一致；如需调整请在该集中常量文件内统一修改，并确认不会破坏既定视觉基调。

