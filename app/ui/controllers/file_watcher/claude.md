## 目录用途
`ui/controllers/file_watcher/` 收敛“文件监控 / 资源库自动刷新”链路的可复用组件：将 `QFileSystemWatcher + 去抖 + 后台线程 + 指纹计算 + 刷新触发` 拆分为职责单一的模块，供主窗口门面 `FileWatcherManager` 组合使用。

## 当前状态
- **图文件监控**：`graph_file_watch_coordinator.py` 处理 `fileChanged` 去抖、watcher 恢复、冲突检测，以及重载后视图状态恢复/撤销栈清理。
- **资源库 watcher 注册**：`resource_watch_registry.py` 后台扫描资源库目录树并在主线程分批 `addPath`；扫描线程为 `ResourceWatchDirScanThread`。
- **目录过滤策略（单一真源）**：`resource_watch_policy.py` 提供 `ResourceWatchPolicy`，统一“资源目录子树 + 当前存档作用域”的路径判定；路径归一化统一复用 `engine.utils.path_utils.normalize_slash`。
- **自动刷新桥接**：`resource_auto_refresh_bridge.py` 将纯逻辑状态机（计时器/指纹计算/刷新请求）桥接到 Qt 计时器与后台线程；指纹计算由 `ResourceFingerprintThread` 执行；bridge 的回调语义收敛为“请求刷新”，互斥开始/结束由上层在真实刷新任务开始/完成时通知。
- **UI HTML 自动转换（可选）**：`ui_html_auto_convert_coordinator.py` 监听当前项目存档 `管理配置/UI源码/` 变化；路径判定与 UI 源码目录计算做缓存并以纯字符串归一化比对（避免在 directoryChanged 风暴下频繁 `resolve()` 触发 IO）；当私有扩展注册 converter 时执行转换并写入运行时缓存（不落资源库），否则为禁用态且无副作用。

## 注意事项
- watcher 监听范围应同时做两层过滤：只监听资源子树（元件库/实体摆放/节点图/战斗预设/管理配置/复合节点库等）+ 仅监听“共享 + 当前 package_id”的项目存档根目录，避免跨项目噪音与目录事件风暴。
- 高并发目录事件下的去抖/调度应避免“无限延后”，并对高频日志做限流，防止刷屏引发 UI 卡顿。
- 热路径（directoryChanged 过滤/事件去重/批量 watcher 维护）应避免触发文件系统 IO（例如频繁 `Path.resolve()`）；路径去重/归一化优先使用纯字符串规范化；必要的 `directories()` 读取尽量缓存并增量更新。
- 本目录不使用 `try/except` 吞异常；关闭窗口/退出应用时必须可打断并回收后台线程（目录扫描/指纹计算），避免 Qt 对象销毁后的跨线程回调导致 Windows `access violation`。
- 日志约定：高频事件默认走 `log_debug`，按 `settings.DEBUG_LOG_VERBOSE` 控制可见性；需要用户决策的提示统一交由上层对话框处理。
- 资源库目录约定：资源根目录为 `assets/资源库/共享/...` 与 `assets/资源库/项目存档/<package_id>/...`，扫描与监听不依赖旧式按类型目录结构。

