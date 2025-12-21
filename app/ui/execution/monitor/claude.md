# 执行监控子包（execution/monitor/）

## 目录用途
执行监控面板采用职责分层架构：面板本体仅负责 UI 组装与委托调用，识别、日志、历史预览与执行控制逻辑拆分为独立模块，由本子包统一管理。

## 当前状态

## 模块职责

### panel.py（~379 行，胶水层）
ExecutionMonitorPanel 本体，仅负责组装与委托：
- UI 组装：通过 `panel_ui.build_monitor_ui(self)` 构建所有控件
- 委托初始化：构造时创建 `RecognitionActions`、`FocusController`、`LogViewController`、`VisualRenderer`、`ScreenshotCaptureManager`、`ExecutionControl`
- 信号转发：接收外部调用（start_monitoring/stop_monitoring/log/update_visual），通过信号线程安全更新 UI
- 按钮绑定：通过 `_connect_ui_signals()` 统一连接控件信号到委托方法（控制按钮由 `ExecutionControl` 内部处理）
- 步骤上下文注入：对外 API（`set_current_step_context` / `set_current_step_tokens`），委托给 `LogViewController`
- 可视化渲染：委托给 `VisualRenderer.render_visual()`
- 属性访问：`is_running` / `is_paused` / `step_mode_enabled` 委托到 `ExecutionControl` 的同名属性（通过 @property）
- 外部 API 保持不变：start_monitoring/stop_monitoring/log/update_status/update_progress/wait_if_paused/is_execution_allowed/is_step_mode_enabled
- 精简模式：面板顶部“精简/完整”开关可隐藏截图/测试/拖拽/筛选/事件表，并联动主窗口收起左侧导航栏、缩小窗口与分栏比例；**不隐藏任务清单区域**，保证步骤树与执行入口仍可用
  - 执行入口集中：精简模式下监控面板会显示“执行/执行剩余”按钮，任务清单右侧详情/预览会被收起以释放空间
  - 分栏收敛：精简模式会将主窗口 `main_splitter` 切换为 **上下布局**（上：任务清单步骤树；下：执行监控日志），并临时调整拉伸权重与 handle 宽度；同时临时将 `central_stack` 的 sizePolicy 设为 Ignored，避免 QStackedWidget 以“所有页面最大 sizeHint/minSizeHint”限制最小宽度/高度而产生空白占位
- 自动缩窗：进入精简模式会自动**收缩窗口宽度**到“刚好够放得下步骤树”的程度（基于 `QTreeWidget.sizeHintForColumn(0)` 推导列宽），高度保持不变；为避免底部日志区被按钮行撑宽，精简模式会进一步隐藏暂停/继续/下一步控件，仅保留执行入口与终止按钮

### visual_overlays.py（~190 行）
纯绘制函数，负责在 QPixmap 上叠加可视化元素（节点框/端口圆/OCR区域等）：
- `_draw_overlays_on_pixmap(pixmap, overlays)`：主入口，先绘制矩形/圆形，再绘制“框→文字”的箭头和标签文本
- `_draw_header_banner(pixmap, text)`：左上角标题横幅（半透明黑底白字）
- `_draw_shape_outlines(painter, overlays)`：绘制矩形与圆形（边框）
- `_draw_labels_for_overlays(painter, overlays, occupied, image_bounds)`：为每个矩形/圆形绘制标签文本，并通过箭头明确从对应框指向对应文字
- `_place_label_around_anchor(...)`：标签智能放置（八个候选位置，优先避免与节点框/端口圈及已有标签重叠）
- `_find_non_overlapping_fallback(...)`：当常规候选都被占用时，以扩圈方式在画面内寻找不与框/文字冲突的备选位置
- `_draw_arrow_between_rects(...)`：在锚点矩形与文字矩形之间绘制带箭头的连线，起止点都落在各自矩形的边中点，避免穿过内部
- `_draw_text_with_outline(painter, pos, text)`：带黑色描边的白字，保证在复杂截图上仍可读
- 输入输出保持 dict 结构：`{ 'rects': [...], 'circles': [...] }`，不引入 dataclass
- 小工具：`_rect_intersects_any` / `_grow_rect` / `_clamp_rect_to_bounds` / `_make_qcolor`
- 文本避让仅针对节点/端口等识别框以及圆形点击提示等小型标注框；`节点图布置区域`、`节点图缩放区域`、`Warning 搜索区域` 等用于提示范围的巨型区域框不会被加入避让障碍，标签可以落在这些区域内部。

