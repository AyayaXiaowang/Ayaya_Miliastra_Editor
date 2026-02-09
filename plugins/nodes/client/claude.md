目录用途

- 存放客户端侧节点实现（Client），采用“一节点一文件”，按类别分子目录（事件节点/执行节点/查询节点/流程控制节点/运算节点等）。
- 每个节点实现为一个函数，使用 `@node_spec` 装饰器声明元信息与端口类型。

当前状态

- 包级 `__init__.py` 为无副作用最小包，不做“扫描目录 + 动态导出”；运行时节点函数导出统一由 `app.runtime.engine.graph_prelude_client` 负责（基于 V2 AST 清单加载并注入）。
- 共享实现统一放在 `plugins.nodes.shared.*`，节点文件直接从该命名空间导入 helper。
- 包根目录提供 `__init__.pyi` 类型桩文件（仅供静态类型检查/IDE 补全，运行时不参与导入），由 `app.cli.graph_author_tools generate-node-stubs` 从 `NodeRegistry/NodeDef` 自动生成：包含节点函数名、输入端口参数名与类型，以及返回值形态，降低 Graph Code 写作的拼写风险。

注意事项

- 严格按照节点规范定义输入/输出端口与参数校验。
- 辅助方法统一放入 `plugins/nodes/shared/`；节点文件内避免与节点无关的逻辑。
- 资源路径通过统一资源管理访问，不要硬编码绝对路径。
- **禁止为通过校验而新增节点**：节点图校验报 `CODE_UNKNOWN_NODE_CALL` 表示该 client 作用域的节点库不存在该节点；必须改节点图/换已有节点，不允许通过新增 `plugins/nodes/client/**` 同名节点来绕过。

