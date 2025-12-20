## 目录用途
配置「定义 / Schema / 默认值」的集中地，不存放任何实例化数据或环境私有配置。

## 当前内容
- `settings.py`：全局设置类（调试选项、验证选项、布局选项、资源库刷新策略、真实执行与运行时行为开关、安全声明提示等），提供如 `LAYOUT_TIGHT_BLOCK_PACKING` 与 `DATA_NODE_CROSS_BLOCK_COPY` 这类布局行为开关、`RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED` 这类资源库自动刷新开关，以及任务清单相关的 `TODO_MERGE_CONNECTION_STEPS` 与 `TODO_GRAPH_STEP_MODE`（默认 `ai`：先创建再连接）；同时还包含 `REAL_EXEC_CLICK_BLANK_AFTER_STEP` / `REAL_EXEC_REPLAY_RECORDING_ENABLED` 等控制自动化执行收尾与回放记录行为的开关；`RUNTIME_CACHE_ROOT` 用于统一配置运行时缓存根目录（默认 `app/runtime/cache`）；设置的本地持久化文件默认落在 `app/runtime/cache/user_settings.json`。启动入口需先调用 `settings.set_config_path(workspace_root)` 注入工作区根目录，供布局/缓存等模块使用；并通过 `engine.utils.logging.logger` 输出统一格式日志；同时通过 `LAYOUT_ALGO_VERSION` 暴露布局算法语义版本号，供资源层在加载节点图缓存时判定布局语义是否兼容。
  - 布局相关补充：`LAYOUT_COMPACT_DATA_Y_IN_BLOCK` / `LAYOUT_DATA_Y_COMPACT_PULL` / `LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD` 用于控制块内数据节点 Y 轴松弛阶段的“紧凑偏好”，在满足端口下界/列内不重叠/多父区间等硬约束的前提下，尽量减少垂直空洞，使可调整的父级链条整体更紧凑。
- `resource_types.py`：资源类型枚举，统一罗列资源库中实际存在的资源类别（模板、实例、节点图、战斗预设与各类管理配置等），供资源层与上层引用，不包含额外的代码占位型资源。
- `rules/*`：节点图与运行时使用的定义 / 规则占位（例如类型占位定义、规则配置等），需保证在当前 Python 版本下可正常导入；其中 `rules/entity_rules.py` 提供实体类型、组件兼容性与实体变换校验等权威规则定义与查询接口。
- `ingame_save_data_cost.py`：局内存档数据量计算模块，基于引擎实测数据提供各字段类型的数据量开销计算能力。定义了各类型（整数、布尔值、浮点数、字符串、三维向量、GUID、配置ID等）的单值和列表开销，支持根据结构体定义和条目数量计算总数据量，并提供超限检测功能。数据量上限为 10000 点。

## 公共 API
通过 `engine` 导出用于上层注入或读取的 Schema / 常量。

## 依赖边界
- **允许依赖**：`engine/utils`
- **禁止依赖**：`app/*`、`plugins/*`、`assets/*`、`core/*`

## 注意事项
- 区分「定义（这里）」与「实例（assets/ 或 app/ 注入）」。
- 资源类型枚举 `ResourceType` 定义于 `engine/configs/resource_types.py`，供资源层与上层统一引用。
- 全局设置实例 `settings` 可从 `engine.configs.settings` 或 `engine` 顶层导入。
- `rules/` 下的占位类型 / 规则仅作为类型检查和配置 Schema 使用，不应依赖运行时副作用；同时需要考虑 Python 版本限制（例如内置不可继承类型），以免阻塞任意节点图脚本的导入。

---
注意：本文件不记录任何修改历史。请始终保持对「目录用途、当前状态、注意事项」的实时描述。
