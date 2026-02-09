## 目录用途
块级布局算法与数据结构：负责识别基本块、分析块间关系，并在给定全局布局上下文中计算单个或多个块的几何信息。

## 当前状态
- `BlockLayoutContext.should_place_data_node()` 使用 `_block_data_nodes_set` 标记判断是否已通过 `set_block_data_nodes()` 设置数据节点集合，避免空集合被误判为"未设置"而回退到旧逻辑。
- 聚合所有以 `block_*.py` 命名的布局实现模块，例如块识别、块布局上下文、块布局内部算法与工具等。
- **新两阶段布局流程**：`BlockIdentificationCoordinator` 和 `BlockLayoutExecutor` 支持分阶段调用：
  - 阶段1：`identify_blocks_flow_only()` / `identify_flow_only()` - 只识别流程节点，创建LayoutBlock框架
  - 阶段2：`layout_block_data_phase()` / `layout_data_phase()` - 在全局复制完成后，放置数据节点并计算坐标
- `BlockLayoutContext` 新增 `set_block_data_nodes()` 和 `should_place_data_node()` 方法，由全局复制管理器在阶段2设置该块应放置的数据节点集合。
- 通过 `engine.utils.graph.graph_utils` 统一判断流程口/数据口语义，避免在块逻辑里重复维护图规则。
- 块识别阶段的事件流收集直接复用 `engine.utils.graph.graph_algorithms`，保持与解析层一致的遍历语义。
- 暴露对外的接口仅依赖于 `layout/internal` 提供的上下文数据类型与配置，不直接访问 UI 或资源层。
- 数据链 BFS、深度遍历等行为统一复用 `layout/utils/graph_query_utils`，本目录仅保留端口序列等轻量工具。
- `BlockLayoutContext` 在链重算时仅重置链状态，默认直接复用全局只读索引；当启用跨块复制时改为使用共享的可写边索引视图（copy-on-write），上一块的副本和重定向立刻对后续块可见，同时避免整张图的列表深拷贝；copy-on-write 视图通过 `EdgeListProxy` 懒复制列表，仅在发生写操作时才克隆对应节点的边集合，读取阶段保持零额外分配。
- 无需共享可变索引时，`BlockLayoutContext` 的数据/流程边查询直接委托 `LayoutContext` 的只读 API，确保多处复用同一份缓存，减少图索引的重复维护。
- 当全局复制阶段修改了图模型（新增副本/重定向数据边）后，协调器会刷新 `BlockLayoutExecutor` 内缓存的 `BlockLayoutContext` 对全局 `LayoutContext` 的引用并重建索引，确保阶段2读取到最新的数据边索引。
- `BlockLayoutContext` 总是持有一份 `LayoutContext` 以供端口排序和高度估算使用，彻底移除线性扫描式的端口索引 fallback。
- `BlockLayoutContext` 仅维护节点槽位、链编号与必要的映射缓存，保持最小化状态面，并新增 `pending_copy_sources` 集合记录尚未复制的跨块数据节点；当启用共享边索引时会停用全局 `LayoutContext` 的边访问，`get_data_in_edges` / `get_data_out_edges` / `iter_out_data_edges` 直接读取 copy-on-write 视图，复制产生的节点和边可在首轮排版即时生效，避免同一张图同时维持两份缓存。
- 即便启用共享边索引，`BlockLayoutContext` 也会将 `_global_edge_api` 绑定到全局 `LayoutContext`，`is_pure_data_node` 始终复用缓存而不退回 O(E) 逻辑。
- `BlockLayoutContext` 内置节点高度缓存，块内算法（坐标计算、边界归一化、堆叠排序）共享同一份估算结果，避免在大图中反复调用高度函数。
- 启用跨块数据复制时，识别协调器会维护一份共享索引副本（来源于 `LayoutContext`），并在块内操作时原地更新，既避免重复构建又保持增量一致；事件推断仍复用全局上下文只读视图。
- 事件根信息在块识别阶段集中缓存，避免每个块重复 BFS，保持块内调试信息与事件流元数据同步。
- `BlockIdentificationCoordinator` 复用编排器预计算的事件 ID→标题映射，仅孤立流程会回退到 `_resolve_event_metadata`，并将 `_layout_block_internal` 拆分为“上下文准备 + 布局管线”两个私有方法，便于维护。
- `_BlockLayoutScalars` 在上下文构建与布局管线中只计算一次并复用，几何常量保持一致。
- 块内几何标量（如槽位宽度 slot_width、数据节点堆叠间距、flow→data 安全间隔、端口→data 安全间隔）会读取 `settings.LAYOUT_NODE_SPACING_X_PERCENT/LAYOUT_NODE_SPACING_Y_PERCENT` 的倍率，仅缩放“间隙常量”来调节相邻节点之间的空白距离，不改变节点本身宽高估算。
- 核心层已经提供事件→流程节点的完整映射时，`BlockIdentificationCoordinator` 直接读取映射并跳过图级 BFS，避免在块识别阶段重复遍历；事件标题查找表也由编排器构建后传入，彻底消除重复的 `build_event_title_lookup`。
- 事件标题回退统一使用 `graph_query_utils.resolve_event_title` 与共享的 `build_event_title_lookup` 映射，块识别与核心保持一致的命名策略。
- `BlockIdentificationCoordinator` 构造参数与核心布局常量一一对应，不包含重复或未使用项，便于编排层按统一配置注入。
- `BlockIdentificationCoordinator` 采用 **BFS（按块层级）** 识别流程块，并通过自增 `_block_sequence` 生成稳定块序号；兄弟分支不会因 DFS 深度优先而被推到很靠后的 `order_index`，避免分支初始化节点落到最后块。
- `BlockIdentificationCoordinator` 每次构造都会重建 `_layout_y_debug_info`，即使 UI 未开启调试叠加也能获得完整的节点调试映射，随开随用。
- `_layout_block_internal` 返回的数据节点集合基于 `context.data_nodes_in_order` 去重展开，纯生产但暂未被本块消费的节点也会写入 `global_visited`，跨块复制时能准确识别边界。
- `DataNodePlacer` 在消费完链指令后，直接处理 `pending_copy_sources` 集合中剩余的跨块节点并触发复制，无需再遍历整块节点输入，保证“仅用于后续块”的查询节点也能在本块创建镜像。
- `DataNodePlacer` 执行复制计划或降级放置后会立即清理对应的 `pending_copy_sources`，失败时也会回落到共享视图放置并同时标记 pending 状态，确保兜底阶段不再重复复制同一节点。
- `BlockPositioningEngine` 与 `CoordinateAssigner` 共同复用 `layout/utils/longest_path.resolve_levels_with_parents` 处理块列索引与流程槽位，最长路径与残余补偿逻辑保持一致，便于集中优化。
- `BlockPositioningEngine` 基于块级 DAG 直接跑最长路径求列索引，并借助垂直 bucket 索引筛选潜在重叠块，bucket 高度由块间距与节点高度动态推导，将“入口间距 + 矩形重叠”检查从 O(N²) 降到与局部块数相关；是否在满足约束后继续左移由 `enable_tight_block_spacing` 控制，可由上层设置面板配置。
- `BlockPositioningEngine` 会补全“任意节点ID → LayoutBlock”的映射（含 data 节点），使块间 X/列索引求解能基于跨块 data 依赖建立约束；当 `LAYOUT_TIGHT_BLOCK_PACKING` 关闭时，列索引阶段会把跨块 data 边也视作依赖边，从根源避免出现右→左折返线（跳过 `PORT_EXIT_LOOP`/“跳出循环”回边）。
- `BlockPositioningEngine` 的列内堆叠阶段采用 **全局 Y 轴迭代收敛**：先按列初始堆叠得到每块 top_y，再基于“多父合流/多子分叉”的目标中心点反复松弛；每轮在列内通过 forward/backward 约束传播保证严格不重叠，并把“无强约束块”尽量向上紧凑堆叠，为需要居中的块让出空间，从而在复杂图里也能稳定逼近“居中 + 不重叠”的解。
- `BlockPositioningEngine` 的 Y 轴迭代在“事件组内不存在任何对齐/居中目标约束”的场景会被跳过：该场景下迭代最终会收敛到初始紧凑堆叠的同一解，跳过不会改变排版结果，只减少开销。
- `BlockPositioningEngine` 的 Y 轴目标除了多父/多子外，还包含 **单父对齐**：当块只有一个父块时，会尝试把该块的垂直中心对齐到父块中心，避免“7->8 单线但 8 被堆到同列顶部（跑到右上方）”这类现象；最终仍以列内不重叠约束为硬约束。
- `BlockPositioningEngine` 对“互为唯一父子”的单连线（父块唯一子块=该子块，且子块唯一父块=该父块）提供 **top_y 强制对齐**：在主迭代收敛后，把整条“唯一父子链”视作一个组件，取链内当前最大的 top_y 作为对齐目标，并将链上其它块 **仅向下** 平移到该 top_y（不做上移）；从而既满足“7 和 8 只有这一条有效连线 → 必须同一高度”，也允许“入口块跟随链条整体下移”以满足分叉居中（例如 1->2 且 2->3/4 时，2 先居中 3/4，1 再下移对齐 2）。
- `BlockPositioningEngine` 对“父块多分叉”的场景会为子块生成**分叉组目标 top_y**：当子块为单父且其父块拥有多个子块时，按端口顺序用子块自身高度堆叠出一个“子块组”，并让该组的垂直中心对齐到父块中心，从而满足“10 连 11/13 → 10 在它们中间（且子块围绕父块展开）”的排版期望；列内不重叠仍为硬约束，必要时会整体下移让位。
- `BlockPositioningEngine` 在列内初始顺序上会对“父块多分叉的单父子块”做轻量重排：子块在目标列中按父块端口顺序排列；该重排是**局部互换**（仅在这些子块原本占据的槽位内重排，不越过其它非兄弟块），以避免破坏列内整体结构；同时保持确定性与既有对齐约束。
- 当“作为分叉子块的目标 top_y（贴近兄弟分支）”与“作为父块的多子居中目标（贴近自身子块组）”冲突过大时，布局会优先保持兄弟分支紧凑（避免出现 3→4/6 这种兄弟分支之间的大空白带）；冲突较小时会折中求解以保持整体平衡。
- `BlockRelationshipAnalyzer` 仍会输出 `BlockShiftPlan`（包含偏移值与参考块集合）供上层构建块关系与调试使用；块间最终 Y 放置以 `BlockPositioningEngine` 的迭代结果为准，不再额外叠加“经验下移”以避免过度偏移导致的居中失真。
- 块间排版按事件组逐组放置时，`BlockPositioningEngine` 会保留已放置块集合（`positioned_blocks`）与 bucket 索引，不会在单个事件组放置过程中清空；否则会导致前序事件组被误判为孤立块并在收尾的 `place_orphan_blocks()` 阶段被重新放置到右侧，引发“不同事件流起点 X 不一致”的问题。
- 块级模块统一从 `engine.layout.internal.layout_models` 导入 `LayoutBlock`（在本目录中通过相对导入 `..internal.layout_models` 实现），不再在函数体内延迟导入布局算法模块，循环依赖与重复导入被清理。
- `BlockLayoutContext` 构建边索引时优先复用全局/共享缓存，必要时才回退到 `layout/utils/graph_query_utils.build_edge_indices`，与核心上下文保持一致的缓存结构。
- 端口索引访问统一走 `LayoutContext` 或本地 fallback，`block_layout_utils` 中的线性扫描函数已移除，链枚举、树打印与复制逻辑的端口排序完全依赖缓存，性能和行为与布局阶段保持一致。
- `identify_block_flow_nodes` 强制依赖 `LayoutContext` 的缓存索引，块识别阶段的汇合/分支判定不再退回 O(E) 的全图扫描。
- `BlockIdentificationCoordinator` 在事件入口调用链中沿用上游传入的事件ID与标题，只有孤立流程才回退到 `_resolve_event_metadata`，减少重复回溯。
- `DataNodePlacer` 在跨块复制时直接消费链枚举返回的上游闭包顺序，且仅为 skip 集内节点创建副本并按拓扑顺序落位，既避免再次递归整个数据子图，也保证只复制真正跨块的依赖；放置阶段按链ID去重即可覆盖同一逻辑链的不同指令。复制工具内部以“根原始节点 ID + 块 ID”作为语义标识防止重复复制，同时在重定向阶段仍以当前块中真实出现在线上的节点 ID 作为 key，保证连线不会因副本去重而断开。
- 常规放置路径直接消费 `DataChainEnumerator` 的 `chain_nodes` 与预计算的上游映射，省去数据边 DFS，放置复杂度与链长度线性相关。
- `DataNodePlacer` 在完成链指令放置与跨块 pending 源兜底复制后，会以块内流程节点为起点沿数据输出边遍历纯数据子图；但只有当数据节点的输出边指向当前块的流程节点或已放置的数据节点时，才将其纳入本块 `data_nodes_in_order`，保证数据节点被分配到**首次实际消费它的块**，而不是"首次发现它的块"。
- `DataNodePlacer` 会在常规放置完成后对 `block_data_nodes` 做一次覆盖兜底：将全局复制阶段判定“归属本块”的纯数据节点全部纳入 `data_nodes_in_order`，避免某些只参与输出组装/未被流程节点直接消费的纯数据链在 UI 中表现为“不属于任何块”或缺少坐标。
- `DataChainEnumerator` 在生成放置指令时会请求忽略 skip 集合的上游闭包，但只将 skip 集内的节点写入 `CopyDecision.upstream_closure`；链首仍在当前块时不会强制整链复制，而是交由 `DataNodePlacer` 增量复制真正跨块的上游节点；链路预算统一通过 `ChainTraversalBudget` 下发，collect 函数与枚举器共享同一套限额，不再出现配额重复截断。
- `DataChainEnumerator` 当单个起点因限流（如 `LAYOUT_MAX_CHAINS_PER_NODE`）发生截断时，不再中止整块链枚举：后续流程节点的入参仍会被编号，避免出现“未被任何数据链引用”与块内 X 折返线。
- `DataChainEnumerator` 共享节点级记忆化缓存复用 `collect_data_chain_paths` 的子问题结果；缓存 key 包含 `(node_id, 输出端口名)`，并透传起点输出端口以支持端口感知裁剪（例如【获取局部变量】句柄链不展开“初始值”上游），避免布局回头线与不必要的跨块归属。
- 跨块复制判定集中在 `CopyDecision`，`DataNodePlacer` 先生成 `_PlacementPlan` 再执行，复制/降级/兜底步骤统一在计划阶段确定；当禁用复制或命中禁止复制节点时，链条会以共享视图方式放置并记录 `shared_data_nodes`，保证图形结果仍可观察。
- 当 `DATA_NODE_CROSS_BLOCK_COPY` 关闭时，`DataNodePlacer` 会降级为直接放置原始链条而不是跳过，保证节点仍参与排序，只是不会创建额外副本。
- `shared_data_nodes` 会在禁用复制的场景下从 `LayoutBlock.data_nodes`、`node_local_pos` 以及回写的 `global_visited` 结果中过滤，保证真实数据节点仅归属于首个块，同时保留局部链信息供下游引用。
- `BlockRelationshipAnalyzer` 在分析阶段缓存 block→parents 映射，`BlockPositioningEngine` 直接复用该映射，避免在每个事件组内重复构建父子关系和入度数据。
- `BlockPositioningEngine` 在事件组入口一次性构建父集合并在列索引/堆叠阶段共享，同时在计算列左右坐标时按稀疏列增量推进，避免对空列做 range 扫描。
- `BlockPositioningEngine` 的列内堆叠阶段仅遍历真实存在块的列，稀疏列不会触发空循环，事件组纵向累积复杂度与有效列数保持一致。
- Copy-on-write 边索引代理收敛在 `layout/utils/edge_index_proxies.py` 中，块识别只负责实例化与消费，避免在本目录维护容器实现。
- `LayoutBlock` 记录 `node_width` 并在 `BlockPositioningEngine` 中用于“入口≥出口+间距”的约束，宽度调整后也能得到一致的列间距。
- `BlockLayoutExecutor` 会遍历整个基本块中的流程节点，按块内顺序收集跨块流程出口并写入 `LayoutBlock.last_node_branches`，保证递归识别、块关系分析与排序能覆盖途中分支，同时在块边界层面视流程环路为“本块终点+后继块入口”，保持事件流整体可达。
- `DataNodePlacer` 的上游遍历改为显式栈迭代，深链不会触发 Python 递归上限，且 `_collect_upstream_node_ids` 统一了预计算与闭包路径。
- `DataChainEnumerator` 在为 `(src_flow, dst_flow)` 记录最小槽位差时，会统计**该 src_flow 输出在链上所有直接入口中最靠上游的入口距离**（max entry index + 1），以确保这些“流程→数据”直接消费者均有足够列宽落在 `src_flow` 的右侧，从而避免出现折返线；入口之前的共享上游子链仍不会被重复计入。

