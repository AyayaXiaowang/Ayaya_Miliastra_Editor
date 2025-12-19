# UI 模块

## 目录用途
基于 PyQt6 的节点图编辑器 UI 层，包含图视图/场景、资源浏览、属性面板与管理面板等交互组件。UI 只负责呈现与交互，持久化由 `engine/resources` 负责（资源根：`assets/资源库`）。

**重要**：本项目是教学模拟系统，**任务清单系统**(`todo_list_widget.py`)是最核心的功能，它自动生成操作步骤清单，引导用户在真实编辑器中完成相同操作。

## 分层与依赖约束（双 UI 目录的定位）
- 本目录（`ui/`）是“应用层 UI 实现”：PyQt 应用与全部交互控件/控制器所在。
- `app/models/` 是“应用层的应用模型抽象”：协议/任务模型/生成器/视图模式配置，不含任何 PyQt 依赖。
- 依赖方向：仅允许 `app/ui -> app/models`；严禁 `app/models -> app/ui`，避免抽象层反向耦合具体实现。
- 建议导入模式：
  - 任务与步骤数据：`from app.models import TodoItem, TodoGenerator`
  - 视图模式配置：`from app.models.view_modes import ViewMode, RIGHT_PANEL_TABS`
  - 主题与控件：留在本目录（`app.ui.foundation.theme_manager`、各 `Widget`、`Controller`）

## 注意事项
- UI 仅承担呈现与交互，资源与索引的写回统一通过 `ResourceManager`、`PackageController` 等控制器完成；不要在 UI 层直接 `open()` 读写资源文件或绕过索引。
- 图编辑器默认只读（节点/连线/端口与常量值不落盘），可写内容由控制器统一保存；避免在控件内绕过控制器直接修改图模型或缓存。
- 跨页面交互与模式切换统一通过控制器/信号完成，禁止越层调用执行器私有方法或在 Widget 间直接访问内部状态。
- 主题与样式统一使用 `ThemeManager` / `StyleMixin` / 主题 token，避免硬编码 QSS 或颜色字符串。

## 异常处理约定
- UI 层不使用 `try/except`；所有异常应直接抛出（或通过显式的集中处理入口记录/展示），禁止兜底、降级与静默失败。

## 当前架构

### 控制器架构（主窗口）
主窗口采用**控制器架构 + Mixin 模式**，将业务逻辑从主窗口分离到独立的控制器模块，并使用 Mixin 拆分主窗口的职责：

- **主窗口** (`main_window/`)：使用 Mixin 架构将主窗口逻辑拆分为若干职责模块（主文件作为薄层入口）
  - `main_window/main_window.py`：MainWindowV2 类定义（约90行），继承所有Mixin，负责核心初始化
  - `controller_setup_mixin.py`（约130行）：控制器初始化和信号连接
  - `ui_setup_mixin.py`（约280行）：UI组件创建和布局
  - `mode_switch_mixin.py`（约340行）：视图模式切换和右侧面板管理
  - `event_handler_mixin.py`（约230行）：UI事件和信号响应
  - 向后兼容：`app.ui.main_window` 包的 `__init__.py` 直接导出 `MainWindowV2, APP_TITLE`，外部代码无需修改导入路径
- **控制器层** (`controllers/`)：包含4个独立控制器，通过信号槽实现松耦合通信
  - `PackageController`：功能包生命周期管理
  - `GraphEditorController`：节点图编辑核心逻辑
  - `NavigationCoordinator`：跳转协调
  - `FileWatcherManager`：文件监控和冲突解决

**主窗口拆分优势**：
- 职责清晰：每个 Mixin 约200-340行，易于理解和修改
- 可维护性：模块化后定位问题更快，修改范围更小
- 可测试性：各模块可独立测试（注入依赖即可）
- 向后兼容：外部代码无需修改

**控制器架构优势**：
- 单一职责，每个控制器专注一个功能域
- 松耦合，通过信号槽通信，易于测试和维护
- 可扩展，新增功能只需添加新控制器
- 状态清晰，控制器管理自己的状态，主窗口仅协调

详见 `main_window/claude.md` 和 `controllers/claude.md`。

• 主窗口顶部工具栏：提供功能包选择/基础存档操作/设置/保存状态指示等；不包含“执行任务清单(真实)”按钮（真实执行能力通过任务清单与执行监控面板配合使用）。

### 分层与模式约定（State / Controller / View + 命令与事件）
- UI 层在整体上遵循轻量版的 **State / Controller / View** 模式：
  - **State / 视图模型**：由 `engine` 与 `app/models` 提供的资源视图与任务模型充当状态层（如 `PackageView`、`GraphModel` 及 Todo 相关模型），UI 组件仅持有这些对象的引用，不在内部复制业务状态。
  - **Controller**：`ui/controllers/` 与各领域子包内的控制器（如 `GraphEditorController`、`NavigationCoordinator`、`app.ui.todo.todo_preview_controller.TodoPreviewController` 等）负责在状态与 UI 之间做转换与调度，集中承载业务流程，不直接依赖具体 Widget 结构。
  - **View**：`ui/` 下的各类 Widget、Panel、Dialog 负责呈现与交互，将用户操作转换为对控制器方法的调用与信号发射，不直接操作磁盘或引擎内部细节。
- **命令与事件**：
  - 图编辑领域的可撤销操作统一封装为 `app.ui.graph.graph_undo` 中的命令对象，通过 `UndoRedoManager` 管理；控制器与场景不在多处手写“修改模型 + 更新视图”的组合逻辑。
  - 跨页面跳转与模式切换统一通过 `NavigationCoordinator` 与主窗口事件 Mixin（如 `window_navigation_events_mixin.py`）以信号形式表达，避免组件之间的直接函数调用耦合。
  - 任务清单与执行子系统内部通过“步骤执行命令 + 执行策略对象（`AnchorSelector` / `ExecutionCoordinator` / `RetryHandler` 等）”组合驱动真实编辑器操作，UI 面板仅暴露“开始/暂停/终止/单步”等意图，不拼装底层 OCR/拖拽细节。
- **新增功能建议**：
  - 新的领域能力（例如新的资源库页面、调试工具或执行模式）优先设计为“状态 + 控制器 + 视图三层”，其中状态层依赖 engine 与 models，控制器只暴露清晰的方法与信号，视图只关心布局与交互，将复杂逻辑放在可测试的纯 Python 模块中。
  - 涉及跨页面行为时（例如从验证面板跳转到图编辑器或任务清单）应通过现有控制器与 `NavigationCoordinator` 扩展信号与回调，而不是在任意 Widget 内部直接访问主窗口或其它页面的私有方法。

### 节点图编辑模式
- 目前为**交互可用但不落盘**：允许拖拽、添加、删除、连线等所有编辑操作，用于预览与尝试；但逻辑内容不会写回文件。
- **可保存内容**：节点图变量、节点图名称、所属功能包等元信息仍可保存（变量保存仅合并，不改动逻辑）。
- **不保存内容**：节点、连线、端口、常量值等逻辑内容不写盘；离开页面或重载后恢复为文件中的版本。
- **复用编辑核心**：复合节点页面加载内部子图时，同样复用 `GraphEditorController` 的加载与交互能力（通过 `composite_edit_context` 传入上下文）；保存路径仍独立由复合节点管理器负责。
- 复合节点被选中并加载时，控制台会额外打印该复合节点的虚拟引脚统计（流程入/流程出数量），便于快速核对映射是否生效。

### 设置与跨块复制
- 全局设置对话框负责管理布局与执行相关开关（如“数据节点跨块复制”），切换关键开关后会通过 `GraphEditorController.prepare_for_auto_layout` 在下一次自动排版前按需重建当前图的模型与缓存，确保视图与布局语义保持同步。

### 懒加载（启动优化）
- 复合节点管理器页面在首次进入时才创建并加载库，避免启动即扫描/解析。
- 复合节点管理器组件 `composite_widget` 采用懒加载，未进入“复合节点”模式前该属性为 `None`；在模式切换时访问其属性前需判空（例如：保存当前复合节点前先判断 `composite_widget` 存在且 `current_composite_id` 非空）。
- 节点图库进入页面时只刷新列表，不默认选中第一项（避免自动打开编辑器）。
 - 任务清单左侧树：模板图根(`template_graph_root`)采用按需懒加载。
   - 首次“选中”该项会生成并插入详细步骤；
   - 首次“点击左侧展开箭头”同样会触发生成（通过 `itemExpanded` 信号）；
   - 展开指示器在未生成子项前始终可见（`ChildIndicatorPolicy.ShowIndicator`）。

