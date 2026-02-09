# 复合节点 UI 子包（ui/composite/）

## 目录用途
`ui/composite/` 收纳全部复合节点专用 UI：复合节点管理器、预览卡片、右侧属性/引脚面板以及后续的复合节点工具组件。目录仅服务于复合节点领域，不承载常规节点图或管理面板逻辑。

## 当前状态
- `composite_node_manager_widget.py` 对外提供 `CompositeNodeManagerWidget`（两页结构：浏览页/预览页），具体实现按职责拆分为 service + mixins：
  - `composite_node_manager_service.py`：`CompositeNodeRow/CompositeNodeService`（无 Qt），提供行数据与 CRUD/加载/保存编排。
  - `composite_node_manager_ui_mixin.py`：工具栏/搜索、页面装配、GraphEditorController 初始化、只读状态控件禁用。
  - `composite_node_manager_browse_mixin.py`：set_context 过滤、文件夹树/列表刷新与搜索。
  - `composite_node_manager_selection_mixin.py`：选中/预览加载、脏改动确认、外部按 id/name 跳转。
  - `composite_node_manager_context_menu_mixin.py`：右键菜单与库结构 CRUD（新建/删除/移动/刷新）。
  - `composite_node_manager_save_mixin.py`：虚拟引脚/元信息修改与保存、影响确认。
  - **浏览页**：左侧文件夹树（`QTreeWidget`）+ 中间复合节点列表（`QListWidget`）；左侧树结构与节点图库一致：
    - 浏览页主体使用 `QSplitter` 分栏：左侧树仅设 `minimumWidth`（默认 `Sizes.LEFT_PANEL_WIDTH`），允许用户拖拽分隔线调整宽度。
    - 顶层为 **`🧩 复合节点库`** 根节点，并显式分出 **`📁 当前项目`** 与 **`📁 🌐 共享`** 两个分支，避免共享节点都在根目录时无法从树上区分归属；
    - **当前项目分支优先、共享分支靠后**；共享分支内的子目录在每一层名称前显示 **`🌐`** 标记，避免共享子目录被误认为项目目录；
    - 单击列表仅选中并通过 `composite_selected` 驱动右侧属性/引脚面板更新；**双击**列表条目才进入预览页。
    - 左侧树对 `QTreeWidget#leftPanel` 启用 `show-decoration-selected`，保证选中高亮覆盖展开箭头/缩进区域，与节点图库的整行选中效果一致。
    - 页面样式不再通过本页 `setStyleSheet()` 覆盖全局主题，统一依赖 `PanelScaffold.apply_widget_style()` 注入的 `ThemeManager.tree_style/list_style/...`，避免与节点图库出现选中态/边距的样式分叉。
  - **预览页**：仅展示 `GraphView` 子图预览区；子图加载统一复用 `GraphEditorController.load_graph_for_composite` 并注入 `composite_edit_context`（`composite_id/manager/on_virtual_pins_changed/can_persist`）。
  - **返回列表**：页面内仍不提供“返回到列表”按钮；与节点图库一致，通过**再次点击左侧导航“复合节点”**触发模式进入，从而重置回浏览页。跨页面的返回/前进由主窗口顶部工具栏的后退/前进提供。
  - **外部更新同步**：库页提供 `reload_library_from_disk()` 用于在不重启进程的情况下重新扫描 `复合节点库/**/*.py`；右键菜单“刷新列表”会重扫磁盘版本并通过 `composite_library_updated` 通知主窗口刷新 NodeRegistry，从而保证列表/右侧面板/预览与最新落盘一致。
  - 页面以“只读预览”为基线（`EditSessionCapabilities.read_only_preview()`），并额外开启 `can_validate=True`：库页不提供“允许保存/保存”入口，避免产生“可改但无法落盘”的错觉；但 **允许拖拽节点** 与 **自动排版** 用于整理视图便于浏览（修改不落盘）；工具栏保留“新建/删除”等按钮但在只读模式下禁用。
