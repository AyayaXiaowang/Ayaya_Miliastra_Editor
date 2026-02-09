# features/ 目录

## 目录用途
主窗口的“功能模块（Feature）”收敛层：把原本分散在 `UISetupMixin` / `wiring/*` / `ModeSwitchMixin` / 各类 `*_events_mixin.py` 里的“新增功能需要多点改动”的装配逻辑，逐步迁移为**单文件自包含**的 Feature。

Feature 的目标不是替代现有架构一次性推倒重来，而是提供一个**渐进迁移的单点扩展口**：
- 新增一个右侧动态面板 / 快捷键 / 信号连线 / 小型流程编排时，优先新增一个 Feature 模块；
- 旧代码继续可用，Feature 与 Mixin/Wiring 并存，逐步把历史入口挪到 Feature 内部。

## 当前状态
- 已引入最小化的 `MainWindowFeature` 协议与默认 feature 安装入口。
- 中央页面的 wiring 已收敛为 `CentralPagesAssemblyFeature`：集中处理各页面的信号连接与页面级 binder 调用，使 `ui_setup_mixin.py` 更接近“只创建控件/布局”的薄层。
  - 存档库页（`PackageLibraryWidget`）额外连线 `package_load_requested -> main_window._on_packages_page_package_load_requested`，用于在 PACKAGES 模式下通过“切换为当前”按钮或双击条目显式切包（左侧选中仅预览，不自动切包）。
- 管理配置库页面除 `data_changed/active_section_changed` 外，还会连接 `selection_summary_changed` 到主窗口的 `_on_management_selection_changed`，以显式信号替代库页对主窗口方法名的反射式调用。
- 模板/实体/战斗等“库页选中”信号优先使用统一的 `selection_changed(LibrarySelection | None)`，降低 `CentralPagesAssemblyFeature` 需要逐页绑定不同 `*_selected` 信号的耦合；若某页尚未迁移，仍保留旧信号回退连接。
- 右侧面板已大胆收敛为单一 Feature：`RightPanelAssemblyFeature` 负责
  - 执行监控面板创建与上下文注入
  - 右侧各面板的 binder 信号连线（调用 wiring 的 binder 函数）
  - 右侧标签注册矩阵（tab_id/标题/允许模式）；其中管理模式相关 tabs 由 `ui/main_window/management_right_panel_registry.py` 的配置驱动，避免分散硬编码
  - 节点图库只读页签：注册 `graph_used_definitions`（“信号/结构体/变量”），用于从当前选中节点图汇总并展示其引用到的信号/结构体/关卡变量定义与使用位置
  - 创建 `main_window.right_panel`（`RightPanelController`）作为对外唯一入口：业务代码只调用 `right_panel.*` 表达意图，不再直接操作 registry/policy，减少协议漂移与“两个真源”风险
  - 不在 `main_window` 上额外挂载执行监控面板别名属性；面板访问统一通过 `right_panel`（tab_id=`execution_monitor`）完成
  以减少新增右侧面板时跨 `UISetupMixin + wiring + presenter/mixin` 的多点修改。

## 注意事项
- Feature 内不做“吞异常/兜底”，错误直接抛出，便于定位装配顺序问题。
- Feature 不应把业务逻辑写回主窗口；复杂流程仍应下沉到 controller/service 或 `app/models`。
- Feature 只能依赖主窗口公开属性（例如 `side_tab/right_panel_registry/graph_controller/app_state`，以及通过 `app_state.workspace_path/node_library/...` 获取稳定依赖），避免反向导入 Mixin 私有实现。