### 核心视图组件

#### 模块结构
- **图形项** (`items/`)：端口、节点、连线的图形渲染类（QGraphicsItem）
  - `port_item.py`：端口显示、虚拟引脚映射、右键菜单、多分支编辑框
  - `node_item.py`：节点显示、标题栏渲染、端口布局、常量编辑控件管理、变参/多分支"+"按钮
  - `edge_item.py`：连线图形项
- **编辑控件** (`widgets/`)：节点输入端口的常量编辑控件
  - `constant_editors.py`：文本/布尔/向量3 输入框
- **场景** (`graph_scene.py`)：图场景核心，采用 mixin 架构；主文件作为薄层入口，核心交互与模型操作分布在子模块中
  - 继承 `SceneOverlayMixin + SceneInteractionMixin + SceneModelOpsMixin + YDebugInteractionMixin + QGraphicsScene`
  - 核心职责：初始化、add_node_item、get_node_def、布局辅助（_promote_flow_outputs_for_layout）、虚拟引脚清理、端口刷新
  - 继承/MRO 注意：为确保 mixin 覆盖 Qt 的事件与前/后景绘制，建议将 mixin 置于 `QGraphicsScene` 之前；如必须将 `QGraphicsScene` 置于首位，则需在 `GraphScene` 内显式转发 `drawBackground/drawForeground/mouse*` 至对应 mixin 方法，避免覆盖失效
  - **场景子模块**：
    - `overlays/`：叠加渲染（网格/基本块/Y调试图标绘制/文本避让）详见 `ui/overlays/claude.md`
    - `scene/`：交互、模型操作与 Y 调试三大职责 Mixin，详见 `ui/scene/claude.md`
      - `interaction_mixin.py`：鼠标事件/端口高亮/自动连接/Y调试图标点击
      - `model_ops_mixin.py`：边管理/复制粘贴/删除/高亮/验证更新
      - `ydebug_interaction_mixin.py`：布局Y调试 Tooltip/链路高亮（单链/多链4色轮换）/分页导航
- **视图** (`graph_view.py`)：图视图、键鼠交互、焦点管理、动画过渡
  - **视图子模块** (`graph_view/`)：视图组件按职责拆分到 `graph_view/` 子目录
    - `animation/`：视图变换动画辅助类（`ViewTransformAnimation`）
    - `overlays/`：叠层组件（小地图 `MiniMapWidget`、标尺绘制器 `RulerOverlayPainter`）
    - `popups/`：弹出窗口（添加节点菜单 `AddNodePopup`）
    - `controllers/`：交互控制器（事件处理、状态管理、帧设置优化）
    - `navigation/`：视口导航器（居中、聚焦、适应、动画过渡）
    - `highlight/`：高亮服务（节点/连线/端口高亮与灰显）
    - `context/`：上下文菜单桥接（添加节点菜单显示逻辑）
    - `top_right/`：右上角控件管理器（自动排版按钮与额外按钮）
    - `auto_layout/`：自动排版控制器（验证、克隆布局、差异合并、同步）
    - `assembly/`：视图装配器（setScene/resize 联动）
    - 外部仍从 `ui/graph_view.py` 导入 `GraphView`，保持 API 稳定；主文件仅保留薄层入口，将视图行为委托给各子模块
    - 详见 `ui/graph_view/claude.md`

- `graph_view.py`：图视图，键鼠快捷键与焦点管理，支持平滑动画过渡，删除连线等编辑动作通过 `app.ui.graph.graph_undo` 的命令对象进入撤销/重做链
  - 高亮策略：提供批量高亮 API（一次性高亮两个节点与连线），避免逐个高亮相互清除
  - 端口高亮回退：当步骤未提供端口名时，视图将从边数据推断源/目标端口并进行高亮
  - 右上角浮动控件：仅保留“自动排版”按钮；如有需要，可通过 `set_extra_top_right_button()` 放置一个自定义操作按钮（例如预览页的“编辑”）
  - 自动排版：执行“克隆就地布局 + 差异合并 + 回填坐标/块”的一致性流程：
    - 同步策略（增强版）：始终基于当前模型克隆一份并运行一次就地布局（含跨块复制与清理），将“克隆布局”与“当前模型”做差并双向同步：
      - 新增：合并克隆布局中存在而当前缺失的节点与连线（例如跨块复制产生的副本与其连线）；
      - 删除：移除当前存在而克隆布局中已删除的连线（例如被“副本→副本”替换后的原始跨块旧边）；
      - 清理：仅当节点为“数据节点副本”且在克隆布局中已消失时，才会从当前模型中删除该副本（对应“孤立副本清理”）；
    - 回填：坐标与 `basic_blocks` 统一取自该克隆布局（即“合并来源”），确保“坐标/块集合/副本与连线”在首次自动排版即完全一致；`_layout_y_debug_info` 同样优先使用克隆布局中的信息，若缺失再回退到纯计算结果。
    - 端口识别一致性：在克隆体上根据节点库显式端口类型临时“提升流程输出端口命名”，以便布局阶段按“流程口规则”正确识别流程边（与 `GraphScene` 初始化路径保持一致）；不改变原模型与 UI 展示。
    - 该同步保证“设置里切换‘数据节点跨块复制’开关后刷新”不会残留旧连线或孤立副本，画面始终与最新布局语义一致。
  - 排版前回调：视图在执行排版前会调用 `on_before_auto_layout()`（由主窗口注入）。默认不重载模型，仅在设置切换触发的一次性标记下（例如将“数据节点跨块复制”从 True→False）才清缓存并从 `.py` 重新解析；发生重载时会自动保存并恢复视图缩放与中心点，确保画面稳定不偏移
  - 坐标标尺：顶部/左侧标尺在缩放时按像素密度自动合并刻度，避免数字重叠；基础间距为 250，当像素间距不足时成倍合并（如 500/1000/...）。
  - 加载大图的场景更新：`GraphScene` 在批量构建阶段不会为每个节点单独重算 `itemsBoundingRect` 与小地图范围，而是由控制器在批量添加完成后统一调用场景的重建入口，一次性更新场景矩形与小地图缓存，保持网格与小地图功能完整同时降低大图加载卡顿。
  - 拖动时的连线刷新：节点自身通过 `NodeGraphicsItem.itemChange(ItemPositionHasChanged)` 仅刷新与该节点相连的连线，场景层不再在每帧遍历全部连线统一 `update_path()`，避免大图中拖动单个节点时出现与连线数量成正比的卡顿。
- “添加节点”菜单（AddNodePopup）：列表项直接存放 `NodeDef` 对象，避免同名 server/client 变体因键冲突误取；菜单会按 `GraphView.current_scope`（server/client）过滤作用域。
- 添加节点弹窗的分组规则：
  - 功能类别分组：按 `NodeDef.category`（事件节点/执行节点/查询节点/…）进行分组与着色；
  - 复合节点分组：额外提供“复合节点”分组，展示所有带 `is_composite=True` 的节点（不影响其在功能类别分组下的展示与筛选）；
  - 搜索/端口类型/作用域等过滤条件同样作用于"复合节点"分组，确保与其它分组行为一致。
- `GraphEditorController.load_graph()` 会在加载后根据图的 `metadata.graph_type` 设置 `GraphView.current_scope`，确保"添加节点"列表与当前图类型一致。
  - 自动排版完成后的行为：通过主窗口注入的回调，在排版完成后将当前 `GraphModel` 写入持久化缓存（默认 `app/runtime/cache/graph_cache/`），并调用 `GraphView.fit_all()` 自动适配全图并居中视图，使再次打开时直接使用最新位置（不改动 .py 文件）。
