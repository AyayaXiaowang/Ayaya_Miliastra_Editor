## 目录用途
管理模式下与“管理配置（management）”相关的注册表与少量通用基元：为管理库页面（sections）、右侧编辑面板与工具脚本提供统一的“类型/资源桶/聚合口径”单一真源。

## 当前状态
- **资源访问口径**：管理配置通过 `engine.resources` 的 `PackageView/GlobalResourceView` + `ResourceManager` 访问（共享根 + 当前项目存档根）；项目存档索引仅保存引用 ID（`PackageIndex.resources.management[...]`），编辑面向资源视图模型而非索引本体。
- **UI 主入口**：管理模式列表页由 `ManagementLibraryWidget` 与各 `BaseManagementSection` 实现驱动；本目录的旧版页面骨架（`BaseConfigPage/StandardTablePage/...`）仅保留给少量遗留对话框/工具页参考，新页面应直接实现 section + 复用通用对话框基类。
- **注册表（单一真源）**：`section_registry.py` 统一声明
  - `MANAGEMENT_SECTIONS`：section_key → 标题/分组/资源绑定；
  - `MANAGEMENT_RESOURCES` 及其派生常量：资源桶顺序、标题、ResourceType 绑定、聚合模式；
  - `MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS`：用于从“资源桶 key”映射到管理页面默认 section_key（双击跳转等场景）。
- **与主窗口协作**：库页通过选中信号驱动主窗口 `_on_management_selection_changed`；右侧通用/专用面板选择由 `management_right_panel_registry.py` 的注册表 + `RightPanelController` 统一编排。
- **UI HTML 工作流收敛**：UI HTML 以源码为真源，派生物进入运行时缓存，因此管理库不再以“管理配置资源”的方式维护 UI 页面/布局/控件模板入口。

## 注意事项
- 新增管理类型时，先更新 `section_registry`（sections/resources/default mapping），再实现对应 `BaseManagementSection`；若需要右侧专用编辑面板，则在 `app.ui.panels` 增加 Panel 并在主窗口右侧面板注册表中接入。
- 避免在多个视图重复硬编码“资源桶标题/顺序/聚合模式”；一律以 `section_registry.py` 为准。
- 表单/表格类编辑优先复用 `FormDialog`/`FormDialogBuilder` 与 `ThemeManager` 样式 token；错误不做 `try/except` 吞掉，统一通过对话框提示用户或直接抛出暴露回归。

