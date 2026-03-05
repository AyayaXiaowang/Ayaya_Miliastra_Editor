## 目录用途
存放 Todo 相关测试：覆盖任务清单的核心纯逻辑（当前步骤解析、执行规划、预执行提醒、刷新恢复），以及与端口语义常量过滤等规划细节，保证 Todo 行为稳定且可回归。

## 当前状态
- `test_todo_core_logic.py`：围绕 `TodoItem/CurrentTodoContext` 与核心解析/规划函数构造最小用例，覆盖当前 Todo 决策顺序、模板/事件流根回溯、单步执行错误分支与识别补写规划等。
- `test_todo_execution_service.py`：回归 `TodoExecutionService` 的执行规划行为（truncate、从事件流续跑、非支持类型返回错误等）。
- `test_todo_execution_preflight_warning.py`：回归执行前提醒扫描规则（按 graph_id 过滤 todo_map，并识别信号/结构体/复合节点相关步骤）。
- `test_todo_refresh_restore.py`：回归刷新后“恢复当前选中步骤”的优先级规则（selected_todo_id → current_todo_id → detail_info 全量匹配 → graph_id 兜底）。
- `test_dynamic_port_steps_semantic_constant_filtering.py`：回归动态端口步骤常量参数过滤规则（隐藏稳定 ID 不暴露到通用参数配置步骤）。
- `test_todo_detail_viewmodel.py`：回归 Todo 详情与富文本 tokens 的结构化生成规则（颜色/背景/计数等）。
- `test_todo_detail_info_schema.py`：回归 `detail_info` schema 的声明完整性与基础校验行为（新增 detail_type 必须补齐 schema，否则测试失败）；并额外覆盖动态端口步骤类 detail_type，避免因生成侧使用变量赋值而漏过静态扫描。
- `test_todo_ports_contracts.py`：回归 Todo Ports/Protocols 的运行时合同（monitor port 结构校验）。
- `test_step_type_registry_completeness.py`：回归 Todo 图步骤 detail_type 的“声明完整性”（预览 handler / 详情 builder 中引用到的图步骤类型必须出现在 `StepTypeRules/TodoStyles` 的声明集合里）。

## 注意事项
- 优先保持纯逻辑测试，不依赖主窗口与真实资源库。
- 如需最小 UI 组件回归（例如 QTreeWidget 高亮），应放入 `tests/ui/`。
- 如需仓库根目录（repo root / workspace_root），统一使用 `tests._helpers.project_paths.get_repo_root()`，避免在测试文件里写 `Path(__file__).parents[...]`（测试分目录后深度会变化）。