- `graph_scene.py`：图场景，图形项与命令触发（通过 `app.ui.graph.graph_undo.UndoRedoManager` 及一组 UI 命令封装），基本块可视化绘制；引擎侧仅暴露纯模型命令（`engine.utils.undo_redo_core`），UI 命令集中在 `app.ui.graph.graph_undo`，避免引擎层依赖 `GraphScene`
  - **节点颜色**：`NodeGraphicsItem._category_color_start/end()` 决定节点标题栏的渐变颜色
    - 优先级：虚拟引脚 > 复合节点（通过`composite_id`判断）> category映射
    - **集中管理**：复合节点标题栏颜色统一来源于 `app.ui.foundation.theme_manager.Colors`
      - `Colors.NODE_HEADER_COMPOSITE_START` / `Colors.NODE_HEADER_COMPOSITE_END`
      - 渐变风格：银白（适配深色画布）；预览组件与右侧"虚拟引脚"面板中的复合节点外观同源
  - **基本块显示**：在背景层绘制半透明矩形标识基本块区域
    - 默认开启：`settings.SHOW_BASIC_BLOCKS = True`（见 `engine.configs.settings`）
    - 初始化行为：若当前 `GraphModel.basic_blocks` 为空，场景初始化时通过引擎 `engine.layout.LayoutService` 的纯计算结果填充 `basic_blocks`（不改动节点位置）
    - 适用范围：编辑器与任务清单右侧只读预览共用同一机制
  - **编号标签**：在前景层（`drawForeground`）绘制，确保不被节点遮挡
    - 每个基本块左上角显示编号（1、2、3...）
    - 圆角矩形背景，文字颜色自适应背景亮度
    - 标签使用块颜色作为背景（90%不透明），自动计算最佳文字颜色（黑/白）
  - **信号系统集成**：`GraphScene.get_node_def()` 会在基础节点定义上为“发送信号/监听信号”节点构造视图型 NodeDef 代理，根据信号绑定与当前包的 `SignalConfig.parameters` 为参数端口写入精确的类型信息，使端口配色、连接高亮与节点常量编辑控件（布尔/三维向量等）能够直接依赖信号参数类型，而无需在 UI 层重复解析配置。`GraphEditorController.load_graph()` 在批量装配场景后会基于当前包的信号定义计算 schema 哈希，仅在 `GraphModel.metadata["signal_schema_hash"]` 与当前版本不一致时调用场景的 `_on_signals_updated_from_manager` 刷新信号端口，从而在信号未变更时保持已有端口结构与布局稳定。
  - **布局Y坐标调试（轻量图标+Tooltip）**：当 `settings.SHOW_LAYOUT_Y_DEBUG = True` 且模型包含 `_layout_y_debug_info` 时，在每个节点右上角绘制一个“!”小图标；点击该图标会弹出说明卡片，使用“说人话”的中文解释当前 Y 轴位置的最终结果与候选来源（如“列底”“对齐关联端口”“唯一目标对齐”“多输出中点”等），并给出简短的使用提示。说明卡片不再因点击空白区域自动关闭，仅通过标题栏“XX”按钮或点击其他节点的调试图标时关闭。该方案不再进行全局文本避让与端口叠加，极轻量、不卡顿。点击拦截发生在 `GraphView/GraphScene`（命中区域做了±6px 的轻微扩展以提升可点性），关键日志前缀为 `[YDEBUG-CLICK]`（打开/未命中）与 `[YDEBUG-TOOLTIP]`（显示）。
    - 说明卡片尺寸：内容区域字号相对默认略放大一档（约 1.4 倍），宽度适中，并通过滚动区域承载长文案。
    - 关联链路展示：以可点击链接渲染；点击某条链后，高亮该链涉及的所有数据节点/端口/数据连线，其他元素置灰；链上节点在左上角绘制醒目的序号徽标（带边框），显示“链内序号”。当关联链路超过 10 条时，说明卡片内支持分页查看。
    - 高亮全部链路：说明卡片“关联链路”标题后提供“高亮全部/清除”操作。高亮全部时，仅高亮“当前节点”的所有链路；不同链以 4 种颜色循环着色（边与端口显示对应颜色，节点绘制对应颜色的外描边），并在节点左上角绘制链编号徽标（显示“链ID”）。若某个节点属于多个链路，采用其最小链ID的颜色与编号。清除操作移除该全链路着色（不会改变普通选择或单链高亮状态）。
    - 流程节点的链路展示：流程节点同样提供“关联链路”，内容为“连在它的数据入口的链路”（按 `target_flow == 当前流程节点` 汇总），同样支持点击链路高亮与分页。
  - **端口明细显示策略**：与 Y 调试开关联动的“端口序号与Y坐标”不再全图叠加展示，已并入 Tooltip 文本中（仅在点击图标时可见），避免大量测量与避让计算带来的性能开销。
  - 说明卡片内容顺序：优先展示“关联链路”（若不存在则说明原因），随后展示“最终位置/候选来源”等摘要。
  - Tooltip 顶部补充展示“所属块（第 N 块，block_N）”与“所属事件流名称”（若存在），若名称缺失则回退展示“事件根节点ID”，便于快速定位上下文。
  - **多分支端口标签策略**：分支输出口使用常规输出标签展示端口名；内联匹配值编辑框默认隐藏，仅在需要编辑时显示；常规输出标签对所有输出端口均绘制（含 `流程出`、`默认` 及各分支）。
  - **流程端口判定（输入/输出侧）**：统一使用 `engine.nodes.port_type_system.is_flow_port_with_context(node, port_name, is_source, node_library)` 并传入场景的 `node_library`，优先依据 NodeDef 的显式端口类型，再回退名称规则；多分支节点的所有输出端口视为流程端口（规则已覆盖）。
- `dynamic_port_widget.py`：多分支节点的动态端口管理UI组件，**端口名即匹配值本身**（整数→如 `0`，字符串→如 `hello`，默认口为 `默认`）
  - 多分支端口添加：当已有分支为字符串时，新增需输入字符串（端口名即输入内容）；当尚无或已有整数分支时，自动添加使用节点定义声明的范围端口并按 `engine.nodes.port_name_rules` 生成具体端口名，全部回退逻辑集中在 `_generate_dynamic_port_name()`，确保 UI 与引擎一致。
  - 端口新增流程复用 `_add_port_via_command()` 执行统一的撤销命令，并通过 `app.ui.foundation.dialog_utils` 提供的标准提示告知重复/非法输入，字符串/范围模式保持同一代码路径。
  - `AddPortDialog` 继承 `BaseDialog`，复用主题对话框样式并在确认时阻止空输入。
  - `AddPortButton` 等 `QGraphicsItem` 子类在 `super().__init__()` 过程中会被 Qt 调用 `boundingRect()`，因此需要在调用基类构造前就写入诸如 `button_size` 这类几何字段，避免属性尚未初始化即被访问。
- `node_detail_overlay.py`：节点详情浮窗（远距离高亮端口）
  - 流程端口判定：统一使用 `engine.nodes.port_type_system.is_flow_port_with_context(node, port_name, is_source)`，避免名称硬编码与语义漂移；端口图形项的 `is_flow` 仅作为显示层标记来源，不再做逻辑判定。
- `navigation_bar.py`：导航栏

### 功能页面组件
- `package_library_widget.py`：功能包总览与管理（查看包含内容、重命名、删除）。包含两个特殊视图：
  - 全部功能包（global_view）：显示全部资源，仅浏览；不可重命名/删除
  - 未分类功能包（unclassified_view）：显示未被任何功能包纳入的资源；不可重命名/删除
- 详情页"节点图"列表以中文名展示（读取图元数据中的 `graph_name`）；第二列表格单元的 tooltip 显示对应的图 ID，便于定位与复制。
- `template_library_widget.py`、`entity_placement_widget.py`：元件库与实体摆放页面在刷新时会保持用户之前选中的元件或实例，当用户在右侧属性面板添加节点图、自定义变量等内容后，左侧列表刷新会恢复之前的选中状态并重新触发选中事件，确保右侧属性面板立即显示更新后的内容（包含新增的节点图数量、变量数量等统计信息），无需用户手动切换选择。元件/实体属性面板的基础信息页统一通过 `metadata["guid"]` 存储 GUID，模板、实例与关卡实体各自维护独立的 metadata 字典；实体摆放页修改实例 GUID 只写入对应实例资源，存档库页面通过 `ResourceManager.get_resource_metadata()` 的 `guid` 字段展示当前落盘状态。
- `graph_library_widget.py`：节点图库与检索
  - 子模块（职责拆分）：`ui/graph_library/`
    - `folder_tree_mixin.py`：文件夹树/右键菜单/拖拽移动/重命名/子文件夹
    - `graph_list_mixin.py`：卡片列表渲染/筛选/排序/编辑与删除/详情/变量
  - 主组件仅负责装配 UI（_setup_ui/_apply_styles）、信号绑定与基础状态（current_*）
  - 节点图库过滤规则：
    - 全局视图：显示全部节点图（按类型/文件夹组织）
    - 未分类视图：仅显示未被任何功能包引用的节点图
    - 具体功能包：仅显示该包索引 `PackageIndex.resources.graphs` 中的节点图
