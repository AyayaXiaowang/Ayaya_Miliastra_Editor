## 目录用途
`ui/main_window/window_navigation_events/` 承载 `WindowAndNavigationEventsMixin` 的拆分实现：按职责把“窗口标题/保存状态、导航历史、UI 会话状态、验证与设置、命令面板、关闭退出”等逻辑拆成多个小 mixin，并由聚合入口 `window_navigation_events_mixin.py` 组合继承以保持对外入口稳定。

## 当前状态
- **模块拆分**：包含 `save_status_mixin.py`（标题/保存状态）、`navigation_history_mixin.py`（后退/前进）、`ui_session_state_mixin.py`（会话状态持久化与恢复）、`toast_mixin.py`、`navigation_helpers_mixin.py`、`validation_and_settings_mixin.py`、`command_palette_mixin.py`、`close_event_mixin.py`。
- **会话恢复与启动稳定**：`ui_session_state_mixin.py` 提供启动期 `view_mode` 的轻量窥探入口，供主窗口在首次 `show()` 前预切换模式；恢复过程中若已处于目标 `ViewMode` 则跳过重复导航，仅补齐选中/详情恢复，减少二次跳变。
- **退出顺序**：关闭退出遵循“清理后再写盘”：提示通过后先保存 UI 会话状态并停止异步加载，再清理文件监控，最后做增量落盘（禁止退出时无条件全量保存）。
- **刷新后台化**：工具栏“刷新资源库”入口只触发异步刷新请求，“开始/完成”提示由主窗口统一发出，避免 UI 线程阻塞。
- **本地测试入口**：`validation_and_settings_mixin.py` 提供“本地测试（Local Graph Sim）”打开入口（HTTP server + 系统浏览器预览），并按当前项目存档作用域刷新可选图/UI 源码列表。
- **命令面板与调试**：命令面板/快捷键面板收敛全局调试入口（如性能悬浮面板开关与性能监控详情），便于卡顿排查。

## 注意事项
- 各 mixin 仅共享主窗口公开属性/协议（`app_state/view_state/nav_bar/central_stack/right_panel/...`），避免相互反向 import 形成耦合。
- 保持方法命名约定：事件入口 `_on_*`，辅助方法 `_build_* / _trigger_* / _restore_*`，优先复用主窗口稳定钩子。
- 退出阶段需先停止可能跨线程回调的异步系统（线程池/QThread/后台刷新协调器），再销毁 watcher 与 Qt 对象，降低 Windows 下 `access violation` 风险。

