## 目录用途
`ui/foundation/` 存放与具体业务无关的 UI 基础设施与通用工具模块，例如基础控件、主题与样式管理、交互辅助函数、滚动与视图工具、对话框封装与上下文菜单构建器等。这里的代码不关心“节点图/任务清单/管理面板”等具体页面，只提供可复用的 PyQt6 级别交互与视觉基元。

- 主要类型包括：
  - 基础 Widget 与通用控件封装（对话框、开关按钮等）
  - 主题/颜色/尺寸与样式工具
  - 通用交互辅助方法（滚轮缩放、滚动定位、刷新节流等）
  - Toast 提示、工具栏装配、导航栏等基础 UI 组件
  - 树/列表等结构化控件的通用构建与状态管理工具（如 `folder_tree_helper.py`）
- 文案片段：`info_snippets.py` 提供跨模块复用的标准说明文字（例如节点图变量简介），用于保持不同界面的文案一致性。

## 当前状态
- 主题系统：`theme_manager.py` 负责主题 token 暴露与样式缓存；`ThemeManager` 暴露 `Colors/Sizes/Icons/Gradients/HTMLStyles` 类属性，token 实现在 `theme/tokens/`，QSS/HTML 片段位于 `theme/styles/`，`style_mixins.py` 提供统一样式混入（新代码优先使用 `apply_panel_style` / `apply_form_dialog_style` / `apply_card_style` 三个入口），`canvas_background.py` 专职画布网格绘制；常用组件的样式（如左侧导航按钮、Toast 卡片等）通过 `ThemeManager.navigation_button_style()` / `ThemeManager.toast_style()` 统一暴露，避免在具体 widget 中重复书写 QSS。主题系统支持浅色/深色模式切换：启动时由 `ThemeManager.apply_app_style()` 根据 `settings.UI_THEME_MODE` 与系统配色方案选择实际调色板，并在全局应用对应 QSS。
- 字体选择：`fonts.py` 提供 UI/等宽/emoji 字体族的按平台选择与替换兜底；`ThemeManager.apply_app_style()` 在启动阶段统一注入应用字体。需要显式设置字体时应使用该模块，避免在组件中硬编码 `Microsoft YaHei/Consolas` 等字体族名。
- `style_mixins.py` 的基础样式混入现已覆盖按钮/输入/树/列表/表格/滚动条外，也同时注入下拉框与数值框样式（combo/spin），确保面板内的 QSpinBox/QComboBox 与全局主题一致。
- 画布网格：`canvas_background.draw_grid_background()` 依赖 `ui/graph/graph_palette.py` 中的固定深色调色板（背景 `#1E1E1E`，细网格 `#2A2A2A`，粗网格 `#3A3A3A`），不随主题切换变色，保证节点图画布外观稳定；网格起点使用 floor 对齐，避免负坐标/缩放/平移下出现跳变与错位。
- 基础控件：`base_widgets.py` 提供统一样式的对话框基类（`BaseDialog` / `FormDialog`）以承载表单与列表，同级模块中还包含通用布尔开关等基础输入部件（如带主色渐变轨道的 `ToggleSwitch`），可在各业务面板中直接复用，保证布尔配置项的交互与尺寸规范一致。
- 工具与辅助：滚动/视图工具、刷新门控、节流与全局热键等集中于本目录，供各功能页面调用；`dialog_utils.py` 提供标准化的警告/信息/确认弹窗入口（包含“是/否”确认与“确认+不再提示”两类对话框），并作为多数 UI 组件的唯一 `QMessageBox` 依赖，其他目录不直接实例化 `QMessageBox`；输入对话框统一通过 `app.ui.foundation` 顶层导出的 `prompt_text` / `prompt_item` / `prompt_int` 使用（实现位于 `input_dialogs.py`），避免在业务模块中直接调用 `QInputDialog.get*`。
- 文件夹树工具：`folder_tree_helper.py` 统一封装 `QTreeWidget` 文件夹结构的构建与展开状态记录/恢复，已被节点图库与复合节点管理器复用，避免在不同页面各自实现一套树结构逻辑。
- 导航栏组件：`navigation_bar.py` 统一生成左侧模式按钮，实际渲染顺序保持“功能包→元件库→实体摆放→战斗→管理→复合节点→节点图库→验证→任务清单”，按钮视觉样式依赖主题色与渐变配置并通过主题样式工厂集中管理，确保导航与整体 UI 主题风格一致，同时保证任务清单按钮位于最底部，方便用户完成验证后再进入任务列表。
- ID 生成：`id_generator.py` 统一封装 `generate_prefixed_id()`，UI 层新增资源 ID 时不需要各处重复手写 `datetime`。
- 全局滚轮防误触：`theme_manager.ThemeManager.apply_app_style()` 在应用级安装事件过滤器，禁止通过滚轮切换 `QTabBar` 标签；所有下拉框在未展开下拉列表时忽略滚轮事件，仅在弹出列表展开时响应滚轮；所有数值类 `QAbstractSpinBox` 完全不响应滚轮，始终将滚轮交给外层可滚动容器，避免用户滚动窗口时误改选项或数值。
- UI 预览画布：`ui_preview_canvas.UIPreviewCanvas` 基于 `QGraphicsView` 提供界面控件布局预览，具体的单控件预览图形项由 `ui_preview_item.UIWidgetPreviewItem` 承担；画布支持滚轮缩放与中/右键按住拖拽平移视图，左键负责单/多选与框选控件，选中控件的描边与调整手柄统一使用主题主色（`Colors.PRIMARY`）；为避免拖拽/缩放时出现残影，预览画布使用 `FullViewportUpdate`，并在预览项内部对“选中态/尺寸变化”正确调用 `prepareGeometryChange()` 且禁用 item cache，确保局部重绘边界准确。
- Toast 通知：`toast_notification.ToastNotification` 提供右上角堆叠的非模态提示框，适用于删除成功等无需用户交互的轻量状态反馈，相比对话框更不打断操作流程；`ui_notifier.notify` 封装了“根据传入 QWidget 或带 `main_window` 属性的上下文选择合适父窗口并打印日志”的通用逻辑，业务组件统一通过该函数触发 Toast，而非直接实例化 `ToastNotification`，Toast 卡片的视觉样式由主题样式工厂统一提供。
- 开发者工具：运行时的 UI 悬停检查器等开发调试组件已迁移至 `ui/devtools/` 包中，这里仅保留与业务无关的纯 UI 基础设施，确保基础层不反向依赖具体业务面板或调试工具；平台相关的全局热键能力集中在 `global_hotkey_manager.py`，仅在 Windows 环境下使用。