- `template_library_widget.py`：元件库
- `combat_presets_widget.py`：战斗预设（文件列表形式）
- `entity_placement_widget.py`：实体摆放（文件列表形式）
  - 模板/实例/关卡实体与存档归属（“所属存档”行）统一通过 `PackageEventsMixin` 与 `PackageController.current_package_index` 协调：
    - 右侧属性面板中勾选/取消某个存档，只更新对应存档的索引对象（当前存档使用内存副本，其它存档通过 `PackageIndexManager` 即时落盘），再由 `save_package()` 统一写回索引文件；
    - 当前存档下的元件/实体列表依赖 `PackageView.templates` / `PackageView.instances`，勾选状态变更会同步失效其内部缓存并调用 `refresh_templates()` / `refresh_instances()`，保证列表与“所属存档”选择始终一致，不出现“列表没变或切换存档后勾选被还原”的情况；
    - 结构体定义、战斗玩家模板等管理项的归属同样以“每个存档自己的索引字段”为唯一来源，全局/未分类视图仅作只读聚合，不直接写入资源或索引。
- 管理配置库与管理面板相关组件：
  - `graph/library_pages/management_library_widget.py`：管理配置库主界面，使用“左侧管理类型列表 + 右侧列表”的双栏布局展示计时器、变量、预设点、外围系统等管理资源，并通过 `active_section_changed` / `data_changed` 信号与主窗口及持久化链路解耦。
  - `management/section_registry.py`：集中声明各管理 section 的 `key/title/group/resources` 等元数据，为管理配置库与存档库等视图提供统一的中文标题与聚合规则来源。
  - `graph/library_pages/management_sections_base.py` 与 `management_section_*.py`：为每个管理类型提供 `iter_rows/create_item/edit_item/delete_item` 等列表语义实现，所有业务逻辑下沉到 Section 中，库页面本身只负责装配 UI 与分发用户动作。
  - 管理配置库中体量较大的 Section（例如结构体定义）在枚举列表时会复用基于 `ResourceManager` 的进程内只读缓存，并在对应资源增删改后显式失效缓存，以减少频繁切换类别时的磁盘扫描与 JSON 解析开销。
  - 主窗口在管理模式下通过 `PackageEventsMixin._on_management_selection_changed` 将当前选中的 (section_key, item_id) 映射到右侧属性/编辑面板：大多数管理类型使用通用的 `ManagementPropertyPanel` 展示摘要，信号/结构体/主镜头等复杂类型则使用专用的 `SignalManagementPanel` / `StructDefinitionManagementPanel` / `MainCameraManagementPanel`。
  - 样式层复用 `StyleMixin.apply_management_widget_style()` 控制管理相关列表与树的配色与基础控件样式，保持与其它资源库页面一致的观感。
- `management/` - 管理配置元数据与 Section 注册表目录
  - `section_registry.py` - 管理 section 元数据注册表（仅描述标题/分组/资源 key 与聚合模式，不再维护旧式页面类映射），供管理配置库页面与存档库等视图共享。
  - 旧版配置页面基类（`BaseConfigPage/StandardTablePage/FormTablePage/DualPaneConfigPage` 等）已下线，管理模式入口与编辑体验统一由 `app.ui.graph.library_pages.management_library_widget.ManagementLibraryWidget` + 各 `BaseManagementSection` 与右侧属性/专用 Panel 承担；表单类编辑对话框统一复用 `app.ui.foundation.base_widgets.FormDialog` 与 `app.ui.forms.schema_dialog.FormDialogBuilder` 等辅助工具。
- `composite_node_manager_widget.py`：复合节点管理库页面（基于 `DualPaneLibraryScaffold` 的“左树+右编辑区”骨架，左侧树由 `CompositeNodeService` 提供扁平行数据并支持按文件夹组织，右侧通过 `GraphEditorController.load_graph_for_composite` 复用节点图编辑核心，在默认逻辑只读模式下仅在内存中加载和尝试编辑复合子图，不写回源码）
- `todo_list_widget.py`：任务清单组件（组装与依赖注入）
  - 结构化子模块（职责内聚）：
    - `todo_tree.py`：树构建、懒加载、增量刷新、三态/样式
    - `todo_detail_panel.py`：详情页渲染与统计（依赖 `TodoDetailAdapter/Renderer`）
    - `todo_preview_panel.py`：预览加载/缓存、聚焦/高亮（内聚 `TodoPreviewController`）
    - `todo_executor_bridge.py`：执行入口/步骤切片/监控上下文注入与状态回填（与 UI 解耦）。定位图根优先沿树项父链，若树为懒加载未展开则沿 `todo.parent_id` 逐级回溯至 `template_graph_root`。
    - `todo_runtime_state.py`：运行态状态/提示的集中状态机（success/failed/skipped）
    - `todo_context_menu.py`：右键菜单与动作（仅创建菜单与触发执行桥）
  - 图数据加载与复用统一使用 `app.common.graph_data_cache`，模型/执行/跳转/树节点共享同一 cache key，避免把整张图字典写入 detail_info。
  - 主体仅负责装配、信号转发与依赖注入，保持快捷键与行为不变
  - 注意：预览条件放宽为“有 graph_data 即可”；graph_id 可为空（仅影响按图ID过滤事件流的优化，不影响显示与高亮）
  - 当前状态：树/详情/预览/执行/运行态/右键菜单均已模块化，主组件不再承载这些领域逻辑
  - 预览：右侧使用 `GraphView+GraphScene` 的只读模式展示节点图，禁用拖拽、增删节点/端口与快捷键编辑；顶部右侧复用“自动排版”悬浮区域的定位逻辑放置“编辑”按钮，点击后通过跳转协调器直接打开该图进入编辑器（不闪现图库页），主窗口统一切换到编辑器模式以同步左/右面板
  - 交互：点击父级“事件流根/模板图根”同样显示预览
    - 事件流根：加载其所属图并对该事件流涉及的节点集合进行聚焦（成组适配）
    - 模板图根（配置节点图）：加载其所属图并适应全图显示（fit all）
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
  - 执行入口（右侧详情/预览工具栏共用一组主按钮）：
    - 主执行按钮文案会根据步骤类型自动调整：
      - 叶子图步骤：显示“执行当前步骤”，仅执行这一条 Todo
      - 模板图根：显示“执行整张节点图”，按清单顺序连续执行整图
      - 事件流根：显示“执行整个事件流”，仅执行该事件流下的所有步骤
      - 复合节点步骤：显示“查看复合节点指引”，只在执行监控面板输出操作指引，不触发自动化
    - “执行剩余步骤”：仅在叶子图步骤上可见，从当前步骤起连续执行到同级末尾（在“配置节点图”步骤隐藏）
    - 单步执行在真实执行前会调用执行策略对象对当前画面做一次“快速映射+退化校验”（原点平移投票 → 相对锚点匹配 → 单锚点匹配），成功时会同步可见节点坐标，用于后续创建步骤基于已有节点推断创建位置；若仅此一步为创建类步骤且校验失败，则在当前坐标校准结果下继续尝试执行，以支持“空画布首次放置锚点”的场景。
  - 预览控制器：`todo_preview_controller.py` 负责只读加载图、高亮与聚焦动画，基于“detail_type → handler” 的映射按任务类型分发处理；每个 handler 专注于“如何选出节点/边集合并组合高亮/聚焦动作”，共享一组模板化辅助方法（批量清理/隐藏覆盖层/灰化与聚焦调度），避免出现单体 if/elif 分支树
  - 详情渲染器：`todo_detail_renderer.py` 负责根据任务类型输出右侧详情HTML（表格/摘要）
  - 详情适配器：`todo_detail_adapter.py` 提供分类/模板/实例等统计与汇总数据，减轻主组件负担
  - 导航控制器：`todo_navigation_controller.py` 负责上/下一个任务导航与 Ctrl+P 路由
  - 树三态与增量刷新：`tree_check_helpers.py` 统一封装父子联动、父节点三态与叶子节点文本/样式应用
  - 树项富文本：`todo_rich_item_delegate.py` 支持按分段 tokens 绘制（图标/动作/节点名/计数），动作词采用“步骤类型色+浅色底+加粗”，节点名采用“节点类别色”，使不同步骤更显眼且彼此颜色不同；不支持类型及警告/失败态自动回退为整段单色文本。
  - 节点图步骤类型（节选）：创建/连接/设置端口类型（`graph_set_port_types_merged`，颜色=青色）/参数合并(`graph_config_node_merged`，颜色=紫色)、动态端口新增（变参/字典/分支）、以及“分支输出值配置”(`graph_config_branch_outputs`)；预览高亮节点并聚焦。
  - 设置端口类型：预览仅高亮“需要设置类型的端口”，即声明类型属于“泛型家族”（以“泛型”开头，包括泛型/泛型列表/泛型字典等）的输入与输出数据端口（排除流程端口）；非泛型端口不高亮
  - 预览类型判定依赖节点库：在加载预览时将主窗口的节点库注入 `GraphView/GraphScene`，用于按端口声明类型进行高亮筛选
  - 树交互准则：
    - 父级/容器型树项（含子项、模板图根、事件流根）不可由用户直接勾选，仅用于显示三态进度与导航；点击标题仅切换选中，不触发批量勾选。
    - 若用户尝试对父级复选框进行交互，将被忽略，父级勾选状态仅由其子项完成度计算并回填三态，不会触发对子项的批量状态修改或整树刷新。
    - 仅叶子步骤可勾选为“完成”。
    - 叶子步骤的复选交互由自定义委托处理：仅在点击复选框本体时切换勾选状态；点击该行文本仅改变选中高亮，不影响勾选状态。
    - 选中“模板图根/事件流根”默认不自动加载右侧预览，保持在“详情”；需要预览或执行时再使用相关按钮或选择具体步骤。

