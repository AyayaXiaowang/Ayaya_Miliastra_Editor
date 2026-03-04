## 目录用途
块级布局算法与数据结构：负责识别基本块、分析块间关系，并在给定全局布局上下文中计算块内/块间几何（流程节点 + 数据节点）。

## 当前状态
- **两阶段布局**：`BlockIdentificationCoordinator`（阶段1：仅识别流程块/事件流）+ `BlockLayoutExecutor`（阶段2：在全局复制完成后放置数据节点并分配坐标）。
- **块内上下文**：`BlockLayoutContext` 以 `LayoutContext` 为全局只读索引来源；在跨块复制/增量写边场景可切换为 copy-on-write 边索引视图（`EdgeListProxy` 等），避免整图深拷贝并保证后续块能看到前序变更。
- **共享图语义**：流程口/数据口判定、事件流遍历与数据链查询统一复用 `engine.utils.graph.*` 与 `engine.layout.utils.graph_query_utils`，本目录只保留块级编排与最少必要状态。
- **数据节点归属原则**：数据节点分配到“首次实际消费它的块”；跨块共享通过复制/重定向实现，语义敏感的查询节点可被列入禁止复制集合。
- **确定性**：块识别采用 BFS 生成稳定块序号；所有会影响对齐/收敛的遍历必须稳定排序（如按 `LayoutBlock.order_index`）。

## 注意事项
- 仅关注块抽象与布局算法，不引入 `app/*`、`plugins/*`、`assets/*` 依赖；基础类型统一从 `engine.layout.internal` 导入。
- 新增工具函数优先放到 `engine/layout/utils`，避免本目录膨胀为“工具杂货铺”。
- 流程环路防御：块识别阶段检测到重复 node_id 会停止前进并把该节点视为块终点；依赖环路表达的结构应通过后续块与 `last_node_branches` 展开。
- 为保证可复现，禁止依赖 `set` 的迭代顺序；必要时引入显式排序键。