### preview_dialog.py（~220 行）
截图历史预览对话框，非模态，支持左侧缩略图列表+右侧大图：
- `_ImageHistoryPreviewDialog`：接收 `images`（QPixmap 列表）、`start_index`、`titles`
- 统一对话框样式：继承 `BaseDialog` 并隐藏底部按钮栏，确保与主应用字体/控件/滚动条一致
- 交互：
  - 滚轮缩放（以鼠标为锚点）
  - 左键拖拽平移
  - 键盘左右/A/D 切换图片
  - 自动适配视口尺寸（延迟一帧再做二次自适应，避免初始化阶段视口过小）
- 缩略图：左侧列表，图标模式，160x90，点击切换
- 大图：右侧 QScrollArea + QLabel，支持按视口自适应初始缩放

### actions_recognition.py（~350 行）
一次性识别测试动作集合，回调驱动，不直接持有 UI 状态：
- `RecognitionActions` 类，接受回调：
  - `log_callback`：日志输出
  - `update_visual_callback`：可视化更新（截图+叠加）
  - `get_graph_model_callback`：获取当前图模型（用于比对识别结果）
  - `get_workspace_path_callback`：获取工作区路径（创建执行器）
  - `get_window_title_callback`：获取目标窗口标题（截图）
- 方法：
  - `check_current_page()`：检查当前页面（截图→识别节点/端口→叠加→比对模型）
  - `test_ocr()`：对顶部标签栏执行 OCR
  - `test_settings()`：Settings 按钮行识别（优先基于当前图扫描，无模型时回退全局检测），会统计并输出扫描节点数与命中 Settings 行数
  - `test_warning()`：Warning.png 模板匹配
  - `test_ocr_zoom()`：识别节点图缩放区域（期望 50% 等百分比文本）
  - `test_nodes()`：节点识别（叠加矩形与中文标题；若 `list_nodes` 去重抑制了节点，会以红框标注原始矩形，标签包含“被抑制”提示、触发抑制的目标框、IoU/包含率/中心距等具体指标）
  - `test_ports()`：端口识别（为每个检测到的节点列出最终端口结果，按 kind/side/index 标注并叠加显示置信度百分比；同时用红框标注端口识别跳过的节点顶部区域，排除高度来自 `app.automation.vision.get_port_recognition_header_height_px()`）。
  - `test_ports_deep()`：深度端口识别（基于一步式识别模板匹配结果，展示置信度≥70%的模板命中；包括在 NMS 与同行去重阶段被抑制的候选，在标签文本中追加“因NMS重叠被排除 / 因同行去重被排除”等原因说明，并对因 NMS 重叠被抑制的候选在同一模板、同一目标框分组内仅展示置信度最高的一条，同时在标签中显示与其发生重叠的保留命中及 IoU 折算后的重叠率）；端口标题栏排除高度与运行时保持一致（使用 `app.automation.vision.get_port_recognition_header_height_px()`），并在画面上用红框标注被排除区域。
  - `test_settings_tpl()`：Settings.png 模板匹配
  - `test_add_templates()`：Add.png / Add_Multi.png 模板匹配
  - `test_searchbar_templates()`：search.png / search2.png 模板匹配
  - `test_window_capture_strict()`：仅窗口截图测试，调用基于 PrintWindow 的截图接口抓取一帧，用于验证在有遮挡场景下仍能获得完整窗口图像
- 节点识别测试会在 `list_nodes` 去重导致原始节点数量与最终展示数量不符时追加日志，并在画面叠加红框显示被抑制的原始矩形（含原因指标），直接对应日志内容，便于定位差异；深度端口识别在端口模板层级以类似方式展示被抑制候选，并在日志中给出少量摘要示例。
- `_on_test_ocr_clicked` / `_on_test_settings_clicked` / `_on_test_warning_clicked` 等测试入口已统一到单一实现，避免重复代码

