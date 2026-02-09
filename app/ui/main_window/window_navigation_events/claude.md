## 目录用途
`ui/main_window/window_navigation_events/` 用于承载 `WindowAndNavigationEventsMixin` 的拆分实现，按职责把“窗口标题/保存状态、导航历史、UI 会话状态、验证与设置、命令面板、关闭退出”等逻辑拆成多个小 Mixin，避免 `window_navigation_events_mixin.py` 单文件过大。

外部入口保持不变：仍应通过 `ui/main_window/window_navigation_events_mixin.py` 使用聚合后的 `WindowAndNavigationEventsMixin`。

## 模块结构
- `save_status_mixin.py`：窗口标题/保存状态标签/工具栏保存入口。
- `navigation_history_mixin.py`：导航历史（后退/前进）与回放上下文（如复合节点定位）。
- `ui_session_state_mixin.py`：UI 会话状态持久化（去抖写盘）与启动恢复。
- `toast_mixin.py`：全局 Toast 显示入口（薄封装）。
- `navigation_helpers_mixin.py`：通用跳转辅助（`_navigate_to_mode`/管理 section 切换/打开玩家编辑器）。
- `validation_and_settings_mixin.py`：验证、设置对话框、资源库手动刷新、更新/环境检查与下载更新。
- `command_palette_mixin.py`：命令面板 / 快捷键面板 / 快捷键设置 的数据构建与打开入口。
- `close_event_mixin.py`：窗口关闭（未保存修改清单、清理顺序、按脏块增量落盘）。

## 当前状态
- 本目录为 `WindowAndNavigationEventsMixin` 的实现拆分载体，聚合层位于同级 `window_navigation_events_mixin.py`。
- 关闭退出（`close_event_mixin.py`）遵循“清理后再写盘”的顺序：未保存提示通过后先保存 UI 会话状态并停掉异步加载，再清理文件监控，最后 `flush_current_resource_panel()` + `save_dirty_blocks()` 做增量落盘（禁止退出时无条件全量保存）。
- 命令面板与退出提示等用户可见文案对齐“项目存档”术语（PACKAGES 视图）。
 - 顶部工具栏“刷新资源库”入口已后台化：按钮只触发主窗口的异步刷新请求；“开始/完成”提示由主窗口统一发出，避免在 UI 线程阻塞等待导致误判为卡死。
- `validation_and_settings_mixin.py` 额外提供“本地测试”入口：在主程序内启动节点图 + HTML UI 的离线模拟（HTTP server + 系统浏览器预览）；打开/复用对话框时会同步当前项目存档 ID，使其仅展示当前项目范围内的节点图/UI 源码供选择；并注入 `ResourceManager/PackageIndexManager` 以支持入口图 owner 的“引用资源推断”能力。
- 命令面板/快捷键面板已收敛全局调试入口：包含“性能悬浮面板（卡顿定位）”的快捷键提示，并在命令面板中提供“切换悬浮面板/打开性能监控详情面板”的条目，方便在卡顿时快速打开并复制报告。

## 注意事项
- 各 Mixin 仅共享主窗口公开属性/协议（`app_state/view_state/nav_bar/central_stack/right_panel/...`），避免相互反向 import 形成耦合。
- 保持方法命名约定：事件入口 `_on_*`，辅助方法 `_build_* / _trigger_* / _restore_*`，并尽量复用主窗口稳定钩子而非依赖其它 mixin 私有细节。
 - 退出阶段需先停止可能跨线程回调的异步系统（线程池/QThread/后台刷新协调器），再销毁文件监控与 Qt 对象，降低 Windows 下 `access violation` 风险。