- 复合节点库支持接入“当前存档上下文”过滤：`CompositeNodeManagerWidget.set_context(current_package_id, current_package_index)` 会根据顶部存档选择过滤“可见复合节点集合”，并在左侧树中仅构建这些可见节点覆盖到的 `folder_path`（项目目录在前、共享目录在后；tooltip 仍会标注归属，列表条目使用与节点图库一致的 **“共享”徽章**标记共享资源归属）。
- 搜索框仅过滤“中间复合节点列表”（匹配名称/描述/路径/ID），不再对文件夹树做递归隐藏，以保持与节点图库一致的浏览体验。
- 复合节点源码生成策略由应用层决定：`CompositeNodeService` 会在创建 `CompositeNodeManager` 时注入 `app.codegen.CompositeCodeGenerator`，使“保存复合节点到文件”的能力不再要求引擎层内置生成器。
- `composite_node_preview_widget.py`、`composite_node_property_panel.py`、`composite_node_pin_panel.py` 均移入本目录，保持“管理器+右侧面板”同域维护，减少 `ui/` 根和 `ui/panels/` 下的散落文件。
- folder_path/目录字符串的分隔符归一化统一复用 `engine.utils.path_utils.normalize_slash`，避免 UI 层散落 `replace("\\", "/")` 口径漂移。
- 复合节点预览：`preview_scene.py` 提供可复用的绘制项与视图（预览绘制相关字体统一通过 `app.ui.foundation.fonts` 选择，避免硬编码平台字体名），`pin_card_widget.py`/`pin_list_panel.py` 管理引脚卡片与右键行为（虚拟引脚名称支持在列表中双击行内编辑，点击列表其它区域或切换焦点会自动结束编辑并还原为标签），`composite_node_preview_controller.py` 负责合并/删除/重命名逻辑与预览刷新；当 `EditSessionCapabilities.can_persist=False` 时仅更新内存中的 `CompositeNodeConfig`，不会写回复合节点文件。预览图的标题栏渐变与网格背景沿用 `ui/graph/graph_palette.py` 的固定深色调色板（背景 `#1E1E1E`、网格 `#2A2A2A/#3A3A3A`、标题文本 `#FFFFFF` 等），不随主题切换，以保持画布观感一致；预览高度与节点图一致使用 `UI_ROW_HEIGHT` 行高、`UI_NODE_PADDING` 边距与最大行数规则（左右两侧端口总行数取最大），避免多类型端口同时存在时高度偏小；预览画布支持鼠标滚轮缩放，空白处左键或中键拖动画布便于查看大批量虚拟引脚，用户一旦手动缩放/拖拽后不再自动fit以避免“放大后突然重置”。
- `pin_card_widget.py` 使用 ThemeManager/Colors 统一卡片、标签与行内编辑样式，确保虚拟引脚编辑时与主题配色保持一致。
- 虚拟引脚列表交互：当页面 `can_persist=False`（不可落盘）时禁用“引脚类型”修改；引脚名称支持文字选中复制与一键复制按钮；列表顶部会展示当前复合节点标题并提供一键复制入口，便于复用命名与沟通定位。
- 属性/引脚面板复用 `app.ui.foundation.style_mixins.StyleMixin` 的面板样式，`composite_node_property_panel` 直接调用 `apply_panel_style()`，所有输入/按钮/滚动条的主题行为由 `ThemeManager` 集中维护；
  - 属性面板顶部在标题下方以面板级行集成 `PackageMembershipSelector`（单选归属位置），用于配置复合节点的“所属存档/共享”；切换选择等价于移动复合节点 `.py` 文件到 `共享/复合节点库` 或 `项目存档/<package_id>/复合节点库`，由主窗口统一调用 `PackageIndexManager.move_resource_to_root(...)` 完成落盘与缓存刷新。
  - 复合节点的名称/描述等元信息在属性面板中设为只读，避免在库页产生“可改但无法保存”的误导。
- 目录内模块面向 `MainWindow`/`Todo`/`Management` 等上层组件暴露明确定义的 API（`set_composite_widget`、`load_composite`、信号等），便于组合与只读预览。
- 复合节点预览小部件与虚拟引脚列表保持与真实节点一致的顺序和布局，流程/数据引脚在同一侧连续排列；预览图中的端口名文本会避开端口与序号标签区域，始终在端口一侧留出足够间距，保证可读性。

## 注意事项
- 若组件既被普通节点图复用，请仍放在通用目录，由此处组合调用，避免跨域耦合。
- 需要 GraphController/ResourceManager 时，通过依赖注入保持可测试性，禁止在本目录中直接创建全局单例。
- 继续遵守 UI 层异常策略：不写 `try/except` 兜底，把错误交给上层入口处理。
- 涉及“确认/提示”类弹窗时统一走 `app.ui.foundation.dialog_utils`，保证弹窗文案与按钮一致，且提示文本可选中复制。
- 面板与预览小部件的配色统一复用 `ThemeManager/Colors` 与样式工厂，不要在本目录中直接写死十六进制颜色或 QSS 颜色字符串；复合节点预览画布采用深色网格背景时，端口标签与虚拟引脚名称应使用语义上的高对比度前景色（例如 `Colors.TEXT_ON_PRIMARY` 或等价亮色），保证在浅色/深色主题下都具备足够可读性。
- 复合节点右侧“虚拟引脚管理”面板的标题与提示文案使用语义色 `Colors.TEXT_PRIMARY`/`Colors.TEXT_PLACEHOLDER`，保证在浅色/深色主题下文字对比度充足；加载复合节点时会在控制台输出当前虚拟引脚的方向、类型、索引与映射数量，并在预览图中按输入/输出侧分别打印引脚统计，便于排查“只显示首个流程引脚”等布局或解析问题。
