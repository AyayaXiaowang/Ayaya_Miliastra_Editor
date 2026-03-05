## 目录用途
V2 节点实现解析管线（只解析不导入）：发现实现文件、从 AST 抽取 `@node_spec`、标准化与校验、合并 server/client 变体、构建索引并提供查询封装。

## 当前状态
- 主流程为 discovery → extractor_ast → normalizer → validator → merger → indexer → lookup，最终产出可查询的节点定义索引与 `NodeLibrary` 封装。
- 支持“外置工作区”：当 `workspace_root/plugins/nodes` 不存在时，可回退到工具链根目录的 `plugins/nodes` 进行静态解析。
- 复合节点追加由 `composite_runner.py` 解析产出 `NodeDef`，不依赖 `CompositeNodeManager`（管理器仅负责运行期库管理与懒加载）。

## 注意事项
- 全程只解析不导入，避免导入副作用；校验为阻断式抛错，不做静默兼容。
- 类别键统一为内部标准 `类别/名称`（类别带“节点”后缀）；端口不兼容时用 `#{scope}` 变体键表达。
- scopes 推断优先基于实现文件路径（server/client），`doc_reference` 不参与推断；`plugins/nodes/shared/**` 不放置 `@node_spec` 定义。
- 类型名标准化：禁止 `Any/any/ANY/通用`，要求使用“泛型”；别名索引不得让无 `#scope` 的别名指向 scoped 变体键。

