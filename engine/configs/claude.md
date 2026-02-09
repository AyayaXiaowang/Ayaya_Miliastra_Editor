## 目录用途
配置「定义 / Schema / 默认值」的集中地，不存放任何实例化数据或环境私有配置。

## 当前内容
- `settings.py`：全局设置类（调试选项、验证选项、布局选项、资源库刷新策略、真实执行与运行时行为开关、安全声明提示等），提供如 `LAYOUT_TIGHT_BLOCK_PACKING` 与 `DATA_NODE_CROSS_BLOCK_COPY` 这类布局行为开关、`LAYOUT_NODE_SPACING_X_PERCENT/LAYOUT_NODE_SPACING_Y_PERCENT` 这类自动排版间距倍率配置（横向/纵向，100% 为基准）、`RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED` 这类资源库自动刷新开关，以及任务清单相关的 `TODO_MERGE_CONNECTION_STEPS`、`TODO_GRAPH_STEP_MODE`（默认 `ai`：AI-先配置后连线；另支持 `ai_node_by_node`：AI-逐个节点模式）与 `TODO_EVENT_FLOW_LAZY_LOAD_ENABLED`（事件流子步骤分批挂载开关）；输出与 UI 相关的调试/交互开关也在此集中管理（例如 `UI_TWO_ROW_FIELD_DEBUG_PRINT` 控制 TwoRowField 行高调试打印 `[UI调试/TwoRowField]`，`UI_UNHANDLED_EXCEPTION_DIALOG_ENABLED` 控制 UI 全局未捕获异常是否弹出阻塞错误对话框）；节点图画布交互也在此集中管理（例如 `GRAPH_AUTO_FIT_ALL_ENABLED` 控制是否允许“进入编辑器/预览时自动适配全图（压缩视图）”、`GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED` 控制行内常量控件虚拟化、`GRAPH_LOD_ENABLED` 与 `GRAPH_LOD_*` 控制缩放分级渲染/可见性回滞/连线命中测试降级阈值，其中端口绘制阈值 `GRAPH_LOD_PORT_MIN_SCALE` 默认 0.30（30%）；背景网格会在低倍率下按 `GRAPH_GRID_MIN_PX` 自动放大步长以避免网格过密导致卡顿；块鸟瞰模式由 `GRAPH_BLOCK_OVERVIEW_*` 控制进入/退出阈值与鸟瞰网格密度）；同时还包含 `REAL_EXEC_CLICK_BLANK_AFTER_STEP` / `REAL_EXEC_REPLAY_RECORDING_ENABLED` 等控制自动化执行收尾与回放记录行为的开关；`RUNTIME_CACHE_ROOT` 用于统一配置运行时缓存根目录（默认 `app/runtime/cache`）；设置的本地持久化文件默认落在 `app/runtime/cache/user_settings.json`。启动入口需先调用 `settings.set_config_path(workspace_root)` 注入工作区根目录，供布局/缓存等模块使用；并通过 `engine.utils.logging.logger` 输出统一格式日志；同时通过 `LAYOUT_ALGO_VERSION` 暴露布局算法语义版本号，供资源层在加载节点图缓存时判定布局语义是否兼容。验证相关设置包含“节点图脚本运行时校验”开关，用于在直接运行/导入节点图源码时及早暴露不符合规范的写法；布局增强补充包含 `LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY` 与 `LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE`，用于在跨块复制后自动插入【获取局部变量】中转节点拆分“同块内跨节点距离过长”的长连线（按阈值分段）。
  - 导出相关补充：`UGC_GIA_NODE_POS_SCALE` 用于控制“节点图 `.gia` 导出时的节点坐标缩放倍数”（对 x/y 同步乘法缩放，配合 X 轴居中对齐）；仅影响真源编辑器中的分布展示，不影响图逻辑语义。
  - 全局性能监控（卡顿定位）：`APP_PERF_MONITOR_ENABLED` / `APP_PERF_OVERLAY_ENABLED` / `APP_PERF_STALL_THRESHOLD_MS` / `APP_PERF_CAPTURE_STACKS_ENABLED` 用于启用 UI 心跳 + watchdog 的轻量监控，记录 UI 主线程阻塞事件并可选显示主窗口级悬浮面板，帮助定位“非画布页面/全局卡顿”。
  - 节点图 fast_preview 边渲染：`GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED` 控制是否以单一渲染层批量绘制轻量预览边，进一步降低超大图的 `QGraphicsItem` 数量（仅影响 fast_preview_mode）。
  - 只读大图批量边：`GRAPH_READONLY_BATCHED_EDGES_ENABLED` / `GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD` 控制在只读预览场景（例如任务清单右侧图预览）下是否将连线从“逐条 EdgeGraphicsItem”收敛为“批量边渲染层”，以显著降低超大图的 item 数量与重绘开销（不要求启用 fast_preview）。
  - 画布性能面板：`GRAPH_PERF_PANEL_ENABLED` 控制是否在画布左上角显示实时耗时分解面板（拖拽/缩放/重绘卡顿定位用），默认关闭以避免日常使用的额外统计开销。
  - 切图画布缓存：`GRAPH_SCENE_LRU_CACHE_SIZE` 控制运行期 GraphScene LRU 缓存容量（默认 2，0 禁用），用于同进程 A→B→A 秒切回并避免重建图元；注意内存开销显著，建议保持小容量（1~2）。
  - 画布网格：`GRAPH_GRID_ENABLED` 控制是否绘制网格线（背景底色仍保留）；关闭后可显著降低超大图平移/缩放时的背景绘制开销。
  - 平移/缩放隐藏图标：`GRAPH_PAN_HIDE_ICONS_ENABLED` 控制是否在平移（拖拽）或滚轮缩放期间临时隐藏端口/⚙/+ 等小图元并跳过 YDebug 叠层绘制，停止交互后恢复，用于减少 Qt item 枚举与绘制固定开销。
  - 拖拽平移静态快照：`GRAPH_PAN_FREEZE_VIEWPORT_ENABLED` 控制是否在手抓拖拽平移期间将画布冻结为静态快照（拖拽平移时不重绘 items，松手后恢复），用于极致优化超大图平移流畅度。
  - 缩放静态快照：`GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED` 控制是否在滚轮缩放期间将画布冻结为静态快照（缩放时不重绘 items，停止滚轮后恢复），用于极致优化超大图缩放流畅度。
  - 布局相关补充：`LAYOUT_COMPACT_DATA_Y_IN_BLOCK` / `LAYOUT_DATA_Y_COMPACT_PULL` / `LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD` 用于控制块内数据节点 Y 轴松弛阶段的“紧凑偏好”，在满足端口下界/列内不重叠/多父区间等硬约束的前提下，尽量减少垂直空洞，使可调整的父级链条整体更紧凑。
  - 日志相关补充：`NODE_IMPL_LOG_VERBOSE` 控制 `log_info` 输出；`DEBUG_LOG_VERBOSE` 控制 `log_debug` 输出，用于将启动/监控等高频细节降到 Debug，默认不刷屏。
