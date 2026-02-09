# runtime/engine

## 目录用途
运行时引擎模块，包含节点图执行所需的核心运行时环境和执行器。

## 当前状态
包含以下核心组件：
- `game_state.py`：游戏状态管理（变量系统统一写入辅助、实体系统、事件系统自动清理、Mock系统），同时内建 `TraceRecorder` 记录变量写入与事件触发。
  - 额外提供 UI 离线模拟状态：记录 `switch_layout/set_widget_state/activate_widget_group/remove_widget_group` 等 UI patch，供本地测试回显按钮显隐/状态切换（不代表真实游戏 UI）。
  - 内建离线定时器驱动：`start_timer_sequence + tick()` 会按“定时器序列/循环次数”语义触发事件 `定时器触发时`，用于本地测试的倒计时/状态机推进
  - 支持配置在场玩家数量：维护并复用 `玩家1..玩家N` 实体列表，供 `获取在场玩家实体列表` 与多人等待/投票门槛逻辑使用
  - UI 绑定根实体追踪：当写入 `UI*` 自定义变量时记录根实体 ID，供本地测试向浏览器侧回传 `bindings.lv`（倒计时等文本刷新）
  - UI 默认值注入：支持从 UI HTML 注入 `lv.*` 默认值映射；当节点图首次读取缺失的 `UI*` 自定义变量时会自动补齐默认结构（尤其是字典变量），避免“对字典写 key”变成 no-op
  - 兼容“按数值 GUID 查询实体”的离线语义：`get_entity(int_guid)` 会按需创建并缓存 `MockEntity(entity_id=str(guid))`，用于跑通节点图中常见的 `以GUID查询实体` 流程（仅用于离线模拟/教学）。
- `node_executor.py`：节点执行器基类（支持追踪、断点、循环保护），执行时输出结构化追踪事件（起止时间、调用栈、结果类型）；其中 `LoopProtection` 已下沉到 `engine.utils.loop_protection`，此处仅保持旧导入路径可用（re-export）。
- `trace_logging.py`：提供 `TraceRecorder` / `TraceEvent`，用于统一收集运行期的节点执行与信号事件。
- `node_graph_validator.py`：节点图代码规范验证入口（re-export `engine.validate.node_graph_validator`），支持按文件一次性缓存与运行时开关
- 额外提供 `validate_file_cli(__file__)`：节点图脚本可在 `__main__` 中一行调用完成“校验 + 文本报告 + 退出码”；校验前会通过 `ensure_settings_workspace_root(load_user_settings=True)` 加载用户设置（对齐 UI 的自动排版/relay 等开关），通过时也会打印警告明细；文本报告统一复用 `engine.validate.node_graph_validator.format_validate_file_report`，确保与 `app.cli.graph_tools validate-file` 输出口径一致（Windows 下统一 UTF-8 输出）。
- `view_state.py`：视口/画布映射（S→V），维护 scale 与 canvas_to_viewport_offset
- `graph_prelude_server.py` / `graph_prelude_server.pyi`：Server 侧节点图前导脚本（最小化导入，`.pyi` 为类型桩，向编辑器透出节点函数与占位类型，消除“函数名标黄”）
  - 透出 `engine.graph.composite.pin_api` 提供的 `流程入/流程出/数据入/数据出` 等辅助函数，供复合节点自动引脚声明使用。
  - 同时透出 `GraphVariableConfig`，使节点图文件无需再单独 import 变量声明类型
- `shared_composites_server.pyi`：共享复合节点扩展语法糖的类型桩（仅用于补全/静态检查），由内部生成流程从 `assets/资源库/共享/复合节点库/**/*.py` 自动生成。
- `graph_prelude_client.py`：Client 侧节点图前导脚本（最小化导入，与 server 版保持等价导出，包括 `pin_api` 与 `validate_node_graph`）
- `resource_definition_validator.py`：运行期“代码级资源定义”强校验入口：在节点图前导脚本导入阶段统一校验结构体/信号/关卡变量定义（发现错误直接抛出），避免资源定义错误在运行期潜伏。
- `node_impl_loader.py`：运行时节点实现加载器（V2 唯一入口），按作用域加载节点实现并导出；workspace_root 推断统一使用 `engine.utils.workspace.resolve_workspace_root`，避免与 CLI/校验入口口径漂移；同时为节点显示名自动注入“可调用别名”（`name.replace("/", "")` 与 `make_valid_identifier(name)`），确保 Graph Code/导出代码可稳定调用包含特殊字符的节点。

## 注意事项
- 本目录仅包含可执行代码，不存放缓存数据
- 缓存数据统一存放在 `app/runtime/cache/`（以 `settings.RUNTIME_CACHE_ROOT` 为准，默认落点为 `app/runtime/cache`）
- 从外部导入时使用 `from app.runtime import GameRuntime` 或 `from app.runtime.engine import ...`
- 节点图代码推荐仅使用一行导入：`from app.runtime.engine.graph_prelude_server import *`（或 client 版），严格校验可通过 `validate_node_graph` 或运行时验证开关配合使用

## 异常处理约定
- 运行时不使用 `try/except` 吞没错误；事件与节点执行中的异常直接抛出，便于快速暴露与定位问题。


