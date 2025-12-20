## 目录用途
`app/codegen/` 存放**应用层/工具层**使用的代码生成器：把 `engine` 产出的中立产物（`GraphModel`/IR/节点库索引结果）序列化为可运行的 Python 源码（节点图 Graph Code、复合节点函数/类代码等）。

## 依赖边界
- 允许依赖：`engine/*`、`plugins/*`、`app/runtime/*`（以 `runtime.*` 顶层导入形式使用）
- 禁止依赖：`app/ui/*`（避免把 UI 逻辑引入生成器）、`core/*`

## 当前状态
- 节点图导出与复合节点导出的“可执行/可运行”代码生成器已迁入本目录；`engine` 不再包含运行时绑定的生成逻辑。
- 生成代码默认采用 `runtime.engine.graph_prelude_*`/资源库 `_prelude.py` 的导入策略：上层可通过参数选择导入模式、选择 server/client 预设以及是否启用 `@validate_node_graph`（校验入口默认指向 `engine.validate.node_graph_validator`）。
- 为避免 `ui.*` 与 `app.ui.*` 双导入，节点图/复合节点生成代码在 workspace_bootstrap 策略下只注入 `PROJECT_ROOT` 与 `ASSETS_ROOT` 到 `sys.path`，不注入 `<repo>/app`。
- 可执行节点图代码生成在遇到“端口名无法作为 Python 关键字参数名”的情况（例如包含括号、斜杠等）时，会对**非变参节点**自动回退为**位置参数**生成，避免产生语法错误并保持通过节点图校验规则（禁止 `{}` 字面量绕路）。
- 节点调用名统一以 `make_valid_identifier(节点显示名)` 派生（运行时会导出同名别名），从而支持节点显示名包含 `/`、`：`、括号等字符时仍可在 Graph Code 中作为合法函数调用出现。
- 是否传入 `self.game` 由运行时节点函数签名决定：仅当首参为 `game` 时才传入，避免纯查询类节点因多传参数导致运行时报错。
- 事件处理方法名同样使用 `make_valid_identifier` 派生，并在“监听信号”场景下以绑定的 `signal_id` 作为事件名与方法后缀，保证 `register_handlers` 与 `on_<事件>` 方法名一致。
- 复合节点源码落盘统一生成**类格式（@composite_class）+ JSON payload**：文件内以 `COMPOSITE_PAYLOAD_JSON`（多行字符串）承载 `CompositeNodeConfig.serialize()`，避免触发复合节点校验规则中的“禁止 list/dict 字面量”，并确保 UI 可视化编辑后可闭环落盘与再次解析/校验。

## 注意事项
- 本目录只负责生成源码字符串，不负责写文件或管理资源索引；落盘与缓存由 `engine.resources`/上层 CLI 负责。
- 不在生成器里写判空/存在性分支来“兜底”，错误应直接抛出并由调用方暴露给用户。
- 生成器内部使用 f-string 拼接调用表达式时，避免在花括号表达式部分写带反斜杠的转义字符串（Python 3.11 及以下会触发 `SyntaxError: f-string expression part cannot include a backslash`）；必要时先把值写入变量再拼接；空字符串字面量统一用 `'""'`。

---
注意：本文件不记录变更历史，仅描述目录用途、当前状态与注意事项。


