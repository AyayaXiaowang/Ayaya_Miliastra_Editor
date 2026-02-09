# ui/scene 目录

## 目录用途
存放场景交互与对象管理相关的 Mixin 组件，用于从 `GraphScene` 中分离交互与管理职责。

## 当前状态

### 子模块列表

1. **interaction_mixin.py** - 场景交互 Mixin
   - `SceneInteractionMixin`: 提供鼠标事件处理、端口高亮、自动连接等交互能力
   - 鼠标事件入口：`mousePressEvent` / `mouseReleaseEvent` / `mouseMoveEvent` 作为统一入口, 内部再委托给私有方法处理具体分支。
   - 连线流程：`_handle_port_connection_mouse_press` 负责端口拖拽起手与临时预览, `_handle_connection_on_mouse_release` 根据命中图元选择 `_try_commit_edge_between_ports`（直接建线）或 `_prepare_pending_connection_and_open_menu`（记录 pending_* 并弹出“添加节点”菜单）, `_highlight_compatible_ports` / `_clear_port_highlights` 统一管理端口高亮。
   - 端口可连性：除 `can_connect_ports` 的类型匹配外，还会读取 `NodeDef.input/output_generic_constraints` 对“泛型家族端口（以‘泛型’开头）”的允许集合做约束，并对【数据类型转换】节点额外执行“输入类型 ↔ 输出类型”的联动检查（以 `engine.type_registry.TYPE_CONVERSIONS` 为准）。
   - 自动连接：`auto_connect_new_node` 依赖 `pending_src_*` 与 `_find_compatible_port` 等 helper 精确挑选连线目标, 通过 `AddEdgeCommand` 创建连线, 找不到兼容端口时会立即清理待连接状态。
   - 节点移动：`on_node_item_position_change_started` / `on_node_item_position_changed` 仅记录移动起点并刷新关联连线路径；在超大图或 `fast_preview_mode` 下连线路径刷新会做节流/批处理以降低拖拽卡顿，鼠标释放时 `_finalize_node_move_commands` 会补齐一次刷新并根据 `node_move_tracking` 生成 `MoveNodeCommand` 入撤销栈，同时清理 `_moving_started` 标记；当场景启用“批量渲染边”时，节点拖拽的连线刷新会额外调用 `update_batched_edges_for_node_ids(...)` 做局部几何重算，且节流判断的 edge_count 以 `model.edges` 为准（不依赖 `edge_items`）。
   - Y 调试：鼠标事件中优先将 Y 调试图标命中委托给 `_handle_ydebug_mouse_press`, Tooltip 与链路高亮仍由 `ydebug_interaction_mixin.py` / `tooltip_overlay.py` / `highlight_manager.py` 协同完成。

2. **model_ops_mixin.py** - 场景对象管理 Mixin
   - `SceneModelOpsMixin`: 提供 add_edge_item、copy/paste、delete、高亮、更新验证等对象管理能力
   - 方法: `add_edge_item`, `delete_selected_items`, `_update_scene_rect`, `_remove_node_graphics`, `get_node_item`, `highlight_node`, `highlight_edge`, `highlight_port`, `clear_highlights`, `copy_selected_nodes`, `paste_nodes`, `update_validation`
   - `_update_scene_rect()` 会按**当前视口大小**补齐必要边距，保证边缘节点可居中显示；常规图以 `itemsBoundingRect()` 为基础计算内容边界，超大图（节点/连线超过阈值）则降级为基于 `GraphModel.nodes[*].pos` 的估算边界以避免枚举全量 QGraphicsItem（端口/常量控件/连线等）造成卡顿；阈值与估算参数由 settings 的 `GRAPH_SCENE_RECT_SIMPLIFY_{NODE|EDGE}_THRESHOLD` 与 `GRAPH_SCENE_RECT_APPROX_NODE_{WIDTH|HEIGHT}` / `GRAPH_SCENE_RECT_MARGIN` 控制（均有默认值，可按需在设置页暴露）。
   - `copy_selected_nodes()` 通过 `node_index_map` 缓存节点序号，批量复制连线时避免对 `selected_node_ids.index()` 的重复遍历，复制大图时由 O(N²) 降为 O(N)。
   - `add_edge_item()` 在批量装配阶段（GraphScene.is_bulk_adding_items=True）会延迟目标节点端口重排，批量结束后由 GraphScene 统一 flush，避免逐边重排带来的卡顿。
   - 高亮兼容 fast_preview 批量边：当场景无 per-edge item 时，`highlight_edge/clear_highlights` 会委托 `GraphScene.set_batched_selected_edge_ids(...)` / `clear_batched_selected_edges()` 维护批量边层的“选中边集合”，保持只读预览的边高亮语义一致。
   - 节点删除/撤销移除图形项（`_remove_node_graphics`）在 fast_preview 批量边模式下会同步清理批量边层中的相关边，避免残留索引导致的残影与命中异常。

