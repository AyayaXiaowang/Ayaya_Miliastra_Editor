# 节点图编辑子包（ui/graph/）

## 目录用途
`ui/graph/` 集中承载“节点图编辑器”及其周边库页面相关的 PyQt6 UI 组件与辅助模块，包括：
- 图场景、视图与撤销栈
- 节点/连线/端口等图形项（QGraphicsItem）
- 节点图库页面与通用库页面 Mixin
- 元件库与实体摆放等“资源库视图”，通过统一的左右分栏脚手架与分类树 Mixin 构建

本子包只负责 UI 与交互层，不直接负责资源持久化；节点图和模板/实例/关卡实体等资源的解析与保存统一委托给 `engine/resources` 与上层控制器。

## 当前状态
- 提供图场景、图视图与相关交互组件，用于节点图的编辑与只读预览；`GraphView` 统一暴露滚轮缩放、平移、自动排版、小地图与“跳转到图元素”等信号能力（推荐从 `app.ui.graph.graph_view` 导入，该模块作为导入门面稳定指向 `graph_view_impl.py`，避免动态加载导致重复类对象）。
- 画布内搜索：`GraphView` 内置画布搜索浮层，默认快捷键为 Ctrl+F（由 `KeymapStore` 绑定，可在“快捷键设置”中修改），支持搜索节点名/代码变量名/输入常量内容，并提供“上一个/下一个”与自动镜头聚焦；同时在右上角提供“🔍 搜索”按钮作为显式入口，搜索栏在缩放/重绘时保持窗口固定位置（避开坐标标尺区域）。另提供“适配全图”快捷键 Ctrl+0（`graph_view.fit_all`）用于手动总览大图。
- 图形项、视图、图库页面等已按职责拆分到子目录，便于在不影响整体结构的前提下演进单个模块；图视图层支持通过 `graph_element_clicked` 信号向上层报告节点/连线/空白区域的单击事件，供任务清单等页面在只读预览模式下做联动高亮，并在重绘阶段统一同步小地图和右上角浮动控件的位置与层级，确保这些辅助控件在窗口与布局变化后依旧贴合视图边缘显示。
- 画布复用：`graph_canvas_host.py` 提供 `GraphCanvasHost`，用于承载并在不同页面之间移动同一个 `GraphView`（典型场景：任务清单预览与图编辑器共享 `app_state.graph_view`），避免 “QStackedWidget 页直接持有 GraphView” 导致的 parent 限制。
- 只读语义收敛：`GraphView.set_edit_session_capabilities()` 会根据 `EditSessionCapabilities` 控制自动排版按钮显隐（只要 `can_validate=True` 就显示；允许“只读但可校验”的页面通过自动排版整理视图而不落盘）；`GraphScene.set_edit_session_capabilities()` 除了同步节点可拖拽外，也会同步将行内常量控件切为“只读但可选中复制”：文本常量允许选中复制、向量输入框改为只读仍可选中，下拉控件在只读态禁用以阻止误改。
- 画布内联控件样式：`graph_component_styles.py` 集中管理节点图画布内联控件（`QGraphicsProxyWidget` 内嵌 `QWidget`）的 QSS 片段与**紧凑尺寸常量**，基于 `GraphPalette` 固定深色调色板，供 `ui/widgets/constant_editors.py` 与 `ui/graph/items/node_item.py` 等复用，避免在具体控件/布局中重复拼装样式字符串或写死尺寸。
  - 画布内联控件的“紧凑显示”由两层共同决定：
    - 行级垂直间距：统一使用 `engine.layout.internal.constants.UI_ROW_HEIGHT`（UI 与布局层共用，避免高度估算与绘制不一致），通过收敛行高来减少控件上下留白；
    - 控件本体尺寸：由 `graph_component_styles.py` 中各控件的宽度/圆角/字号等常量控制（不靠“压扁控件高度”来做紧凑）。
