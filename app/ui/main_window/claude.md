## 目录用途
- 主窗口装配与事件分发：用 Mixin 架构把主窗口职责拆分，再由 `MainWindowV2` 组合。
- 承载模式切换、右侧面板联动、导航请求转发、会话状态保存/恢复、资源库刷新编排等“应用级胶水”。

## 当前状态
- `main_window.py`：`MainWindowV2` 作为壳/装配层；稳定依赖集中在 `MainWindowAppState`（`app_state.py`），各 Mixin 只通过 `self.app_state` 访问共享依赖。
- 启动期模式稳定：主窗口在首次 `show()` 前优先读取上一次会话的 `view_mode` 并预切换到目标模式，降低“先显示默认页再跳转”的启动闪烁感；完整的会话恢复（选中/打开图等）仍由会话恢复 mixin 在事件循环启动后补齐。
- 资源库刷新：`ResourceRefreshService` 负责缓存失效/索引重建；`ResourceRefreshCoordinator` 将构建后台化并做 singleflight + pending 合并。
- 模式体系：`ViewMode` + `mode_presenters/` + `ModeTransitionService` 负责进入模式副作用与切换顺序；选中上下文逐步收敛到 `MainWindowViewState`（`view_state.py`）。
- 右侧面板：对外统一走 `RightPanelController`；内部用 `RightPanelPolicy` + `RightPanelRegistry` + `right_panel_contracts.py` 实现“模式/section → tabs”收敛。
- 图画布复用：全局 `app_state.graph_view` 在图编辑器与任务清单预览间移动复用；进入 `ViewMode.TODO` 时切换为 `EditSessionCapabilities.read_only_preview()`，保证预览页只读。
- 连接与跳转：`wiring/` 作为信号绑定/导航转发集中入口；新增功能优先收敛到 `features/`，避免在 `ui_setup_mixin.py` 或多个 mixin 中继续堆积分支与 `.connect(...)`。

## 注意事项
- **依赖边界**：仅依赖允许层（`engine/*`、`app/models/*` 等）；避免模块顶层副作用（I/O、环境探测、重型依赖加载）。
- **模式切换禁止旁路**：统一通过 `ModeTransitionService.transition(...)`（或主窗口公开导航入口），不要直接操作 `central_stack`/`side_tab`。
- **右侧面板操作**：业务代码只调用 `RightPanelController` 与合同模板；禁止直接 `side_tab.addTab/removeTab` 或调用各类 `_ensure_*` 私有方法。
- **选中回调先校验 ViewMode**：防止后台刷新发出的“空选中/重建列表”事件抢占当前模式右侧上下文。
- **刷新要后台化**：索引扫描/解析/重建必须后台线程完成；主线程仅提交快照并刷新页面（保持 UI 线程 O(1)）。
