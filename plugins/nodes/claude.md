# 目录用途
具体节点实现的容器目录（按 `server` / `client` / `shared` 分域放置），采用“一节点一文件”。

# 公共 API
- **节点定义/发现/校验**：以 `engine.nodes.pipeline`（V2 AST 管线）解析 `plugins/nodes/**.py` 为唯一权威来源（只解析不导入）。
- **运行时节点函数导出**：由 `app.runtime.engine.graph_prelude_server` / `app.runtime.engine.graph_prelude_client` 基于 V2 AST 清单加载并注入，不在 `plugins.nodes.*` 包导入时做全量导出。

# 依赖边界
- 允许依赖：`engine/*`
- 禁止依赖：`app/*`（除运行时装配）、`assets/*`（除只读数据）

# 当前状态
- `server/`、`client/` 下的节点实现文件通过 `@node_spec` 声明元信息与端口类型；`shared/` 存放 helper。
- `plugins.nodes.server` / `plugins.nodes.client` 包级 `__init__.py` 为无副作用最小包，不再包含“扫描目录 + exec_module 导出”。

# 注意事项
- 新增/调整节点：只需新增/修改实现文件并保持 `@node_spec` 正确；节点库与索引由 V2 管线统一生成。
- 新增/调整节点后建议跑一次节点图校验与 pytest 回归，确保节点库契约与端口声明不回归。
- **禁止为通过校验而新增节点**：若节点图校验报 `CODE_UNKNOWN_NODE_CALL`，说明该 scope 的节点库中不存在该节点；应修改节点图/替换为已有节点/调整写法，而不是在 `plugins/nodes/**` 补一个同名节点来绕过。