## 数据节点分块规则

数据节点应该被分配到**首次实际消费它的块**，而不是"首次发现它的块"。

### 判定流程
1. **链枚举阶段**：从流程节点的输入边追溯，发现的数据链直接归入当前块。
2. **下游遍历阶段**：从已放置节点的输出边向下游遍历，使用 `DataNodeOwnershipResolver` 判定：
   - **有出边的节点**：检查消费者是否在当前块（流程节点或已放置的数据节点）
   - **无出边的孤立节点**：分配到入边来源所在的块

### 归属规则（按优先级）
1. 被当前块的流程节点直接消费 → 属于当前块
2. 被当前块已放置的数据节点消费 → 属于当前块
3. 孤立节点（无出边），入边来源在当前块 → 属于当前块
4. 其他情况 → 等待后续块处理

### 边界情况
- **跨块消费**：触发副本创建，原始节点留在首次消费的块
- **无入无出的节点**：理论上不应该存在，校验阶段会报错（`UnusedQueryOutputRule`）
- **skip_data_ids**：标记为跨块边界的节点，不再重复分配

### 相关模块
- `DataNodeOwnershipResolver`：集中管理归属判定逻辑
- `DataNodePlacer._place_downstream_data_nodes_by_ownership`：执行下游遍历和放置
- `assert_all_data_nodes_assigned`：布局后的断言检查（调试模式下启用）

## 注意事项
- 仅关注"块"的抽象与布局算法，不感知具体节点 UI 细节。
- 避免在此目录中引入新的跨层依赖（如 `app/*`、`plugins/*`、`assets/*`）；基础类型应从 `engine.layout.internal` 引入。
- 需要新增工具函数时优先检查 `layout/utils` 是否已有可复用实现，减少冗余。
- 块间排版必须保持可复现：凡是会影响迭代收敛/对齐顺序的遍历（例如遍历块集合、链条组件等）都必须使用稳定排序（以 `LayoutBlock.order_index` 为主键，必要时补充兜底键），避免因 `set` 迭代顺序差异导致块坐标轻微漂移。
- 数据节点跨块复制在 `DataNodePlacer` 内实现，遇到语义敏感的查询节点（如列表中的 `FORBIDDEN_COPY_NODE_TITLES`）应跳过复制，避免副本破坏原有局部状态。
- `identify_block_flow_nodes` 在同一基本块内检测到重复节点 ID 时会停止前进，将该节点视为当前块的终点，用于防御流程环路（包括自环和多节点环）；依赖流程环路表达的结构应通过后续块与 `last_node_branches` 继续展开，而不是期望单个块跨层遍历完整环路。


