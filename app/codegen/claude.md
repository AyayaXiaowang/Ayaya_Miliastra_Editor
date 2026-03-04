## 目录用途
`app/codegen/` 存放应用层/工具层的代码生成器：把 `engine` 产出的中立模型（如 `GraphModel`、节点库索引、复合节点配置）序列化为可运行的 Python 源码（Graph Code / 复合节点源码等）。

## 当前状态
- **稳定门面**：`executable_code_generator.py` 提供 `ExecutableCodeGenerator / ExecutableCodegenOptions` 作为对外入口；实现按职责拆分到 header/emit_graph/emit_node_call/type_inference 等模块。
- **导入策略**：生成代码默认采用 workspace bootstrap + `app.runtime.engine.graph_prelude_*`（server/client）方式导入，不再依赖资源库内的本地 prelude 文件；可选启用 `@validate_node_graph`。
- **调用生成约束**：
  - 节点/事件方法名使用 `make_valid_identifier(显示名)` 派生（运行时提供同名别名）。
  - 端口名无法作为关键字参数时，对非变参节点回退为位置参数，避免语法错误且不绕过校验规则。
  - 是否传入 `self.game` 由运行时节点函数签名决定（首参为 `game` 才传入）。
- **复合节点落盘格式**：统一生成类格式（`@composite_class`）+ JSON payload（`COMPOSITE_PAYLOAD_JSON` 多行字符串），避免 list/dict 字面量触发校验规则，并支持 UI 编辑后闭环解析/再生成。

## 注意事项
- **依赖边界**：允许依赖 `engine/*`、`plugins/*`、`app/runtime/*`；禁止依赖 `app/ui/*` 与历史 `core/*`。
- 本目录只负责生成源码字符串，不负责写文件或管理资源索引；落盘与缓存由 `engine.resources` / 上层 CLI 负责。
- 不在生成器里写“判空/存在性”分支兜底；错误应直接抛出并由调用方暴露给用户。
- 拼接 f-string 时避免在花括号表达式部分出现反斜杠转义（Python 3.11 及以下会报 `f-string expression part cannot include a backslash`）；必要时先落变量再拼接。