- 各类图库/资源库页面复用统一的搜索与过滤 Mixin，以及集中封装的“列表刷新 + 选中策略”助手函数，用于在刷新列表时恢复选中/在列表为空时收起右侧面板，并通过标准化的确认/提示对话框保持交互风格一致。
  - 列表重建（`rebuild_list_with_preserved_selection`）在 clear/build 阶段会临时禁用 `updates` 并阻塞信号，避免逐项 addItem 触发 UI 反复刷新导致的卡顿；采用“必恢复语义”：即使 `build_items()` 抛异常，也会恢复 `updates` 与信号阻塞状态，避免 UI 假死。
- `library_mixins.SearchFilterMixin` 提供 `ensure_current_item_visible_or_select_first(...)`，用于在搜索过滤后当“当前选中项被隐藏”时自动选中第一条可见记录，避免右侧详情仍停留在已被过滤的上下文。
- 元件库与实体摆放页共用实体分类树构建逻辑：实体摆放页的“📁 全部实体”分类会聚合当前视图下所有实体实例，并在存在关卡实体时追加一行“关卡实体”记录，关卡实体也可以通过专门的“📍 关卡实体”分类单独查看；分类树与列表项的实体类型图标统一通过 `engine.graph.models.entity_templates.get_entity_type_info` 获取。
- 图场景在端口类型、布局前处理与自动连线等方面遵循引擎层规则，不在 UI 层复制业务逻辑。
- GraphScene 初始化时会从 settings 的 workspace 单一真源构建 `layout_registry_context`（LayoutRegistryContext），供节点图形项与自动排版流程显式注入端口规划/高度估算所需的注册表派生信息，避免 UI 与布局层出现“按文件位置猜 workspace_root”的隐式回退差异。
- 节点定义查找统一以 `NodeModel.node_def_ref` 为唯一真源：`GraphScene.get_node_def()` 基于 `node_def_ref.kind+key` 精确解析 NodeDef（builtin→canonical key；composite→composite_id），并在其基础上叠加信号/结构体节点的 UI 侧类型扩展；运行时不再允许基于 `title/category/#scope` 做 NodeDef fallback。
- 新建节点（撤销栈 AddNodeCommand）会在模型层为声明了 `NodeDef.input_defaults` 的输入端口补齐默认常量（仅在端口未被显式设置常量时写入）；连线仍优先于常量，避免“可选入参”在 UI 新建节点/保存/导出阶段出现缺参或缺线问题。
- `GraphScene.add_node_item()` 负责在 `addItem()` 之后触发 `NodeGraphicsItem` 的端口布局，确保图形项在布局阶段可通过 `self.scene()` 获取场景上下文（含 `layout_registry_context`）。
- 批量装配大图（`scene_builder.populate_scene_from_model(enable_batch_mode=True)`）时，连线创建会延迟触发目标节点端口重排，并在装配结束后通过 `GraphScene.flush_deferred_port_layouts()` 统一刷新，避免逐边重排导致的卡顿。
- 非阻塞大图装配：`scene_builder.IncrementalScenePopulateJob` 使用 `QTimer(interval=0)` 在主线程按 time-budget 分帧执行 `add_node_item/add_edge_item`，避免一次性创建海量 `QGraphicsItem` 卡死 UI；**批量收尾阶段的延迟端口重排（flush_deferred_port_layouts）同样按 time-budget 分帧推进**，避免“节点/连线已装配完毕但最后一帧仍长时间阻塞”的卡顿错觉；GraphView 提供 `show_loading_overlay/update_loading_overlay_* / hide_loading_overlay` 用于长任务期间展示状态/进度并阻断交互，配合控制器层实现“后台准备 + 主线程增量装配”的大图加载体验。
- 画布性能（不依赖 fast_preview 的优化）：
  - 行内常量控件虚拟化：当 `settings.GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED=True` 时，节点默认不常驻创建 `QGraphicsProxyWidget`（布尔/向量等），改为占位绘制；点击占位区域才按需创建真实控件，退出编辑后释放，显著降低大图下控件数量与重绘成本。
  - 缩放分级渲染（LOD）：当 `settings.GRAPH_LOD_ENABLED=True` 时，节点/端口/连线会按缩放比例自动隐藏细节、降低命中测试开销；视图会在绘制阶段同步当前缩放比例到 `GraphScene.view_scale_hint`，供 `EdgeGraphicsItem.shape()` 等无 option 的路径使用。
  - LOD“真隐藏”（降低枚举开销）：当缩放低于阈值时，场景会对端口图元与端口“⚙”按钮执行 `setVisible(False)`，避免虽然 `paint/shape` 早退但仍被 Qt 大量枚举调用导致的卡顿；当缩放低于连线阈值时，会对非选中/非高亮连线执行 `setVisible(False)`，进一步降低超大图鸟瞰/平移时的 per-item 成本；同时在“端口隐藏”状态下，普通节点图元会切换为 `DeviceCoordinateCache`（设备坐标缓存）以提升低倍率平移流畅度。
  - 平移/缩放降级：当 `settings.GRAPH_PAN_HIDE_ICONS_ENABLED=True` 时，交互控制器会在拖拽平移（右键/中键/空格手抓）与滚轮缩放期间将场景标记为 `_view_panning=True`（内部按来源拆分为平移/缩放，避免并发交互互相覆盖）；场景会临时隐藏端口/⚙/+ 等小图元，并让叠加层跳过 YDebug 前景绘制（图标/链路徽标等），停止交互后按当前 LOD 状态恢复，不改变用户设置与缩放语义。
  - 块鸟瞰模式（仅显示块颜色）：当缩放低于阈值且模型具备 `basic_blocks` 时，场景会自动进入 `blocks_only_overview_mode`（默认 10%=0.10），隐藏节点/连线图元，仅保留 basic blocks 的彩色矩形背景用于总览结构；该模式带回滞阈值避免临界抖动；鸟瞰模式下会隐藏块编号标签等前景叠加以减少噪音，同时仍保留画布背景（底色+网格），并根据缩放自动放大网格间距避免极小倍率下网格过密；basic blocks 的边界矩形在叠加层按节点图元 `sceneBoundingRect()`（合并 children）缓存，拖拽节点时增量扩张保持跟随，拖拽结束/节点重布局/自动排版/移动命令撤销重做后会失效并重算，从而能正确框住“可变高度节点”（例如拼装列表）。
  - 画布性能面板：当 `settings.GRAPH_PERF_PANEL_ENABLED=True` 时，`GraphView` 会在画布左上角显示实时耗时分解，并进一步细分到视图/场景/图元的 `paint/shape/update_path`（高频路径按帧聚合耗时与调用次数、输出上一帧最慢 N 个图元），用于定位超大图平移/缩放卡顿来源；面板同时会显示：
    - `未归因(last)=scene-已统计`：近似反映 Qt 内部 item 枚举/排序/状态保存等 C++ 开销；
    - `panning(last)`：保留“最后一次拖拽帧”的快照（最大段/未归因/paint calls/最慢图元），便于松手后复制拖拽时的数据。
    - 视图侧的 `drawItems` 总耗时与 item 数量（若 Qt 回调走得到），用于验证是否存在“枚举 item 过多导致的额外开销”。
    默认关闭以避免日常使用的额外统计成本。
 - 大图性能优化：当 `settings.GRAPH_FAST_PREVIEW_ENABLED=True` 时，`GraphScene` 会在“不可落盘会话（can_persist=False）且节点/连线数量超过阈值”时启用 `fast_preview_mode`，改用轻量 Node/Edge 图元（不创建端口与行内常量控件）并跳过 basic_blocks 的补算；默认关闭以避免用户打开大图时自动进入“压缩预览”。
 - 批量绘制连线（降低 item 数量）：在 `fast_preview_mode` 下可通过 `settings.GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED` 启用“批量绘制轻量预览边”（无 per-edge item）；同时在只读超大图预览场景也可通过 `settings.GRAPH_READONLY_BATCHED_EDGES_ENABLED/GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD` 启用批量边层，保留节点为 item 且不要求开启 fast_preview，显著降低超大图边图元数量；撤销/删除等 UI 命令在移除连线时会同时清理批量边层缓存，避免残留索引影响命中与绘制。
 - 节点级展开：在 `fast_preview_mode` 下提供 `toggle_fast_preview_node_detail(node_id)`，仅展开用户点中的节点（默认同一时间只展开一个），并将该节点相邻连线升级为端口对齐的 `EdgeGraphicsItem` 以便看清具体连接端口；收起时降级回轻量边。