### focus_controller.py（~80 行）
"定位镜头"识别与视口对齐，回调驱动，并与执行线程共享同一份既是执行器又实现 `ViewportController` 协议的实例：
- 调试落盘：每次成功定位后会将可见节点识别结果写入运行时缓存根目录下的 `debug/last_focus_recognition.json`（默认 `app/runtime/cache/debug/`），仅用于离线分析，不参与运行时逻辑；落盘统一通过 `app.runtime.services.json_cache_service.JsonCacheService`，避免本模块自行拼路径与手写 JSON 写入。
- `FocusController` 类，接受回调：
  - `log_callback`：日志输出
  - `update_visual_callback`：可视化更新
  - `get_graph_model_callback`：获取当前图模型
  - `get_workspace_path_callback`：获取工作区路径
  - `get_graph_view_callback`：获取 GraphView（用于视口对齐）
  - `on_focus_succeeded_callback`：识别成功后发射信号（传入可见节点 ID 列表）
  - `get_shared_executor_callback` / `set_shared_executor_callback`：从监控面板获取/写回共享的 `EditorExecutor`，使“执行线程中的执行器实例”和“本控制器视口控制器视角下的实例”保持为同一对象，共享同一套视口状态与识别缓存
- 方法：
  - `match_and_focus()`：主入口
    1. 检查当前图与工作区路径
    2. 优先复用监控面板中的共享执行器（工作区一致时），否则按需创建新的 `EditorExecutor`
    3. 确保画布缩放为 50%（`EditorExecutor.ensure_zoom_ratio_50`）
    4. 识别与几何拟合（`verify_and_update_view_mapping_by_recognition`，三阶段：唯一锚点→普通锚点→普通节点兜底），仅在成功后才将执行器标记为“可用于拖拽/定位”并写回共享入口
    5. 利用检测结果同步当前可见节点的程序坐标（`sync_visible_nodes_positions`），避免坐标陈旧导致后续可见性判断失真
    6. 获取编辑器视口矩形（程序坐标，`ViewportController.get_program_viewport_rect`）
    7. 视图聚焦（`GraphView._execute_focus_on_rect` 或 `centerOn`）
    8. 识别当前可见节点（`recognize_visible_nodes`），在最新坐标系下统计哪些节点真正“在画面中”
    9. 在监控截图上为所有可见节点绘制矩形并标注“节点名（节点ID）”，并在可获取到 OCR 原始标题时附加 `OCR:原始→纠错后/识别后`，用于定位“错别字纠错是否生效”等问题；覆盖层通过 `update_visual_callback` 推送到面板
    10. 发射 `recognition_focus_succeeded` 信号
- 日志：输出缩放检查、识别拟合、视口矩形、可见节点名称与 X 范围（调试用）
- `ensure_point_visible(program_x, program_y)`：供右侧“拖拽测试”控件调用，复用执行步骤中的视口对齐逻辑；在每次拖拽测试前后都会记录编辑器视口在程序坐标系中的矩形，便于对比平移效果；调用前会显式检查是否已建立有效的坐标映射（`scale_ratio` / `origin_node_pos` 非空），若尚未成功定位则输出友好提示而非抛出异常；内部通过 `ViewportController.ensure_program_point_visible` 驱动视口平移，不再直接访问执行器的下划线私有方法。
- **性能优化**：可见节点统计会自动复用视口拟合阶段的识别结果（底层缓存机制），避免在画面未变时重复执行场景识别，显著减少重复的调试输出

### log_view.py（~450 行）
日志视图控制器（LogViewController），负责日志记录/筛选/搜索/HTML渲染/步骤上下文：
- 构造参数：`log_text_browser`（QTextBrowser）、`search_input`（QLineEdit）、`filter_combo`（QComboBox）
- 日志数据管理：
  - `_log_records`：日志记录列表（包含时间戳/消息/分类/成功失败标志/步骤上下文）
  - `_log_filter_text`：搜索文本
  - `_log_filter_type`：筛选类型（"全部"/"仅点击"/"仅OCR"等）
  - `_log_case_sensitive`：固定为 False（始终不区分大小写）
