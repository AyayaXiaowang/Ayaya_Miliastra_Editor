## 目录用途
- 客户端与服务端共享的节点实现片段、通用类型与工具函数，作为两端的公共依赖。

## 当前状态
- 提供 `client_*_impl_helpers.py` / `server_*_impl_helpers.py` 等共享辅助模块。
- 依赖 `engine.nodes.node_spec` 与 `engine.utils.loop_protection`（循环保护等），不依赖 `app/*`、UI/系统 API、无平台特定逻辑。

## 注意事项
- 保持模块的无副作用导入；不要在导入时读取外部资源或环境变量。
- 公共常量与类型需稳定，变更需同步两端调用方。
- 本目录仅存放 shared helper，不存放 `@node_spec` 节点实现；禁止为通过节点图校验而在此（或两端节点目录）补节点绕过。