3. **ydebug_interaction_mixin.py** - 布局Y调试交互 Mixin
   - `YDebugInteractionMixin` 负责装配与转发 Y 调试相关钩子：Tooltip UI 由 `tooltip_overlay.py` 负责、链路高亮由 `highlight_manager.py` 统一调度、交互状态与分页由 `interaction_state.py` 管理，后续快捷键与图标点击命中也在此集中注册。
   - Tooltip 在顶部展示“节点名称 + 节点ID + GIA序号（导出到 `.gia` 的从 1 开始稳定序号）”，正文部分按“所属块/所属事件流/关联链路/位置依据”等分段渲染；支持高对比度标题栏与拖动偏移，初始定位智能避让节点，定位逻辑统一将 `mapFromScene` 结果归一为 `QPoint`。
   - 当检测到 `final_y` 显著小于“列底候选”时（通常意味着块内数据Y松弛已上移节点），Tooltip 会将该列底标注为“列底，初排”并追加提示文案，避免误判“布局违反安全列底规则”。
   - Tooltip HTML 文案支持分页与链路点击，通过 `highlight_manager` 在单链/全链高亮之间切换。
   - 分页状态与 Tooltip 几何状态均由 `YDebugInteractionState` 记录，视图缩放或宿主尺寸变更时可调用 `_reposition_ydebug_tooltip()` 快速恢复角度与偏移。
   - `SceneOverlayMixin` 会在启用“布局Y坐标调试”但当前模型尚未生成 `_layout_y_debug_info` 时，自动克隆模型并运行一次 `LayoutService.compute_layout`，仅回填调试字典而不更改节点坐标，确保即使自动排版被校验阻塞也能看到感叹号入口。

4. **view_context_menu_mixin.py** - 视图右键菜单桥接 Mixin
   - `SceneViewContextMenuMixin`: 提供 `handle_view_context_menu`，由 `GraphView.contextMenuEvent` 显式委托调用（不再通过 `getattr/hasattr` 反射探测接口）
   - 职责：识别命中图元类型（端口/节点/连线/空白）并决定是否消费事件；节点级扩展点由 `app.ui.graph.signal_node_service` / `app.ui.graph.struct_node_service` 注入菜单项
   - 空白处“添加节点”菜单统一调用 `GraphView.show_add_node_menu(...)`（公开方法），不依赖私有 `_show_add_node_menu` 钩子探测
   - 设计目标：GraphScene 主文件不再直接承载“右键菜单 + 业务入口”逻辑，新增节点特化菜单只改服务层即可

## GraphScene 主文件
`GraphScene` 主文件（约250行）保留核心职责：
- 初始化与配置
- 节点库接口（`get_node_def`）
- 节点项添加（`add_node_item`）
- 布局辅助（`_promote_flow_outputs_for_layout`）
- 虚拟引脚清理（`cleanup_virtual_pins_for_deleted_node`）
- 端口刷新（`_refresh_all_ports`）
 - 右键菜单由 `SceneViewContextMenuMixin` 提供（不在主文件内实现）

## 架构优势
- **职责分离**: 交互/管理/调试三大职责独立成模块，便于维护与测试
- **代码精简**: 主文件保持约 250 行的薄层入口，其余复杂逻辑下沉到各个 Mixin 中
- **低耦合**: Mixin 不导入 `GraphScene`，仅通过属性接口交互
- **易扩展**: 新增功能只需添加新的 Mixin 或扩展现有 Mixin

## 注意事项
- Mixin 不导入 `GraphScene`，仅假设宿主提供必要属性（model, node_items, edge_items 等）
- 交互与管理逻辑完全解耦，便于测试与维护
- 导入使用运行时导入（`from app.ui.graph.items.port_item import ...`）避免循环依赖
- 继承顺序: `GraphScene(SceneOverlayMixin, SceneInteractionMixin, SceneModelOpsMixin, YDebugInteractionMixin, QGraphicsScene)`
- 在 Python 中拼接包含中文引号或 HTML 属性双引号的文本时，外层优先使用单引号或对内部双引号进行转义，避免字符串过早终止导致语法错误
- 场景中的撤销/重做操作统一通过 `app.ui.graph.graph_undo.UndoRedoManager` 与 UI 级命令（如 `AddEdgeCommand`）触发，引擎层仅保留纯模型命令（`engine.utils.undo_redo_core`），避免 `GraphScene` 向引擎泄漏
- Qt 对象生命周期：`QGraphicsScene.clear()` 会释放底层 C++ 图元；若 Python 侧容器（如 `node_items/edge_items`）仍持有包装对象，任何回调（例如 Tooltip close → `YDebugHighlightManager.clear_chain_highlight`）都可能触发 `wrapped C/C++ object ... has been deleted`。因此清空/重载图时应优先清理索引容器；高亮管理器内部也应使用 `sip.isdeleted()` 跳过并清理已删除图元，避免崩溃。