- 步骤上下文管理：
  - `_current_step_title`、`_current_parent_title`、`_current_step_id`
  - `_current_step_tokens_html`：分段富文本（可点击锚点）
  - `_current_step_tokens_plain`：纯文本（用于标题回退）
- 主要方法：
  - `append(message, context_tokens_html, parent_title, step_title, step_id)`：追加日志并显示
  - `clear()`：清空日志
  - `set_filter_type(filter_type)`：设置筛选类型并重建视图
  - `set_filter_text(text)`：设置搜索文本并重建视图
  - `rebuild_view()`：根据当前筛选条件重建日志显示
  - `set_current_step_context(step_title, parent_title)`：设置当前步骤上下文
  - `set_current_step_tokens(step_id, tokens)`：设置分段富文本锚点
  - `get_current_display_title()`：获取当前可显示标题（优先步骤名，回退 tokens）
  - `on_anchor_clicked(url)`：处理锚点点击，返回 todo_id
- 日志分类（`_classify_log_message`）：根据消息内容自动分类为 step/connect/drag/click/mouse/recognize/ocr/screenshot/wait/create/config/retry/calibrate/viewport/other
- HTML 渲染（`_format_log_html`）：带左侧色条、徽标、时间戳、成功/失败色、行首上下文（可点击锚点）
- 筛选匹配（`_record_matches_current_filter`）：类型筛选 + 文本搜索（不区分大小写）
- 锚点生成（`_tokens_to_anchor_html`）：将分段 tokens 转为可点击的 `<a href='todo:...'>`
- 信号自动连接：`search_input.textChanged` → `_on_search_text_changed`；`filter_combo.currentIndexChanged` → `_on_filter_changed`
- 滚动策略：日志追加与重建视图后不再同步滚动到底部，而是通过 `QTimer.singleShot(0)` 做 debounce（同一轮事件循环最多滚动一次），降低 UI 重入风险。

### panel_ui.py（~300 行）
面板 UI 组装与样式，提供一次性构建函数：
- `AspectRatioLabel`：保持 16:9 宽高比的 QLabel 子类，用于截图显示区域；通过 `heightForWidth()` 方法根据宽度自动计算高度
- `build_monitor_ui(parent)`：构建执行监控面板的所有 UI 控件，返回控件引用字典
  - 返回字典包含所有控件：status_label、progress_label、step_context_label、screenshot_label、各按钮、log_text 等
  - 精简模式开关：`compact_mode_button`（QPushButton，checkable），由面板本体连接并驱动 UI 收敛与主窗口小窗化
  - 精简模式执行入口：`execute_button` / `execute_remaining_button`（仅在精简模式下显示），由任务清单编排层监听并路由到执行桥
  - 布局：VBoxLayout 包含状态行、步骤上下文、截图区域与滚动容器
    - 截图区域（`screenshot_label`）：位于滚动区域外部（主布局中），始终可见，不会被控制区/测试区/拖拽测试区等控件挡住；使用 `AspectRatioLabel` 保持 16:9 宽高比
    - 滚动容器（`monitorScrollArea`）：将控制区/测试区/拖拽测试区/日志筛选/日志分割区放入滚动区域，避免这些工具控件挤压截图画面；日志正文 QTextBrowser 仍保留自身滚动条用于长日志快速滚动
    - 控制区：分组 + Grid，每行不超过 3 个主要按钮，减少窄宽度截字
    - 测试区：不在面板内展开，改为"测试工具"菜单按钮弹出 QMenu，避免测试入口数量影响窗口最小尺寸
    - 日志筛选：搜索与筛选拆两行（搜索行优先保证输入框可见）
    - 日志分割区：`log_splitter`（执行事件表格 + 日志正文）允许子项折叠，子控件最小高度为 0，便于小窗场景压缩高度
  - 注意：`QSplitter.setCollapsible(index, ...)` 需在 `addWidget(...)` 之后调用，否则 Qt 会输出 `QSplitter::setCollapsible: Index X out of range` 警告
  - 文案与样式：按钮使用 `kind` 动态属性区分 `primary/secondary/danger`；对 disabled 状态提供统一置灰样式，保证按钮仅在实际可用时呈现"正常颜色"
  - 初始按钮状态：暂停/继续/下一步/终止默认禁用
  - 截图区域：位于主布局中（非滚动区域），使用 `AspectRatioLabel` 保持 16:9 宽高比；由渲染器按当前尺寸缩放绘制。
