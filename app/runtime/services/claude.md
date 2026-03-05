## 目录用途
`app/runtime/services/`：应用层运行时服务（**无 PyQt6 依赖**）。用于收敛资源加载/缓存策略/纯策略计算等可测试逻辑，供 UI 控制器与面板复用。

## 当前状态
- **图数据门面**：`graph_data_service.py` 的 `GraphDataService` 统一加载 `GraphConfig/GraphModel` 并做进程内缓存与失效（按 graph_id / 一键清理），供编辑器与 TODO 预览共享。
- **运行期缓存门面**：`json_cache_service.py` 的 `JsonCacheService` 统一派生 runtime cache root（遵循 `settings.RUNTIME_CACHE_ROOT`），并用原子写保证会话状态/轻量 KV 缓存一致性。
- **预览扫描服务**：`resource_preview_scan_service.py` 的 `ResourcePreviewScanService` 直接从磁盘扫描资源 ID 列表与代码级 Schema（节点图/信号/结构体），用于“预览其它项目存档”而不切换当前 ResourceManager 作用域。
- **画布/面板策略**：`graph_scene_policy.py`、`execution_monitor_panel_policy.py` 等将 UI 侧高频 if-else 下沉为纯策略，UI 只负责应用到 Qt 图元/控件。
- **本地图模拟器**：`local_graph_simulator.py` 提供稳定会话入口（`LocalGraphSimSession / build_local_graph_sim_session`），并配套 HTTP server / 协议描述 / web assets，支持在 runtime cache 下生成可回放/可复现的模拟产物。
- **UI Workbench 纯逻辑**：`ui_workbench/` 提供 UI 源码浏览/布局导入/变量默认值处理等服务，UI 侧仅做门面与展示。

## 注意事项
- 允许依赖：`engine/*`、`app/runtime/*`、`app/common/*`；禁止依赖 `app/ui/*` 与 `PyQt6/*`。
- 服务必须可单测：不要在导入阶段触盘/启动线程；需要后台执行时提供显式启动与 shutdown。
- 缓存必须提供集中失效入口；不使用 try/except 吞错，错误直接抛出或返回结构化结果由上层决定呈现。