- 节点级展开：在 `fast_preview_mode` 下提供 `toggle_fast_preview_node_detail(node_id)` / `set_fast_preview_node_detail_expanded(node_id, expanded)`；节点被选中时会自动展开（框选多选则全部展开），且不会因取消选中而自动收起；为提升大图拖拽性能，自动展开行为带防抖并会避开节点拖拽期间的频繁重建；展开节点的相邻连线会升级为端口对齐的 `EdgeGraphicsItem` 以便看清具体连接端口；用户可点节点右上角按钮手动收起。
- `scene_builder.populate_scene_from_model(...)` 的批量装配模式使用“必恢复”语义：即使装配过程中抛错，也会在 finally 中恢复 `GraphScene.is_bulk_adding_items`，避免后续交互误判仍处于批量模式。
- `logic/` 子目录集中放置信号/结构体节点的纯逻辑层（绑定解析、端口规划、NodeDef 代理），无 PyQt 依赖，供 UI 服务与单元测试复用。
 - 信号节点相关服务（如 `signal_node_service.py`）会在 UI 层基于当前包的信号配置为“发送信号/监听信号”节点补全端口与类型，并约定节点上【信号名】端口仅使用信号的显示名称进行匹配与展示；稳定绑定通过节点隐藏常量 `node.input_constants["__signal_id"]` 承载，并在变更后触发 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成 `metadata["signal_bindings"]`，避免 UI/解析/IR 多源写入互相覆盖。
 - 结构体节点相关服务（如 `struct_node_service.py`）会基于结构体定义为“拆分结构体/拼装结构体/修改结构体”节点补全字段端口与类型：结构体选择结果写入节点隐藏常量 `node.input_constants["__struct_id"]`（稳定 ID），并可写入 `node.input_constants["结构体名"]` 作为展示/兼容；端口同步后触发 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成 `metadata["struct_bindings"]`。结构体节点不再声明独立的“结构体名”输入端口，且结构体类型端口名统一为`结构体`：该端口会被实例化为 `结构体<struct_name>` 用于同型连线校验与类型展示。
  - 结构体列表来源遵循当前 `ResourceManager` 的作用域（共享根 + 当前存档根），避免在 `<共享资源>` 视图中混入其它项目存档目录下的结构体定义导致“归属错觉/同名重复”。
 - `GraphScene` 的“右键菜单桥接”已从主文件剥离到 `app.ui.scene.view_context_menu_mixin.SceneViewContextMenuMixin`；
   信号/结构体节点的菜单项与节点创建前的模型预处理统一由 `signal_node_service.py` / `struct_node_service.py` 提供（`contribute_context_menu_for_node` / `prepare_node_model_for_scene`），避免 `GraphScene` 直接硬编码业务分支。
- `GraphView` 与场景/交互的协作接口显式化：视图右键菜单仅委托 `SceneViewContextMenuMixin.handle_view_context_menu(...)`；场景侧弹出“添加节点”菜单统一调用 `GraphView.show_add_node_menu(...)`（公开方法），不依赖私有钩子探测。
- 复合节点编辑器上下文（`GraphScene.composite_edit_context`）中的“是否允许落盘写回”使用 `can_persist: bool` 作为唯一语义字段；撤销栈与虚拟引脚清理逻辑会以该字段决定是否调用 `CompositeNodeManager.update_composite_node` 写回文件。

## 注意事项
- 新增或扩展“图编辑”相关模块（场景/视图/图形项/图库页面等）时，应优先放入本目录，而非 `ui/` 根目录。
- 需要被管理面板或其他业务页面复用的能力，优先通过控制器或服务类暴露入口，避免在纯 UI 组件中掺入业务规则。
- 遵循项目约定：UI 层不使用 `try/except` 兜底，异常直接抛出，由上层入口统一处理。

