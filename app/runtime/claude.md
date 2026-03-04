## 目录用途
运行期可写区与运行时适配层：集中管理缓存、轻量运行时组件（前导脚本、运行时校验器等）以及编辑器短期状态数据。

## 当前状态
- `cache/`：运行期缓存与 UI 会话状态（如 `graph_cache/`、`resource_cache/`、`node_cache/`、`ui_last_session.json` 等），按需生成且默认被忽略。
- `todo_states/`：任务清单勾选状态（每个项目存档一份），清理后仅影响完成度显示。
- `engine/` 与 `services/`：运行时相关的引擎适配与可测试纯逻辑服务（无 UI 依赖）。

## 注意事项
- `cache/` 属于数据目录：不得放置 Python 源码（尤其不要添加 `__init__.py`），避免把缓存区误变成可导入包。
- 仓库根目录的 `runtime/`（若存在）是历史遗留数据目录，不是 Python 包；代码统一使用 `app.runtime.*` 作为运行时模块入口。
- 运行时路径应由 `engine.configs.settings` / `engine.utils.cache` 派生，避免在各处手写拼路径。
- 缓存应可清理：删除 `app/runtime/cache/` 不应破坏资源库与项目存档，只会重建缓存与会话状态。