### 日志与性能
- **懒加载任务**：进入“任务清单”页面不会解析/加载所有节点图，仅渲染树结构与摘要；当用户首次选中某个“节点图根”时，才按需生成该图的详细步骤并加载预览所需的图数据。
- **解析/布局缓存**：图资源由 `ResourceManager` 提供两级缓存（内存+磁盘），命中时不重复解析与自动排版。
- **UI详细日志**：端口布局与连线创建等调试输出受 `settings.GRAPH_UI_VERBOSE` 控制，默认关闭，避免打开大图时控制台刷屏。
  - 任务树展开规则：默认展开所有父级；事件流根（`detail_info.type == "event_flow_root"`）默认折叠，便于大图下快速定位其它步骤。
  - 任务树事件流排序：按事件起点节点的 Y 坐标升序显示（Y 小在前），与画布垂直布局一致。
- 任务树着色（白底）：叶子步骤按“步骤类型”与“节点类别”着色，颜色集中于 `ui/todo_config.StepTypeColors`，与 `graph_scene.py` 类别主题色一致，确保白底可读。
 - 树文字渲染：树第0列采用自定义 `QStyledItemDelegate`，改为用 QTextDocument 绘制 HTML（与右侧日志一致的渲染路径）。
  - 支持类型：`graph_connect`/`graph_connect_merged`/`graph_create_node`/`graph_create_and_connect(_reverse/_data)`。
  - 规则：动作词（如“连接/连线并创建/创建节点”）使用步骤类型色；节点名严格使用节点类别色（直接读取 `GraphModel.nodes[*].category` 并映射 `StepTypeColors.NODE_CATEGORY_COLORS`）；分隔符与尾注（如“→”“（N条）”）使用中性色；文本前字符图标沿用原样式。
  - 状态优先级：失败/跳过/已完成优先，使用整行统一色与删除线（委托不分段着色）；正常状态使用分段颜色。
  - 选中态仍由样式系统绘制背景，文字由委托绘制，不受 `::item:selected { color: ... }` 统一文字色影响。
  - 视图重绘优化：`GraphView` 采用 `MinimalViewportUpdate` 与 `CacheBackground` 缓存背景，降低大图下的重绘成本；加载批量构建阶段建议在控制器侧暂时禁用视图更新/场景信号，并将 `QGraphicsScene.ItemIndexMethod` 设为 `NoIndex`，完成后恢复 `BspTreeIndex` 再刷新视图。
  - 交互期间清晰度：为避免拖拽节点/框选/连线预览时出现残影或框线残留，左键交互开始时临时切换为 `FullViewportUpdate + CacheNone`，松开后恢复并失效背景一次。
- 执行监控面板：复合节点或节点图步骤点击"执行"后，右侧标签页显示"执行监控"面板（非弹窗）。面板展示每一步产生的真实视觉产物（截图 + 可选叠加），不轮询桌面，不进行实时监控；执行编排由 `ui/execution/runner.py` 统一驱动。所有执行过程中的错误信息、前置条件缺失等统一记录在本面板的日志区域显示（不使用消息弹窗）；若监控面板不可用时才退化为顶部 Toast 提示。面板提供"检查当前页面"按钮，可立即对外部编辑器进行一次截图并在画面上叠加识别出的节点矩形与端口位置用于对照（识别统一通过 `app.automation.vision` 门面，标题已回填库里的完整名）；提供“匹配并定位镜头”按钮与基于同一拖拽逻辑的实验控件：
  - 定位优先规则：若当前画面存在“可见的唯一标题（模型中仅一处的标题）”，优先以这些唯一节点的程序外接矩形作为聚焦目标；否则按当前编辑器视口矩形聚焦。
  - 缩放一致性：在执行匹配与定位前，先对“节点图缩放区域”进行 OCR 检查并确保画布缩放为 50%，无法校正则取消定位操作并输出原因。
- 拖拽测试：在“定位镜头”成功建立坐标映射后，监控面板会显示最近一次编辑器视口在程序坐标系中的中心点，并提供 X/Y 输入框与“拖拽到坐标 / 向左拖拽 / 向右拖拽”按钮；内部统一通过 `EditorExecutor._ensure_program_point_visible` 执行画布平移，与真实步骤执行时的视口对齐逻辑完全一致，仅改变视口位置，不修改图模型。
- 日志区域支持文本搜索与类型筛选（仅点击/仅拖拽/仅鼠标操作/识别/OCR/截图/等待/连接/创建/回退/校准/视口/步骤/成功/失败），不同类型以左侧色条与行首徽标区分（顶部控件以“搜索:”与“筛选:”明确区分），颜色在白底下可读性良好（成功绿、失败红、点击蓝、拖拽深蓝、等待橙、识别紫、OCR 青绿、截图蓝灰、连接深橙、创建深青、回退琥珀、校准蓝、视口青）。
  - 视口对齐：驱动层在需要平移时向执行器传入 `GraphModel`，每次小步拖拽后会尝试基于“中文名精确配对+RANSAC”的几何重拟合，以排除新增/消失节点对坐标映射的干扰。
  - 识别测试（完整）：面板内提供以下测试按钮，点击后直接在面板画面叠加展示结果并输出日志：
    - 测试文字OCR：对顶部标签栏执行 OCR；
    - OCR缩放：对“节点图缩放区域”执行 OCR（用于校验 50%）；
    - 测试节点识别：识别并标注所有节点矩形与中文标题；
    - 测试端口识别：为每个识别到的节点列出端口并标注 kind/side/index；
    - 测试Settings：优先依据当前图扫描 Settings 行；若当前未注入模型，则回退为“对检测到的所有节点逐一枚举 Settings 行”；
    - 测试Warning：匹配 Warning.png 模板并显示命中框与置信度；
    - 测试Settings模板：匹配 Settings.png 模板；
    - 测试Add模板：匹配 Add.png / Add_Multi.png 模板；
    - 测试搜索框模板：匹配 search.png / search2.png（整窗范围）。

### 任务清单详情（UI 数据访问）
- `TodoDetailPanel` 通过 `host_list_widget` 访问运行态数据源：
  - 优先使用 `host_list_widget.tree_manager.todo_map`（权威）
  - 回退至 `host_list_widget.todo_map`
  - 这使详情渲染的适配器无需直接依赖树控件，实现与主组件的低耦合
