# 目录用途
运行期可写区与运行时适配层，集中管理缓存、轻量运行时组件（如 `GameRuntime`、前导脚本与运行时校验器）以及编辑器自身的短期状态数据。

# 目录结构
- `cache/`：所有运行期缓存与 UI 会话状态统一存放位置
  - `graph_cache/`：节点图持久化缓存，用于在不修改源码的前提下记住最近一次布局结果
  - `resource_cache/`：资源索引缓存与节点库缓存，加速启动与资源浏览
  - `node_cache/`：节点库缓存（与 `engine.nodes` 的解析结果相关）
  - `name_sync_state.json`：资源文件名同步状态
  - `ui_last_session.json`：主窗口 UI 会话状态快照（当前视图模式、各库页选中项、任务清单上下文等），编辑器关闭时写入，下次启动时用于恢复到上一次看到的页面与选中上下文，不包含任何大体量图数据或长期配置；读写统一通过 `app.runtime.services.json_cache_service.JsonCacheService`。
  - `player_ingame_save_selection.json`：战斗预设“玩家模板-自定义变量_局内存档变量”页记忆当前玩家模板使用的局内存档模板选择（按玩家模板 ID 存储），便于下次打开沿用；读写统一通过 `JsonCacheService` 的 KV 模式（schema_version + values），兼容旧版存储结构。
- `todo_states/`：项目存档任务清单的勾选状态（每个存档一个 JSON），仅供编辑器 UI 使用，不参与项目存档导出，清理后只会重置任务完成度
- `engine/`：运行时引擎组件（GameRuntime、前导脚本、节点图运行时验证等）
- `services/`：运行时服务（无 PyQt6 依赖），收敛“资源加载/缓存/领域计算”等可测试逻辑，供 UI 与控制器复用

# 公共 API
- 运行时节点图验证入口：`app.runtime.engine.node_graph_validator.NodeGraphValidator` 与装饰器 `validate_node_graph`
  - NodeGraphValidator：基于文件粒度委托 `engine.validate.validate_files` 执行校验
  - validate_node_graph：在定义节点图类时进行一次性验证，可作为装饰器或直接调用
- 节点图前导脚本：`app.runtime.engine.graph_prelude_server` / `app.runtime.engine.graph_prelude_client` 同步暴露 `GameRuntime`、`pin_api` 以及 `validate_node_graph`
- UI 会话状态工具：`app.runtime.ui_session_state` 提供简单的 `load_last_session_state` / `save_last_session_state`，由主窗口调用以读写 `ui_last_session.json`。
- 运行期 JSON 缓存门面：`app.runtime.services.json_cache_service.JsonCacheService` 统一收敛 runtime_cache_root 派生、JSON 读写与 KV 存储模式，避免 UI 侧自行拼路径与手写落盘逻辑。

# 依赖边界
- 允许依赖：`engine/*`、`plugins/*`
- 禁止依赖：`assets/*`（除只读）

# 当前状态
- `cache/` 与 `todo_states/` 目录按需生成，已在 `.gitignore` 覆盖范围内；清空后仅会重建缓存、会话状态与勾选状态，不影响资源库与项目存档。
- `ui_last_session.json` 与 `ui_session_state.py` 在主窗口关闭与启动时自动读写，文件位于 `app/runtime/cache/ui_last_session.json`，不存在时会按默认结构生成。
- `app/runtime/engine` 下的前导脚本、运行时验证器与 `GameRuntime` 已与当前 `engine` API 同步，节点图运行期校验与导出路径以本目录为唯一入口。

# 注意事项
- 顶层 `runtime/` 是仓库运行期缓存目录（历史遗留/兼容部分工具输出），不是 Python 包；代码与生成器应统一使用 `app.runtime.*` 作为运行时模块入口
- `cache/` 是**数据目录**：不得放置任何 Python 源码文件（尤其不要添加 `__init__.py`），避免将运行期数据区误做成可导入包
- 所有缓存与 UI 会话状态文件默认位于 `app/runtime/cache/*`；如需挪到工作区外或统一到其它目录，请通过 `engine.configs.settings.settings.RUNTIME_CACHE_ROOT` 配置，并在代码中统一使用 `engine.utils.cache.cache_paths` 派生路径
- 可写数据与缓存应可清理：删除 `app/runtime/cache/`（或按需清理其子目录）后不会破坏任何资源库与项目存档，只会重置缓存与 UI 会话状态
- 不存放长期配置与发布资源，仅存放运行期生成与状态数据
- 规则类型与占位类型导入统一从 `engine.configs.rules.*` 引入（不要使用 `engine.validate.rules.*`）
- `GameRuntime` 负责在实体销毁时同步清理事件、定时器与挂载节点图，确保运行期状态可回收
- 文档字符串与注释中的“工作区根目录”统一称为 `workspace_root`（不绑定具体仓库目录名）。