- `_apply_compact_controls_style(parent)`：应用紧凑化控件样式（按钮 font-size:11px、padding:2px 8px；复选框 font-size:11px）
- 日志文本：日志正文 QTextBrowser 使用等宽字体（通过 `app.ui.foundation.fonts` 统一选择），避免硬编码 `Consolas` 等平台字体名。
- 不包含信号连接：信号连接由面板在 `_connect_ui_signals()` 中统一处理
- 控件 tooltip：为每个测试按钮提供详细说明（例如："对顶部标签栏或指定区域执行一次 OCR，并在监控面板叠加展示识别结果"）

## 导入路径

**推荐导入方式：**
```python
from app.ui.execution.monitor import ExecutionMonitorPanel
```

**兼容性导入（通过父包重新导出）：**
```python
from app.ui.execution import ExecutionMonitorPanel
```

## 注意事项

### 线程安全
- 所有测试动作与定位逻辑在调用线程执行，通过传入的 `update_visual_callback` 在 UI 线程落图
- 面板的 `update_visual(base_image, overlays)` 方法内部判断线程，若非 UI 线程则通过信号转发

### overlays 结构
保持 dict 格式，不引入 dataclass：
```python
{
  'rects': [ { 'bbox': (x,y,w,h), 'color': (r,g,b), 'label': str }, ... ],
  'circles': [ { 'center': (x,y), 'radius': int, 'color': (r,g,b), 'label': str }, ... ],
  'header': str  # 可选，左上角标题
}
```

### 回调驱动
- RecognitionActions 与 FocusController 不直接依赖面板状态，所有上下文通过回调访问
- 便于后续测试与复用（例如：在非 UI 环境或命令行工具中使用识别动作）
- 监控面板相关颜色（日志左侧色条、徽章背景/前景、执行事件表格前景/背景、截图边框与步骤上下文文字等）统一通过 `ThemeManager.Colors` 获取，避免在本子包中直接写死十六进制颜色值或 `QColor("#xxxxxx")`，以保证浅色/深色主题切换时视觉保持一致。

### visual_renderer.py（~190 行）
可视化渲染器，负责图片渲染、历史维护、双击放大：
- `VisualRenderer` 类继承自 `QtCore.QObject`（必须继承自 QObject 以支持事件过滤），接受参数：
  - `screenshot_label`：截图显示控件（QLabel）
  - `parent_widget`：父部件（用于对话框父级，也作为 QObject 的 parent）
  - `get_current_display_title_callback`：获取当前显示标题的回调（执行步骤名/子步骤 tokens 文本）
  - `get_current_micro_action_callback`：获取微动作标题的回调（最近一条细粒度日志）
- 主要方法：
  - `render_visual(base_image, overlays)`：渲染可视化产物到截图标签
  - `render_visual_snapshot(base_image, overlays)`：一次性可视化（用于"检查页面"等即时测试）
  - `clear_history()`：清空历史记录（开启新监控会话时调用）
  - `backfill_recent_empty_titles()`：将末尾连续的空标题历史项回填为当前可显示标题
  - `eventFilter(obj, event)`：处理双击放大预览事件
- 缩放自适应：监听 `screenshot_label` 的 `Resize` 事件，基于 `_last_full_pixmap` 重新按当前控件尺寸缩放，避免用户拖拽缩窄监控面板时画面被裁剪
  - 拖拽过程中采用 `FastTransformation` 保证跟手；停止拖拽后 debounce 补一次 `SmoothTransformation`，兼顾性能与清晰度
- 状态维护：
  - `_last_full_pixmap`：最近一次的完整画面（用于放大预览）
  - `_current_run_images`：当前运行期的截图历史（原始尺寸，已叠加绘制）
  - `_current_run_titles`：对应的标题列表
  - `_history_max_images`：历史记录上限（默认 200）