- 私有扩展配置：`PRIVATE_EXTENSION_ENABLED` / `PRIVATE_EXTENSION_SYS_PATHS` / `PRIVATE_EXTENSION_MODULES` 仅作为“扩展机制”的 schema；实际私有实现不入库，由使用者在本机通过用户设置文件配置加载。当前 `PRIVATE_EXTENSION_ENABLED` 与 `RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED` 会在加载配置后被强制设为 True（不再由设置页控制）。
- `resource_types.py`：资源类型枚举，统一罗列资源库中实际存在的资源类别（模板、实体摆放、节点图、战斗预设与各类管理配置等），供资源层与上层引用，不包含额外的代码占位型资源；其中管理配置包含 UI 相关资源（`UI布局/UI控件模板/UI页面` 等）用于 UI 工作流的“源-派生-入口”收敛。
- `rules/*`：节点图与运行时使用的定义 / 规则占位（例如类型占位定义、规则配置等），需保证在当前 Python 版本下可正常导入；其中 `rules/entity_rules.py` 提供实体类型、组件兼容性与实体变换校验等权威规则定义与查询接口。
- `ingame_save_data_cost.py`：局内存档数据量计算模块，基于引擎实测数据提供各字段类型的数据量开销计算能力。定义了各类型（整数、布尔值、浮点数、字符串、三维向量、GUID、配置ID等）的单值和列表开销，支持根据结构体定义和条目数量计算总数据量，并提供超限检测功能。数据量上限为 10000 点。

## 公共 API
通过 `engine` 导出用于上层注入或读取的 Schema / 常量。

## 依赖边界
- **允许依赖**：`engine/utils`
- **禁止依赖**：`app/*`、`plugins/*`、`assets/*`、`core/*`

## 注意事项
- 区分「定义（这里）」与「落盘数据（assets/ 或 app/ 注入）」。
- 资源类型枚举 `ResourceType` 定义于 `engine/configs/resource_types.py`，供资源层与上层统一引用。
- 全局设置实例 `settings` 可从 `engine.configs.settings` 或 `engine` 顶层导入。
- `rules/` 下的占位类型 / 规则仅作为类型检查和配置 Schema 使用，不应依赖运行时副作用；同时需要考虑 Python 版本限制（例如内置不可继承类型），以免阻塞任意节点图脚本的导入。

---
注意：本文件不记录任何修改历史。请始终保持对「目录用途、当前状态、注意事项」的实时描述。