## 注意事项
- 统一面向 PyQt6：使用枚举与 API 时保持与 Qt6 对应，树/列表等组件优先使用仍受支持的接口（例如 `QTreeWidgetItem.setExpanded()` 或 `tree_widget.expandItem()`），避免调用已在 Qt6 中移除的旧方法。
- 保持“纯 UI 工具”定位：本目录模块不直接访问磁盘或资源索引，具体资源操作交由 `engine.resources` 或上层控制器负责，避免层级倒置与隐藏副作用。
- 不依赖具体业务页面（如 todo、管理面板等），防止循环依赖和架构混乱；需要主题配色的基础绘制工具（如画布网格背景）应直接依赖 `app.ui.foundation.theme` 下的 token，而不是反向从这些工具中导入 `ThemeManager` 本身。
- 通用工具函数应职责单一、参数命名清晰，避免隐式依赖全局状态；修改主题或基础样式时，应考虑对全局 UI 的影响，优先通过集中常量与函数控制。
- 申请新 ID 或构建对话框样式时，优先调用现有工具（如 `generate_prefixed_id()`、`ThemeManager.dialog_surface_style()`），并在需要新的跨页面说明文字时统一写入 `info_snippets.py`。
- 需要标准输入/确认弹窗时，优先从 `app.ui.foundation` 顶层导入：`BaseDialog` / `FormDialog` / `show_*_dialog` / `ask_*_dialog` / `prompt_text` / `prompt_item` / `prompt_int` 等入口，而不是在业务模块中直接 new `QDialog` 或调用 `QInputDialog.get*`；`tools/check_no_direct_qdialog.py` 用于静态检查基础封装层之外的新代码中是否直接使用 `QDialog`。
- `global_hotkey_manager.py` 使用 ctypes 调用 WinAPI（`RegisterHotKey/UnregisterHotKey`）时必须显式声明 `argtypes/restype`（尤其是 `HWND` 在 64 位进程下为指针类型），否则会把窗口句柄当成 32 位 int 导致溢出或参数截断。

 