## 目录用途
- 本目录承载“文件监控 / 资源库自动刷新”链路的**可复用组件**，用于将 `QFileSystemWatcher + 去抖 + 后台线程 + 指纹计算 + 刷新触发 + 冲突处理` 拆分为职责单一的模块。
- 目标是降低 `FileWatcherManager` 的复杂度：`FileWatcherManager` 仅作为主窗口侧门面（facade）与信号转发层，具体逻辑由本目录组件协作完成。

## 当前状态
- **图文件监控**：由 `graph_file_watch_coordinator.py` 负责处理 `fileChanged` 去抖、watcher 恢复、冲突检测、以及重载后视图状态恢复/撤销栈清理。
- **资源库 watcher 注册**：由 `resource_watch_registry.py` 负责后台扫描资源库目录树并在主线程分批 `addPath`，同时支持“新增目录增量补齐”以降低漏监听概率；后台扫描使用 `ResourceWatchDirScanThread`（QThread 子类）。
  - watcher 监听范围做了两层过滤：
    - “资源目录子树”过滤：仅递归监控资源顶层目录（元件库/实体摆放/节点图/战斗预设/管理配置/复合节点库）及其子目录；对项目存档下其它非资源子树（例如解析产物/工具输出）不建立 watcher，也不参与自动刷新触发，避免目录事件风暴导致指纹扫描耗时与 UI 卡顿/崩溃风险。
    - “当前存档作用域”过滤：共享目录始终监听；项目存档目录只监听当前 `package_id` 对应项目，其它项目（例如 test2）即使有文件更新也不触发 watcher/自动刷新，避免跨项目噪音与稳定性风险。
- **目录过滤策略（单一真源）**：`resource_watch_policy.py` 提供 `ResourceWatchPolicy`，统一承载“资源目录子树 + 当前存档作用域”的路径判定逻辑，供 `FileWatcherManager`（directoryChanged 过滤）、`ResourceWatchRegistry`（addPath 过滤）、`ResourceWatchDirScanThread`（扫描剪枝）共同复用，避免三处实现分叉；路径文本归一化统一复用 `engine.utils.path_utils.normalize_slash`（避免各处手写 `replace("\\", "/")`）。
- **资源库自动刷新桥接**：由 `resource_auto_refresh_bridge.py` 将 `resource_library_auto_refresh_state_machine.py` 的纯逻辑动作（计时器/指纹计算/刷新请求）桥接到 Qt 计时器与后台线程；指纹计算使用 `ResourceFingerprintThread`（QThread 子类），启动时会快照当前基线指纹并携带 `trigger_directory`，用于在后台做“按触发子树增量”的指纹确认；桥接层在退出阶段会停止计时器/线程并避免再调度刷新回调。
  - 刷新已后台化后，本桥接层的 `refresh_callback` 语义收敛为“**请求刷新**”（只负责触发主窗口的异步刷新入口，不再在此处同步执行重活）；对应的“刷新互斥（in_progress）”开始/结束由上层在**实际刷新任务开始/完成**时通过 `notify_refresh_started()/notify_refresh_completed()` 驱动，避免状态机因回调快速返回而误判“刷新已完成”并触发刷新风暴。
  - 去抖计时器调度会做“**不延后**（已有更早 timer 不重置）+ **0ms 不重复 stop/start**（避免事件风暴下 timeout 永远没机会执行）”，并对“目录变化去抖”日志做限流，避免刷屏导致 UI 卡顿。
- **UI HTML 自动转换（可选）**：`ui_html_auto_convert_coordinator.py` 监听当前项目存档 `管理配置/UI源码/` 的目录变化；当私有扩展注册了 `register_ui_html_bundle_converter(...)` 时，会自动将 HTML 转换为 UI bundle，并写入运行时缓存（不落资源库），实现“HTML 存着、变更即自动更新缓存”的体验。
  - 当前仓库内的“千星沙箱网页处理工具”私有扩展已改为 **仅 Web 手动导入/刷新**（不再注册该 converter），因此该自动转换链路默认处于禁用态（converter=None 时协调器会直接跳过，不产生副作用）。
  - 扁平化预览兼容：在调用转换器后，主程序会对 `app/runtime/cache/ui_html_bundle_cli/<package_id>/*.flattened__*.flattened.html` 做一次后处理，确保 `data-debug-label` 在同一文件内唯一；避免 Web 侧检查器基于 label 定位时因重复（例如大量 `text-`）导致“列表可点但点击无反应/无法定位”。
  - 刷新回调若抛异常，也必须保证“刷新互斥”能被复位（发出 `RefreshCompletedEvent`），避免状态机永久停留在 refresh in_progress，导致后续目录事件/指纹复核无法继续推进。
  - `set_enabled(True)` 会在已配置周期性复核间隔（`_periodic_interval_seconds>0`）时自动恢复周期性计时器，便于在“临时禁用→恢复”的场景下保持兜底复核能力不丢失。
  - 为排查“后台放置后 UI 卡死/长时间无响应”，桥接层会输出关键诊断日志（目录事件去抖、指纹差异确认、刷新开始/结束耗时）；其中关键链路使用 **warn 级**日志（始终输出），周期性复核类日志仍做限流避免刷屏。

## 注意事项
- 本目录组件可以依赖 Qt（计时器、线程、信号），但**决策逻辑**应尽量保持在纯逻辑层（例如状态机）中，避免在 watcher 事件回调里堆叠策略判断。
- 不在本目录使用 `try/except` 吞异常；错误应直接抛出，由上层统一中止或处理（但允许在边界处使用“必复位/必清理”的 `finally` 语义，避免异常把 Qt 状态机/线程/计时器留在不可恢复状态）。
- 关闭窗口/退出应用时，必须确保本目录创建的后台线程（目录扫描/指纹计算）可被 `requestInterruption()` 及时打断，并在 `cleanup()` 中等待线程退出，避免“线程仍在跑但 Qt 对象已销毁”导致 Windows `access violation`。

## 日志约定
- 本目录默认不直接 `print(...)` 输出监控细节；高频事件（fileChanged、watcher 恢复、初始扫描 addPath 统计等）统一输出到 `log_debug`，需要排查时通过 `settings.DEBUG_LOG_VERBOSE=True` 打开。

## 资源库目录约定（与监听范围）
- 资源库采用“目录即项目存档 + 共享公共资源”结构：资源位于 `assets/资源库/项目存档/<package_id>/...` 与 `assets/资源库/共享/...` 两类资源根目录下；共享根中的资源对所有项目存档可见。
- `ResourceWatchDirScanThread` 的扫描根目录以 `assets/资源库/项目存档` 与 `assets/资源库/共享` 为主，不再依赖资源库根下的旧式按类型目录或旧式索引目录。


