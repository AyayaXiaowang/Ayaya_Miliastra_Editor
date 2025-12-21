# 复合节点 UI 子包（ui/composite/）

## 目录用途
`ui/composite/` 收纳全部复合节点专用 UI：复合节点管理器、预览卡片、右侧属性/引脚面板以及后续的复合节点工具组件。目录仅服务于复合节点领域，不承载常规节点图或管理面板逻辑。

## 当前状态
- `composite_node_manager_widget.py` 基于 `DualPaneLibraryScaffold` 实现复合节点管理库页面：左侧为按文件夹组织的树，右侧为节点图编辑器内核（`GraphView+GraphScene`），复合节点列表与 CRUD 由 `CompositeNodeService` 封装后注入管理器；页面采用 `EditSessionCapabilities` 作为能力单一真源，并在工具栏提供“允许保存”开关：默认可交互预览（不落盘）；开启后允许保存并对复合节点库执行写入类操作。保存会通过引擎侧 `CompositeNodeManager` 将子图与虚拟引脚写回复合节点文件；当目标文件不是 payload 格式时，会在保存前弹出“覆盖源码并转换为 payload”的确认提示。
- 复合节点库支持接入“当前存档上下文”过滤：`CompositeNodeManagerWidget.set_context(current_package_id, current_package_index)` 会根据顶部存档选择过滤左侧树，只显示当前存档索引 `resources.composites` 引用的复合节点；在 `<全部资源>` 视图下不启用过滤；在 `<未分类资源>` 视图下会推导“未被任何包索引引用”的复合节点集合，并同时收敛文件夹树以避免出现空文件夹。
- 复合节点源码生成策略由应用层决定：`CompositeNodeService` 会在创建 `CompositeNodeManager` 时注入 `app.codegen.CompositeCodeGenerator`，使“保存复合节点到文件”的能力不再要求引擎层内置生成器（仍可在只读模式下不触发保存）。
- 子图加载路径统一复用 `GraphEditorController.load_graph_for_composite`：控制器在内部对复合子图执行一次 `layout_by_event_regions` 预排版，并通过 `composite_edit_context` 将 `composite_id` / `CompositeNodeManager` / `on_virtual_pins_changed` / `can_persist` 等上下文传入 `GraphScene`，使复合页的交互约束与主编辑器保持一致；当未注入 `ResourceManager` 时，管理器退化为本地 `GraphScene` + 手动 `add_node_item/add_edge_item` 的基础实现。
- 复合节点树的构建/展开状态与文件夹结构仍复用 `app.ui.foundation.folder_tree_helper` 和标准化 `dialog_utils`，与节点图库共享同一套逻辑；当 `EditSessionCapabilities.can_persist=False` 时，左侧工具栏与上下文菜单中的“新建/删除/移动”等具备写入语义的操作会在 UI 层禁用或短路，仅保留浏览、选择与跳转能力。
- 复合节点管理器左侧树使用全局 `ThemeManager.left_panel_style()` 与基础树样式组合，选中与悬停高亮风格与节点图库、管理配置等页面的左侧分类列表保持一致，便于用户在不同库视图之间获得统一的导航体验。
- `composite_node_preview_widget.py`、`composite_node_property_panel.py`、`composite_node_pin_panel.py` 均移入本目录，保持“管理器+右侧面板”同域维护，减少 `ui/` 根和 `ui/panels/` 下的散落文件。
- 复合节点预览：`preview_scene.py` 提供可复用的绘制项与视图（预览绘制相关字体统一通过 `app.ui.foundation.fonts` 选择，避免硬编码平台字体名），`pin_card_widget.py`/`pin_list_panel.py` 管理引脚卡片与右键行为（虚拟引脚名称支持在列表中双击行内编辑，点击列表其它区域或切换焦点会自动结束编辑并还原为标签），`composite_node_preview_controller.py` 负责合并/删除/重命名逻辑与预览刷新；当 `EditSessionCapabilities.can_persist=False` 时仅更新内存中的 `CompositeNodeConfig`，不会写回复合节点文件。预览图的标题栏渐变与网格背景沿用 `ui/graph/graph_palette.py` 的固定深色调色板（背景 `#1E1E1E`、网格 `#2A2A2A/#3A3A3A`、标题文本 `#FFFFFF` 等），不随主题切换，以保持画布观感一致；预览高度与节点图一致使用 `UI_ROW_HEIGHT` 行高、`UI_NODE_PADDING` 边距与最大行数规则（左右两侧端口总行数取最大），避免多类型端口同时存在时高度偏小；预览画布支持鼠标滚轮缩放，空白处左键或中键拖动画布便于查看大批量虚拟引脚，用户一旦手动缩放/拖拽后不再自动fit以避免“放大后突然重置”。
- `pin_card_widget.py` 使用 ThemeManager/Colors 统一卡片、标签与行内编辑样式，确保虚拟引脚编辑时与主题配色保持一致。
- 属性/引脚面板复用 `app.ui.foundation.style_mixins.StyleMixin` 的面板样式，`composite_node_property_panel` 直接调用 `apply_panel_style()`，所有输入/按钮/滚动条的主题行为由 `ThemeManager` 集中维护；属性面板顶部在标题下方以面板级行集成 `PackageMembershipSelector`，该行通过 `app.ui.panels.package_membership_selector.build_package_membership_row()` 构建，用于配置复合节点的“所属存档”，并通过 `package_membership_changed` 信号将勾选结果交由主窗口写入 `PackageIndex.resources.composites`——这是复合节点页面中唯一允许通过 UI 修改并持久化的字段，其余内容均视为只读预览。
- 目录内模块面向 `MainWindow`/`Todo`/`Management` 等上层组件暴露明确定义的 API（`set_composite_widget`、`load_composite`、信号等），便于组合与只读预览。
- 复合节点预览小部件与虚拟引脚列表保持与真实节点一致的顺序和布局，流程/数据引脚在同一侧连续排列；预览图中的端口名文本会避开端口与序号标签区域，始终在端口一侧留出足够间距，保证可读性。

## 注意事项
- 若组件既被普通节点图复用，请仍放在通用目录，由此处组合调用，避免跨域耦合。
- 需要 GraphController/ResourceManager 时，通过依赖注入保持可测试性，禁止在本目录中直接创建全局单例。
- 继续遵守 UI 层异常策略：不写 `try/except` 兜底，把错误交给上层入口处理。
- 面板与预览小部件的配色统一复用 `ThemeManager/Colors` 与样式工厂，不要在本目录中直接写死十六进制颜色或 QSS 颜色字符串；复合节点预览画布采用深色网格背景时，端口标签与虚拟引脚名称应使用语义上的高对比度前景色（例如 `Colors.TEXT_ON_PRIMARY` 或等价亮色），保证在浅色/深色主题下都具备足够可读性。
- 复合节点右侧“虚拟引脚管理”面板的标题与提示文案使用语义色 `Colors.TEXT_PRIMARY`/`Colors.TEXT_PLACEHOLDER`，保证在浅色/深色主题下文字对比度充足；加载复合节点时会在控制台输出当前虚拟引脚的方向、类型、索引与映射数量，并在预览图中按输入/输出侧分别打印引脚统计，便于排查“只显示首个流程引脚”等布局或解析问题。


