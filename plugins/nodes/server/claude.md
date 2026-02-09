目录用途

- 存放服务器侧节点实现（Server），采用“一节点一文件”，按类别分子目录（事件节点/执行节点/查询节点/流程控制节点/运算节点等）。
- 每个节点实现为一个函数，使用 `@node_spec` 装饰器声明元信息与端口类型。

当前状态

- 包级 `__init__.py` 为无副作用最小包，不再做“扫描目录 + 动态导出”。运行时节点函数导出统一由 `app.runtime.engine.graph_prelude_server` 负责（基于 V2 AST 清单加载并注入）。
- 共享实现统一放在 `plugins.nodes.shared.*`，节点文件直接从该命名空间导入 helper。
- 包根目录提供 `__init__.pyi` 类型桩文件（仅供静态类型检查/IDE 补全，运行时不参与导入），由 `app.cli.graph_author_tools generate-node-stubs` 从 `NodeRegistry/NodeDef` 自动生成：包含节点函数名、输入端口参数名与类型，以及返回值形态，降低 Graph Code 写作的拼写风险。

注意事项

- 仅在节点实现函数上使用 `@node_spec`，函数命名保持与“节点名称”一致，避免难以追踪。
- 辅助方法统一放入 `plugins/nodes/shared/`；节点文件内避免与节点无关的逻辑。
- 新增/调整节点后建议跑一次节点图校验与 pytest 回归，确保节点库契约与端口声明不回归。
- **禁止为通过校验而新增节点**：节点图校验报 `CODE_UNKNOWN_NODE_CALL` 表示该 server 作用域的节点库不存在该节点；必须改节点图/换已有节点，不允许通过新增 `plugins/nodes/server/**` 同名节点来绕过。

