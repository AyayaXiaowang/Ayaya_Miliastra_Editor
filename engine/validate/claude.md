## 目录用途
引擎侧验证层（纯逻辑）：提供节点图/复合节点/项目存档等校验与可选 QuickFix 能力，统一输出结构化 Issue（`EngineIssue` / `ValidationIssue`）。

## 当前状态
- **稳定入口**：上层通过 `engine.validate.api.validate_files`、`ComprehensiveValidator`、`RoundtripValidator` 等调用；CLI 仅做包装（如 `app.cli.graph_tools`）。
- **目标收集与报告**：`graph_validation_targets` 负责扫描目标与路径归一化；`graph_validation_cli_runner` / `graph_validation_cli_reporting` 负责 `validate-graphs` 的编排与输出（含 `--json`）。
- **退出码语义**：`validate-graphs` 默认 **仅 error 视为失败**（exit code=1）；warning/info 会完整输出但不阻断（exit code=0）。
- **作用域切换**：批量校验由 `graph_validation_orchestrator.collect_validate_graphs_engine_issues(...)` 按资源根目录分组切换 `active_package_id`，并刷新 NodeRegistry + 代码级 Schema 作用域，避免跨项目存档混扫串包。
- **单文件入口**：`node_graph_validator` 提供 `validate_file/strict_parse_file` 与类装饰器入口；收集与文本报告格式化逻辑收敛在 `node_graph_validation_utils.py`（用于在纯文本模式下输出更可定位的信息，如 error code、行号范围与少量源码片段）。
- **严格语义对齐**：
  - 普通节点图：IR 建模错误（`GraphModel.metadata["ir_errors"]`）与结构校验（`validate_graph_model`）会在验证阶段提升为 error，保证与 UI 严格加载口径一致。
  - 复合节点：除 AST/pin_marker 规则外，还会解析复合子图并执行结构校验、虚拟引脚映射校验与流程连通性校验，避免“校验通过但 UI 出现空白引脚/孤立流程口”的漂移。
- **端口类型一致性**：复合节点源码与普通节点图统一执行端口类型匹配与同型输入约束，确保 `拼装列表/拼装字典` 等变参节点在复合节点内同样可被静态拦截明显类型错误。
- **可选 QuickFix**：`graph_validation_quickfixes` 与 `struct_definition_quickfixes` 默认关闭，仅在 CLI `--fix/--fix-dry-run` 明确启用时执行。
- **命名长度硬约束**：自定义变量名与节点图变量名长度上限为 **20 字符**；超长在源码校验与存档综合校验中均会报错。

## 注意事项
- 允许依赖：`engine/nodes`、`engine/graph`、`engine/utils`、`engine/configs`；禁止引入 `plugins/*`、`app/*`、`assets/*`。
- 不使用 try/except 吞错；异常直接抛出或以 Issue 返回。
- **禁止为通过校验而补节点**：遇到 `CODE_UNKNOWN_NODE_CALL` 等错误应改图/改写法/调整 scope，不允许在 `plugins/nodes/**` 加节点绕过。
- 修改节点图/复合节点或生成链路后，必须跑一次配套验证工具闭环确认。