- 左侧步骤树状态呈现：
  - 完成：仅以复选框勾选与置灰（删除线）表达，不再在标题前额外加“✓”。
  - 失败：以“✗”红色标示并显示提示；不改变复选框。
  - 跳过：以“⚠”橙色标示并显示原因（例如：连线端点在当前视口无法同屏）。
  - 连续执行在启动阶段即预置第一步的“行首步骤标签”，因此在坐标映射/识别缓存清空等最早期日志也能显示步骤标签；每步开始时会自动刷新为当前步骤。
  - 体验约定：每次点击“开始监控”或打开历史大图预览时，图片都会自动按当前容器视口进行等比缩放以完整显示，并保持居中；随后用户可用滚轮继续放大/缩小，拖拽进行平移。
  - 画面：截图区域支持双击打开非模态历史预览；预览窗口右侧为大图区，左侧为**当前运行的截图历史缩略图列表**（按时间顺序）。支持点击任意缩略图切换查看旧图；大图支持滚轮缩放（以鼠标为锚点）与按住左键拖拽平移。
- 缩略图标题：缩略图条目文本包含“序号 + 微动作标题”，优先显示本次截图对应的“操作/识别内容”（来自覆盖层 header 或最近一条日志，例如“模板匹配: Node_list.png 命中”“OCR: 设置节点图变量 …”）；若无微动作则回退为“当前步骤名”。截图左上角横幅同样采用这一标题策略。
  - 连续执行在启动阶段即预置当前第一步的步骤上下文，因此启动阶段（缩放检查/快速匹配/校准）产生的截图也带有步骤名，缩略图不再仅显示序号。
  - 历史预览对话框与主应用使用同一主题样式（字体/QSS），中文步骤名在列表与大图标题处可正确显示。
  - 可视化统一：执行驱动会在"坐标校准"和"视口对齐"阶段同样传入 `visual_callback`，这些阶段的截图叠加（安全区/目标点、锚点节点/布置区域）也会展示并纳入历史列表。
  - 控制：暂停 / 继续 / 终止；任意时候按 Ctrl+P 立即暂停（暂停逻辑由监控组件集中处理，外层仅发送请求）
    - 暂停生效点：创建节点前、输入搜索文本前、候选列表OCR轮询中、拖拽连线前
    - 终止行为：立即中断当前执行，包括坐标校准、视口对齐（画布平移）与回退重试阶段
- 单步执行：勾选面板上的"单步模式"，在每个步骤开始前自动暂停；点击"下一步"仅执行一个步骤，下一步开始时再次暂停；
  - 若启动阶段已通过“快速匹配镜头”（识别+几何拟合）建立比例与原点，单步模式不会再次做识别校验，避免重复日志与叠加。
  - 单步完成后：仅勾选当前步骤，不自动跳转下一步；如需下一步请点击"下一步"。
- 模板节点图连续执行：在"节点图根任务（template_graph_root）"点击"执行"，严格按清单左侧显示顺序连续执行；
  - 连续执行期间启用严格创建模式：创建步骤不会因为“场上已有同名/相似节点”而跳过，确保跨基本块时始终按清单逐步创建；需要去重仅在单步或外部直接调用时由坐标阈值判断（≤30px 视为已存在）。
  - 单次校准：连续执行未中断且未进行画布拖动时，仅在开始阶段校准一次；跨基本块不会重复校准。
  - 锚点创建去重：若校准阶段已创建/确认首个锚点节点，则首个创建步骤自动判定完成并跳过，以避免重复创建（以 editor 左上角≤30px 阈值判定“已到位”）。
  - 每步开始前：自动选中该步骤（右侧详情与预览同步）
  - 每步成功后：自动勾选该步骤，并"跳到下一步"（等价于用户按下 Ctrl+]）
  - 执行完成后选中：
    - 若从子步骤发起（单步或从此步到末尾），结束后仍停留在该子步骤。
    - 若从父级发起（图根/事件流根），结束后仍停留在该父级。
  - 执行按钮可见性：事件流根（`event_flow_root`）同样显示“执行”按钮，点击仅执行该事件流的子步骤。
- 父级空步骤回退：当从“节点图根/事件流根”点击“执行”且规划步骤为空时，仍会打开右侧“执行监控”并注入当前图上下文，便于直接使用“检查/定位镜头”；此时不启动执行线程。
- 端口类型设置（`graph_set_port_types_merged`）与参数配置（`graph_config_node_merged`）均纳入连续执行与单步执行；右键菜单亦支持对其"仅执行此步骤"与"从此步到末尾"。
  - 右键"仅执行此步骤（一步）"：执行完成后仅勾选，不自动跳转下一步。
- 任务树右键：提供两种执行入口（仅对受支持的节点图步骤类型）
  - "仅执行此步骤（从此步到末尾）"：从当前步骤起连续执行至链路结束
  - "仅执行此步骤（一步）"：只执行当前这一步，便于快速验证单个动作
- 执行时由 `ExecutionRunner` 自动选择锚点并校准坐标；启动阶段通过 `ExecutionCoordinator.ensure_zoom_50()` 对 `节点图缩放区域` 执行 OCR 检查并确保画布缩放为 50%，随后优先尝试“识别+几何拟合（等比缩放+平移）”建立比例与原点；单步模式在真正执行该步之前会额外进行一次识别与几何校验；无法校正到 50% 或校验未通过时将终止当前执行，避免坐标映射失配。锚点优先级：
  - 快速模式：执行启动时优先尝试“识别+几何拟合（等比缩放+平移）”直接建立比例与原点；若拟合通过，则跳过创建锚点的校准流程；创建节点默认采用“输入后回车快速确认+可见性校验”，失败再回退到 OCR 候选点击。
  - 单步模式：在真正执行该一步之前，执行器会对当前画面做一次“识别+几何拟合（等比缩放+平移）”校验（中文名精确匹配，默认采用“内点率≥15% 或 内点数≥6”，且相对几何误差≤25%），
    通过后更新比例与原点以保证坐标换算正确；未通过时中止该步并输出原因。
  1) 首个创建类步骤的节点（可选择创建作为锚点）
  2) 首个连接类步骤（`graph_connect`/`graph_connect_merged`）涉及的任意一端既有节点
  3) 若仅含参数配置步骤（`graph_config_node`/`graph_config_node_merged`），使用该步骤的目标节点作为锚点
  若直接从连线类步骤单步执行，请确保至少一个端点已在当前视口可见，否则校准可能失败。
  - 坐标校准会将当前 `GraphModel` 传入执行器，用于在同名节点出现多个时做多候选锚点消歧（基于邻域一致性评分）。
  - 右键菜单采用浅色样式（白底深色字，选中浅蓝底），确保在深色主题下可读性。
- 当执行前置条件缺失（未找到模板图根/无图数据/无监控面板等）时，优先将原因写入右侧“执行监控”日志并自动切换显示；仅在无法获取监控面板时，才在页面顶部弹出 Toast 提示并打印到控制台。

### 全局可视化/日志汇聚（从源头保证留痕）
- 开始监控时，UI 将通过 `app.automation.input.common.set_visual_sink()` 与 `set_log_sink()` 注册全局回调；
- 任何使用 `editor_capture.ocr_recognize_region` 或 `editor_capture.match_template` 的识别行为，都会自动在监控面板上推送“带叠加的截图”并写入文本日志，无需开发者额外调用；
- 停止监控时通过 `clear_visual_sink()/clear_log_sink()` 清除接收器。
- 执行入口支持懒加载回退：当 `detail_info` 暂不包含 `graph_data` 时，会优先使用右侧预览上下文中已加载的 `graph_data` 作为执行输入；若仍缺失则进行提示而不静默失败。
- `validation_panel.py`：验证面板（独立页面）

### 设置对话框（SettingsDialog）
- 入口：主窗口工具栏“⚙️ 设置”。
- 现支持修改以下与执行相关的选项（立即生效并写入 `user_settings.json`）：
  - “执行步骤方式”：`classic`（经典，不复位）/`hybrid`（瞬移-复位，平滑拖拽）。
  - “混合模式参数”：步数与步间隔（秒）。
  - "拖拽策略"：`auto`（跟随执行步骤方式）/`instant`（瞬移到终点）/`stepped`（分段步进）。
  - 任务清单生成模式与合并连线、自动保存等。
  - 缓存管理：提供"清除所有缓存"按钮，清空内存缓存并删除（默认）`app/runtime/cache/graph_cache/` 下的节点图持久化缓存文件。
  - 设置页的下拉框与数值框默认忽略滚轮，需点击展开或聚焦后才允许滚轮更改，避免误触。
  - 提供“数据节点跨块复制”开关：控制在“分块/块内放置”阶段是否将跨块共享的数据链复制到后续块（仅复制纯数据节点，遇到流程口停止）。关闭时回退为“先到先得”归属。