- 标题策略：
  - 执行过程中：始终以“当前执行步骤标题”为主，必要时追加更细粒度的子动作或测试标题（例如 `步骤名 · OCR: ...`）
  - 仅测试/调试场景（无步骤上下文但 overlays.header/title 存在）时，直接使用叠加层标题
- 线程语义不变：渲染在 UI 线程执行，由面板通过信号保证线程安全

### screenshot_worker.py（~80 行）
截图线程与抓取管理：
- `ScreenshotWorker`：后台截图线程（QThread），周期性抓取外部编辑器窗口截图
  - 构造参数：`window_title`（目标窗口标题）、`interval_ms`（截图间隔）
  - 信号：`screenshot_ready(PIL.Image.Image)`：截图就绪
  - 方法：`run()`（线程主循环）、`stop()`（停止线程）
- `ScreenshotCaptureManager`：截图抓取管理器，封装截图线程的启动、停止与信号连接
  - 构造参数：`parent`（父对象）、`screenshot_interval_ms`（截图间隔）
  - 方法：
    - `start_capture(window_title, on_screenshot_ready)`：启动后台截图线程
    - `stop_capture()`：停止后台截图线程
    - `get_window_title()`：获取当前窗口标题
    - `set_window_title(title)`：设置窗口标题（不重启线程）

### execution_control.py（~150 行）
执行控制与单步模式：
- `ExecutionControl` 类（继承 QObject），管理暂停/继续/单步/终止
- 构造参数：`pause_button` / `resume_button` / `next_step_button` / `stop_button`
- 信号：
  - `stop_requested`：停止执行请求
  - `status_changed(str)`：状态更新（用于通知面板更新状态标签）
  - `log_message(str)`：日志消息
- 状态属性：`is_running` / `is_paused` / `step_mode_enabled`
- 主要方法：
  - `start_execution()`：开始执行（更新按钮状态）
  - `stop_execution()`：停止执行（禁用所有控制按钮）
  - `request_pause()`：请求暂停（可从快捷键调用）
  - `wait_if_paused()`：等待（阻塞），直到不再暂停
  - `is_execution_allowed()`：检查是否允许继续执行（未终止）；暂停由 `wait_if_paused()` 负责阻塞，不应把 paused 当作“终止”
  - `is_step_mode_enabled()`：检查是否启用单步模式
- 私有槽：`_on_pause_clicked` / `_on_resume_clicked` / `_on_stop_clicked` / `_on_next_step_clicked`
- 按钮连接：内部自动连接所有控制按钮的信号

## 边界/细节提示
- 测试相关方法统一集中在 `actions_recognition.py` 等子模块中实现，避免在面板本体重复代码
- 文本一致性：所有识别测试的中文提示保持与原实现完全一致
- 线程边界：测试与定位不改变线程调度，仍通过 UI 回调落图
- overlays 不引入 dataclass：保持 dict 结构，避免连锁改动
- 识别缓存失效：`check_current_page` 会调用 `_vision_invalidate()` 清空缓存，确保每次重新识别
- 全局汇聚器清理：`actions_recognition.py` 在调用依赖全局 sink 的 OCR/模板匹配前，会用 `_temporary_global_sinks(...)` 进行临时注册并在 finally 中强制清理，避免异常中断后残留回调导致后续监控输出串台
- 线程语义不变：`update_visual` 在非 UI 线程时通过 pyqtSignal 切回
- 仍保留图片缩放策略：先叠加后整体缩放，避免坐标误差
- 结构化执行事件表格复用 `ThemeManager.table_style()` 并统一调色板，保持与其他表格组件一致的配色与选中效果
- 状态委托：面板通过 @property 将 `is_running` / `is_paused` / `step_mode_enabled` 委托到 `ExecutionControl`，外部仍可直接访问这些属性
- 控制器信号：`ExecutionControl` 通过信号（`stop_requested` / `status_changed` / `log_message`）与面板通信，避免直接调用面板方法
- 快捷暂停统一通过 `ExecutionMonitorPanel.request_pause()` 暴露给外部调用，不再提供额外的兼容别名。

