# runtime/engine

## 目录用途
运行时引擎模块，包含节点图执行所需的核心运行时环境和执行器。

## 当前状态
包含以下核心组件：
- `game_state.py`：游戏状态管理（变量系统统一写入辅助、实体系统、事件系统自动清理、Mock系统），同时内建 `TraceRecorder` 记录变量写入与事件触发。
- `node_executor.py`：节点执行器基类（支持追踪、断点、循环保护），执行时输出结构化追踪事件（起止时间、调用栈、结果类型）。
- `trace_logging.py`：提供 `TraceRecorder` / `TraceEvent`，用于统一收集运行期的节点执行与信号事件。
- `node_graph_validator.py`：节点图代码规范验证入口（re-export `engine.validate.node_graph_validator`），支持按文件一次性缓存与运行时开关
- `view_state.py`：视口/画布映射（S→V），维护 scale 与 canvas_to_viewport_offset
- `graph_prelude_server.py` / `graph_prelude_server.pyi`：Server 侧节点图前导脚本（最小化导入，`.pyi` 为类型桩，向编辑器透出节点函数与占位类型，消除“函数名标黄”）
  - 透出 `engine.graph.composite.pin_api` 提供的 `流程入/流程出/数据入/数据出` 等辅助函数，供复合节点自动引脚声明使用。
- `graph_prelude_client.py`：Client 侧节点图前导脚本（最小化导入，与 server 版保持等价导出，包括 `pin_api` 与 `validate_node_graph`）
- `node_impl_loader.py`：运行时节点实现加载器（V2 唯一入口），按作用域加载节点实现并导出；同时为节点显示名自动注入“可调用别名”（`name.replace("/", "")` 与 `make_valid_identifier(name)`），确保 Graph Code/导出代码可稳定调用包含特殊字符的节点。

## 注意事项
- 本目录仅包含可执行代码，不存放缓存数据
- 缓存数据统一存放在 `runtime/cache/` 目录下
- 从外部导入时使用 `from runtime import GameRuntime` 或 `from runtime.engine import ...`
- 节点图代码推荐仅使用一行导入：`from runtime.engine.graph_prelude_server import *`，严格校验可通过 `validate_node_graph` 或运行时验证开关配合使用

## 异常处理约定
- 运行时不使用 `try/except` 吞没错误；事件与节点执行中的异常直接抛出，便于快速暴露与定位问题。


