## 目录用途
- `ugc_file_tools/graph_codegen/` 存放**外部的 Graph Code 生成器**：将 `Graph_Generater.engine` 的 `GraphModel`/IR 等中立结构序列化为可运行的 Python Graph Code。

## 当前状态
- 提供 `ExecutableCodeGenerator`：面向“节点图 Graph Code（类结构）”生成，支持按 flow edges 生成 `if/else` 控制流、推断列表/字典具体类型、以及为 GUID/配置ID 等生成必要的中文类型注解常量。
- `CompositeCodeGenerator` 不在本目录重复实现：统一复用主程序的 `app.codegen.CompositeCodeGenerator`（单一真源），本目录仅保留薄转发以兼容旧导入路径。

## 注意事项
- 本目录属于工具层：允许依赖 `Graph_Generater/engine/*` 与 `Graph_Generater/app/runtime/*`，但**不要把解析 `.gil/.json` 的逻辑放进来**（解析应留在 `ugc_file_tools/` 的 parser/loader 脚本中）。
- 生成器应保持“可静态校验闭环”：生成后的 Graph Code 必须能被 `engine.validate` 校验通过。

