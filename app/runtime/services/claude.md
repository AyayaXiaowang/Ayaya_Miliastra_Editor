## 目录用途
`app/runtime/services/` 存放 **无 PyQt6 依赖** 的应用层运行时服务（service），用于收敛“资源加载 / 缓存策略 / 领域计算”等可测试逻辑，供 UI 控制器与面板复用。

## 当前状态
- `graph_data_service.py`：图数据统一门面（GraphDataService）
  - 统一提供 `GraphConfig/graph_data/GraphModel` 的加载与内存缓存（含 GraphModel 的签名失效，避免布局变更后复用旧模型）
  - 桥接进程内 `graph_data_key` payload 缓存（resolve/store/drop/clear），并将 `invalidate_graph()` 作为“一句清干净”的统一失效入口，供 Todo/预览/导航共享
  - 资源库存在非法节点图源码时，图资源加载可能抛出解析异常：GraphDataService 会将 `ResourceManager.load_resource(ResourceType.GRAPH, ...)` 通过延迟初始化的线程池隔离为“可读错误文本”（可通过 `get_graph_load_error(graph_id)` 获取），避免异常直接炸穿 UI 主线程
- 节点图“所属存档/归属位置”判定走 `PackageIndexManager.get_resource_owner_root_id(resource_type="graph", ...)`：目录即项目存档模式下不再扫描全部存档索引做多对多归属，而是直接依据图文件位于 `共享/` 或 `项目存档/<package_id>/` 判断单选归属根目录。
- `graph_model_cache.py`：GraphModel 缓存工具（纯函数 + 小型 entry），供图相关 UI 在本地字典缓存 GraphModel 时复用
- `json_cache_service.py`：运行期 JSON 缓存门面（JsonCacheService）
  - 统一派生 runtime_cache_root（遵循 `settings.RUNTIME_CACHE_ROOT` 与 `engine.utils.cache.cache_paths` 单一真源）
  - 提供“整文件 JSON”读写与“KV（schema_version + values）”模式，供 UI 会话状态与轻量 UI 记忆类缓存复用
  - 写入统一采用原子写（tmp -> replace），避免中断导致空文件/半写入
  - 提供 `append_jsonl/append_text`，用于“回放记录”等按行追加的落盘场景，避免各处手写路径拼接与文件打开逻辑
- `local_graph_simulator.py`：本地测试的图模拟器（GraphRunner）
  - 加载 Graph Code 源码（并可选生成可执行代码写入 runtime cache），用 `GameRuntime` 驱动事件/信号
  - 启动阶段会从图变量默认值中解析 `ui_key:` 占位符并派生为稳定的“伪 GUID/索引”，用于离线 UI 交互模拟
  - `布局索引_` 图变量支持从描述中提取 HTML 名称并回填稳定 layout_index（用于 `switch_layout` 的页面切换模拟）
  - 支持配置在场玩家数量（创建并复用 `玩家1..玩家N`），用于多人等待/投票门槛等图逻辑模拟
  - UI click 注入支持指定触发玩家（`LocalGraphSimSession.trigger_ui_click(player_entity=...)`），用于多玩家交互回归（投票/等待其他玩家等）
  - 发送信号时允许直接传入 `signal_name`（自动解析为对应 `signal_id`），便于按节点图侧显示名称快速回归
  - 支持在同一 `GameRuntime` 中**同时挂载多个节点图**（主图 + `extra_graph_mounts`）：用于 UI 图联动数据服务图/流程图等多图闭环回归
  - 支持 `resource_mounts`：按“元件模板/实体摆放/关卡实体”解析挂载图并预置自定义变量（读取 `metadata.custom_variable_file` 引用的变量文件默认值 + 『自定义变量』组件默认值 + 实例 `override_variables`），用于让服务图依赖的实体变量在启动即已加载
  - 当未显式提供 `resource_mounts` 且存在 `extra_graph_mounts` 时，会尝试在 active_package_id 对应项目存档内为“额外挂载图”推断一个合适的挂载资源（优先元件模板），并据此预置自定义变量快照；若推断成功，同一图不会再按 `extra_graph_mounts` 重复挂到其它 owner（避免挂到缺变量的实体导致读取到 `None`）
- `local_graph_sim_mount_catalog.py`：本地测试的“元件/实体挂载”目录与解析器
  - 扫描项目存档的模板/实例/关卡实体，输出可勾选的挂载项（挂载的节点图 + 自定义变量名预览）
  - 将勾选项解析为运行期计划：`(graph_code_file, owner_entity_name)` 列表 + `owner_entity -> custom_variables` 初值快照（默认值来源按“变量文件 → 组件 → override”覆盖）
- `local_graph_sim_server.py`：本地测试 HTTP server（启动/重启/端口策略/会话管理）
  - 端口策略与 Windows 独占绑定策略保持不变（默认 `17890`，支持 `AYAYA_LOCAL_HTTP_PORT` / `AYAYA_LOCAL_SIM_PORT` 覆盖）
  - 启动时会从 UI HTML 的 `data-ui-variable-defaults` 提取 `lv.*` 默认值并注入到 `GameRuntime`（用于倒计时/文案绑定刷新）
- `local_graph_sim_server_http.py`：HTTP 路由与监控 API（`BaseHTTPRequestHandler`）
  - `/` 监控面板（来自 `local_graph_sim_web/monitor.html`）
  - `/local_sim.js` 注入脚本（来自 `local_graph_sim_web/local_sim.js`）
  - `/ui.html?layout=<index>`：按 layout_index 切换同目录下不同 UI HTML，并注入脚本；`switch_layout` patch 会联动页面导航（或通知父级监控面板切换 iframe）
  - `/api/local_sim/poll`：轮询推进 `GameRuntime` 定时器并 drain patches，同时回传 `bindings.lv` 用于浏览器侧 `data-ui-text` 占位符刷新
  - 监控 API：`status / sync / bootstrap / trace / entities / restart / clear_trace`（均为 `Cache-Control: no-store`）
- `local_graph_sim_server_html.py`：UI HTML 辅助
  - 注入 `<script src="/local_sim.js">`、解析/合并 `lv.*` 默认值、构建 layout_index -> HTML 映射
- `local_graph_sim_server_web_assets.py`：监控面板与注入脚本的定位/读取（不在导入阶段触盘）
- `local_graph_sim_web/`：浏览器侧静态资源目录（监控面板与注入脚本）

## 依赖边界
- 允许依赖：`engine/*`、`app/runtime/*`、`app/common/*`
- 禁止依赖：`app/ui/*`、`PyQt6/*`

## 注意事项
- 本目录的服务必须保持可单测：不要在导入阶段访问磁盘或启动线程，不要依赖 Qt 对象生命周期。
- 缓存失效应提供明确入口（按 graph_id 与全量清理），避免 UI 侧维护“需要清一串缓存”的链条。
- 若服务内部使用线程池（例如隔离图资源解析错误文本），需提供显式 shutdown 入口供 UI 退出阶段调用，避免残留 worker 线程在解释器退出阶段触发不稳定行为。

