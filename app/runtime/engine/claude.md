# app/runtime/engine 目录说明

## 目录用途
- 运行时引擎适配层：提供 Graph Code 运行预设（prelude）、节点实现导入与运行期校验入口，供 UI/CLI/测试共用。
- 与 `engine/` 的纯逻辑层配合：引擎负责解析/校验/排版；本目录负责运行时需要的“装配与强约束”。

## 当前状态
- `graph_prelude_server.py` / `graph_prelude_client.py`：节点图脚本统一 prelude；导出 `GameRuntime`、端口 API、占位类型，并按 scope 注入节点函数实现（来自 V2 AST 清单）。
- `node_impl_loader.py`：运行时节点实现加载器（V2 唯一入口），按 scope（server/client）从 `plugins/nodes/<scope>/` 导入实现并导出 callable 映射。
- `node_graph_validator.py`：运行时校验入口（re-export `engine.validate.node_graph_validator`），供节点图文件内自检与装饰器使用。
- `resource_definition_validator.py`：运行期定义资源（结构体/信号/关卡变量等）校验入口；prelude 导入时会 fail-fast。
- `game_state.py` / `view_state.py`：运行态状态结构（供模拟/执行器/trace 记录使用）。
- `trace_logging.py`：trace 事件与记录器（`TraceRecorder`、`TraceEvent`）。

## 注意事项
- prelude 会在 import 阶段执行强校验与节点实现导入：不要写 `try/except` 吞错；错误应直接抛出交由上层处理。
- 节点实现清单来自 V2 AST 管线：不要在 UI/工具侧自行扫描 `plugins/nodes/**`。
- 避免在模块顶层导入 PyQt6；本目录保持无 UI 依赖，便于 CLI/测试复用。