### 模式切换与编辑器打开
- 当需要从任务清单或图库打开节点图进行编辑时，控制器发出 `GraphEditorController.switch_to_editor_requested`；主窗口通过 `_on_mode_changed("graph_editor")` 统一切换模式，确保：
  - 中央区切换到“节点图编辑器”
  - 右侧面板（图属性/复合面板/设置）按 `ViewMode` 规则同步增删
  - 避免仅改 `central_stack` 索引导致的右侧面板未刷新
  - 调试输出：关键路径包含日志标识 `[TODO-EDIT]`（任务清单发起）、`[MAIN]`（主窗口接收请求）、`[EDITOR]`（编辑控制器处理），便于排查切换链路
  - 状态快照：`[MODE-STATE]` 行输出左侧导航当前模式、中央栈当前索引/是否为编辑器视图、右侧面板当前标签与所有标签列表
  - 在进入 `GRAPH_EDITOR` 时，右侧会插入并选中“图属性”标签；在图数据加载完成后（`graph_loaded`）会再次同步调用 `GraphPropertyPanel.set_graph(current_graph_id)`，确保属性面板显示真实数据

### 任务清单运行时状态展示
- 叶子步骤在执行后展示运行时状态：
  - 完成：勾选并置灰（删除线）
  - 失败：红色文本并显示错误标记
  - 跳过：黄色警告标记，鼠标悬停显示原因（例如：连线端点在当前视口无法同屏）

## 面向开发者的要点

### 依赖与耦合
- 依赖 `engine` 提供的模型/资源/图代码 API（例如 `GraphModel`、`validate_graph` 等）
- 所有导入置于文件开头，类型提示循环依赖用 `TYPE_CHECKING`
- 禁止延迟导入；保持 import 顺序（标准库→第三方→本地）
  - 性能例外：`graph_view.py` 的自动排版点击处理内按需导入 `engine.graph_code.validate_graph` 与 `engine.layout.LayoutService`，用于降低主窗口启动时的初始化开销。
 - 资源访问：统一使用 `engine.resources.*`（`PackageView/GlobalResourceView/UnclassifiedResourceView/GraphReferenceTracker`）。
- 执行监控的截图能力通过 `app.automation.AutomationFacade.capture_window()` 获取，避免 UI 层直接耦合内部 `editor_capture` 实现；区域计算仍复用 `editor_capture.get_region_rect()`。
- 节点库访问统一：UI 层如需节点定义，统一通过 `engine.nodes.node_registry.get_node_registry(workspace).get_library()` 获取；不要直接在 UI 中调用 `load_all_nodes`，以避免与核心缓存/索引分叉。
 - 端口规则统一入口（避免重复实现）：
   - 范围/变参端口：使用 `engine.nodes.port_name_rules.infer_port_type_from_declared_and_dynamic()` 与 `engine.nodes.port_index_mapper.map_port_index_to_name()`；
   - 流程端口判定：使用 `engine.nodes.port_type_system.is_flow_port_with_context()`；
   - 端口可连性：使用 `engine.nodes.port_type_system.can_connect_ports()`；
   - 端口类型配色：使用 `engine.nodes.port_type_system.get_port_type_color()`。

### 线程与性能
- **主线程约束**：所有 UI 更新在 GUI 主线程执行
- 耗时操作交由后台逻辑完成，仅以信号刷新 UI
 - 执行监控面板提供线程安全接口：日志、状态、进度、可视化更新(`update_visual(image, overlays)`)均通过信号更新
 - 执行动作在后台线程中进行，线程对象由任务清单组件持有（避免线程运行中对象被销毁）
 - 监控画面以执行过程产生的真实视觉产物为唯一来源（截图+OCR/识别叠加），不再轮询用户桌面
 - OCR 模块在程序启动阶段即完成加载，不在监控阶段做预热或额外初始化

### 执行子系统（execution/）

执行相关文件统一收拢在 `ui/execution/` 子包，集中管理执行驱动器、执行线程、执行计划器、执行指引、策略类与监控面板。

#### 目录结构

```
ui/execution/
├── runner.py           # 执行驱动器
├── thread.py           # 执行线程
├── planner.py          # 执行计划器
├── guides.py           # 执行指引
├── strategies/         # 策略类子模块
│   ├── anchor_selector.py
│   ├── execution_coordinator.py
│   ├── retry_handler.py
│   ├── step_skip_checker.py
│   └── step_summary_builder.py
└── monitor/            # 执行监控面板子模块
```

#### 职责分离架构
执行主流程由 5 个独立策略类组合完成：
- `AnchorSelector`: 锚点选择器，多层退化策略（创建 → 连接 → 合并连接 → 参数配置）
- `StepSummaryBuilder`: 步骤汇总构建器，生成可读摘要文本
- `ExecutionCoordinator`: 执行协调器，管理缩放确认、快速映射、锚点校准、单步验证
- `StepSkipChecker`: 跳过检查器，节点可见性与距离检查、端点可见性确保
- `RetryHandler`: 回退处理器，以最近成功锚点为基准重试失败步骤

#### 设计原则
- **执行阶段划分**：`run()` 方法清晰划分为 7 个阶段，每个阶段职责单一、可测试
- **状态管理**：锚点记录、重试状态等封装在对应策略对象内，避免线程生命周期/取消/状态回填的边界问题
- **结果封装**：使用明确的结果类（AnchorInfo、SkipDecision、RetryResult）传递状态
- **扩展性**：如需新增执行策略，可新建独立策略类并在 `thread.py` 中组合使用

#### 导入示例
```python
# 主要执行类
from app.ui.execution import ExecutionRunner, ExecutionPlanner

# 策略类
from app.ui.execution.strategies import AnchorSelector, RetryHandler

# 监控面板
from app.ui.execution.monitor import ExecutionMonitorPanel
```

详见 `ui/execution/claude.md`

### 主题系统与全局样式
- 全局样式注入：程序启动时由 `ThemeManager.apply_app_style(app)` 统一注入字体与基础 QSS（按钮/输入/树/列表/表格/滚动条/标签页/分组框/对话框）。
- 组件样式来源：主题 token/QSS 工厂集中在 `app.ui.foundation.theme.*`，`StyleMixin` 位于 `app.ui.foundation.style_mixins`，请优先通过混入或 `ThemeManager.*_style()` 获取样式，避免在组件内分散 `setStyleSheet` 的硬编码。
- 默认字体：应用级默认字体由 `ThemeManager.apply_app_style(app)` + `app.ui.foundation.fonts` 统一按平台选择并做替换兜底（Windows: `Microsoft YaHei UI`；macOS: `PingFang SC`；等宽：Windows: `Consolas`；macOS: `SF Mono`/`Menlo`）。局部强调请仅调整字号/粗细，尽量复用 `Colors` 配色常量。

#### 右键菜单与语义样式规范（统一入口）
- 右键菜单风格：统一使用 `ThemeManager.context_menu_style()`（白底、深色字、浅蓝选中，高对比分隔线）；不要内联手写 QSS。
- 菜单构建：统一通过 `app.ui.foundation.context_menu_builder.ContextMenuBuilder` 创建菜单与动作；标准动作使用 `StandardAction`（重命名/删除/定位/编辑/打开变量/查看引用）。
- 文本语义样式：成功/错误等状态文本请使用 `ThemeManager.semantic_success()` / `ThemeManager.semantic_error()`；标题字号使用 `ThemeManager.heading(level)`。
- 自绘组件与 QGraphicsItem（如节点预览、动态端口按钮等）的颜色同样应优先通过 `ThemeManager.Colors` 获取，在 `paint()` 中使用 `QtGapp.ui.QColor(Colors.PRIMARY)` 等方式替代直接写死 `QColor("#xxxxxx")`，以便在浅色/深色主题切换时自动跟随 token 调整。

#### 分割线与边框统一规则
- 分割线以 `QSplitter::handle` 的 1px 线为唯一视觉分隔，不再叠加容器左/右侧边框。
- 右侧面板 `QTabWidget` 去除左边框（`objectName="sideTab"`，由 `ThemeManager.right_side_tab_style()` 提供），避免与分割线组合成“双线”。
- 页面内部卡片/分组如需边框，请避免与外层分割缝相邻的一侧再绘制边框（例如：靠近分割线的一侧不画边框）。

#### 工具栏与“新建”按钮行规范
- 工具栏行一律使用 `QHBoxLayout` 并通过 `app.ui.foundation.toolbar_utils.apply_standard_toolbar()` 统一：左对齐、边距 0、间距 `Sizes.SPACING_SMALL`。
- 含搜索/排序等输入控件的工具栏：按钮组在左，`addStretch()` 将搜索/筛选控件推到右侧，保持跨页面一致的视觉位置。
- 建议按钮顺序：新建/添加 → 删除/编辑 → 其他操作 →（伸展）→ 搜索/排序。

#### 库页面复用规范
- 适用范围：`graph_library_widget.py` / `template_library_widget.py` / `entity_placement_widget.py` / `combat_presets_widget.py` 等“库/列表”类页面。
- 统一基元位于 `ui/graph/library_mixins.py`：
  - `SearchFilterMixin`：标准化搜索输入框绑定与占位文案。建议使用 `connect_search(search_edit, on_text_changed, placeholder)`。
  - `SearchFilterMixin` 提供通用过滤 API：
    - `filter_list_items(QListWidget, query, text_getter?)`：统一列表项过滤（不区分大小写）。
    - `filter_table_rows_by_columns(QTableWidget, query, columns)`：统一表格行过滤（按指定列）。
    - `filter_card_map(mapping, query, match_fn)`：统一卡片可见性切换（自定义匹配逻辑）。
  - `SelectionAndScrollMixin`：统一“选中并滚动到可见区域”。卡片容器用 `scroll_to_widget(QScrollArea, widget, center=True)`；列表/树/表格分别用 `select_and_center_*` 系列方法。
  - `ToolbarMixin`：与 `apply_standard_toolbar()` 配套，提供 `init_toolbar(layout)` 与 `setup_toolbar_with_search(layout, buttons, search_edit)` 的装配辅助。
  - `ConfirmDialogMixin`：`confirm()/show_warning()/show_info()` 统一确认与提示对话框。
- 约定：
  - 搜索行为保持“不区分大小写”的语义，页面侧的过滤逻辑仅关心业务字段匹配，不做 UI 状态改动。
  - 滚动行为默认居中（`PositionAtCenter` / `center=True`），避免跨页面出现不同的定位体验。
  - 工具栏按钮仍由页面决定具体顺序与可见性；布局与搜索输入的放置遵循上节规范。

#### 交互规范补充
- 右键菜单：统一使用 `ui/context_menu_builder.ContextMenuBuilder` 构建与显示，确保主题样式、分隔线、禁用态与快捷键一致。
- 对话框：阻塞确认与提示优先使用 `app.ui.graph.library_mixins.ConfirmDialogMixin` 的 `confirm()/show_warning()/show_info()`；非阻塞提示使用 `ToastNotification.show_message()`（如需）；新建列表/表单式编辑对话框应优先继承 `BaseDialog` / `FormDialog`，管理概览/“管理器”类对话框应优先继承 `ManagementDialogBase`，避免直接从 `QDialog` 手写 header/footer。
- 滚轮缩放：
  - `QGraphicsView` 使用 `ui/interaction_helpers.handle_wheel_zoom_for_view()`；
  - `QScrollArea`+内容缩放场景使用 `ui/interaction_helpers.handle_wheel_zoom_for_scroll_area()`，保持“以鼠标为锚点”的体验与统一的最小/最大比例与步进。
  - 节点图编辑视图（`GraphView`）将最小缩放下限设为 `min_scale=0.02`，以便在大图场景下能缩小到全图可见；其他使用方可按需覆盖默认下限（函数默认仍为 0.2）。

#### 三态复选框与 CheckState 约定
- 所有 `setCheckState`/`checkState` 相关 API（例如 `QTreeWidgetItem.setCheckState`、`QListWidgetItem.setCheckState`）必须使用 `Qt.CheckState` 枚举；禁止传入 `int` 或 `*.value`。统一使用 `Qt.CheckState.Unchecked/PartiallyChecked/Checked`。
- 父级/容器型树项在 PyQt6 下使用 `Qt.ItemFlag.ItemIsAutoTristate` 启用三态（自动根据子项呈现部分勾选），避免使用不存在的 `ItemIsTristate`。
- 父子联动与进度展示通过 `tree_check_helpers.apply_parent_progress()` 等方法计算并写入父项的 `CheckState`，与自动三态不冲突。

#### Qt6 枚举与 ItemFlag 使用约定
- 判断标志请使用按位与或 `QFlags.testFlag()`：例如 `if flags & Qt.ItemFlag.ItemIsUserCheckable:`；不要对枚举/Flags 进行 `int()` 强制转换。
- 设置/清除标志请使用按位运算：
  - 设置：`item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)`
  - 清除：`item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)`
  - 组合：保持 `ItemIsEnabled` 基础标志不被意外清除。

### 执行监控面板（execution/monitor/）
执行监控面板采用职责分层架构：面板本体仅负责 UI 组装与委托调用，识别、日志、预览与控制等功能由独立子模块实现。

#### 子包结构（9 个模块）
- `panel.py`：ExecutionMonitorPanel 本体（~379 行），胶水层，组装 UI、委托动作、信号转发
- `visual_overlays.py`：纯绘制函数（矩形/圆/文字布局/标题横幅），输入输出保持 dict 结构
- `preview_dialog.py`：截图历史预览对话框（左侧缩略图+右侧大图，支持滚轮缩放/拖拽/键盘切换）
- `actions_recognition.py`：一次性识别测试动作（检查页面/OCR/节点/端口/模板匹配），回调驱动
- `focus_controller.py`：定位镜头（识别+几何拟合+视口对齐），成功后发射 `recognition_focus_succeeded` 信号
- `log_view.py`：日志视图控制器（LogViewController），负责日志记录/筛选/搜索/HTML渲染/步骤上下文
- `panel_app.ui.py`：面板 UI 组装与样式，提供一次性构建函数
- `visual_renderer.py`：可视化渲染器（图片渲染、历史维护、双击放大）
- `screenshot_worker.py`：截图线程与抓取管理
- `execution_control.py`：执行控制与单步模式（暂停/继续/终止）

#### 委托模式
- 面板构造时初始化 6 个委托：`RecognitionActions`、`FocusController`、`LogViewController`、`VisualRenderer`、`ScreenshotCaptureManager`、`ExecutionControl`
- 按钮点击事件直接调用委托方法（如 `self._actions.check_current_page()`），不再在面板内实现业务逻辑
- 属性访问委托：`is_running` / `is_paused` / `step_mode_enabled` 通过 @property 委托到 `ExecutionControl`
- 导入路径：推荐使用 `from app.ui.execution.monitor import ExecutionMonitorPanel` 或 `from app.ui.execution import ExecutionMonitorPanel`（通过 `__init__.py` 重新导出）

#### 拆分细节
- 已消除重复测试方法定义（如 `_on_test_ocr_clicked` 等），统一实现
- 线程边界保持不变：测试与定位通过传入的回调在 UI 线程落图
- 保持 overlays 的 dict 结构，不引入 dataclass，避免放大改动面
- 对外 API（信号、start_monitoring/stop_monitoring/log/update_visual/wait_if_paused/is_execution_allowed 等）统一由面板暴露，保持稳定
- 日志搜索始终不区分大小写（不提供“区分大小写”开关）
- 详见 `ui/execution/monitor/claude.md`

### 节点图保存统一架构
**核心原则：单一入口，零fallback，明确分工**

#### 保存路径
1. **节点图**：通过 `GraphEditorController.save_current_graph()`
   - 资源库节点图（server/client文件夹）
   - 节点图库管理的所有节点图

2. **模板/实例节点图**：通过 `GraphEditorController.save_current_graph()` → 自动同步到容器 → `PackageController.save_package()`
   - 模板的 `default_graphs`
   - 实例的 `additional_graphs`

3. **复合节点**：独立保存路径 `CompositeNodeManager.update_composite_node()`