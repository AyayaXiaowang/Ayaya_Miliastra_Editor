## 目录用途
`engine/layout/internal/` 存放布局层的核心上下文与注册表派生信息封装（例如 `LayoutRegistryContext`），为 `LayoutService` 提供“只读、可缓存、可注入”的依赖对象，避免布局阶段隐式推导工作区根目录或依赖全局可变状态。

## 当前状态
- `layout_registry_context.py` 提供 `LayoutRegistryContext` 与 `ensure_layout_registry_context_for_model(...)`：
  - 调用方可显式传入 `workspace_path`，或依赖 `Settings.set_config_path(workspace_root)` 注入的 `_workspace_root` 派生工作区根目录；
  - 若未注入工作区根目录且未显式传参，将直接抛错，避免任何“按文件位置猜根目录”的隐式回退。
  - 支持 `LayoutRegistryContext.build_from_node_library(...)`：由调用方提供节点库并派生布局所需的最小索引（实体/结构体入参端口集合/变参规则），用于在“节点库构建中/复合节点解析期”避免反向触发 `NodeRegistry`。

## 注意事项
- 本目录为纯逻辑代码，禁止依赖 `app/*`、`plugins/*`、`assets/*` 或任何外设 I/O。
- 不使用 `try/except` 吞错；错误直接抛出，由上层入口负责处理或中止流程。

## 目录用途
布局核心层：提供 `LayoutService` 以及通用布局常量、上下文数据结构；核心算法入口作为内部实现使用。

## 当前状态
- 承载布局算法编排入口、布局上下文与常量定义等核心模块。
- 借助 `engine.utils.graph.graph_utils` 获取统一的图语义，并通过 `engine.utils.logging.logger` 输出调试信息。
- `internal/constants.py` 中的 `UI_ROW_HEIGHT` 作为 **UI 与布局层共用** 的行高基线：用于端口两行结构的 Y 坐标与节点高度估算；调整行高应确保 UI 端口布局（`NodeGraphicsItem/GraphScene`）与布局层端口Y计算（`coordinate_assigner_data`）保持一致，避免“布局估算高度”和“实际绘制高度”漂移。
- `LayoutContext` 直接复用 `layout/utils/graph_query_utils` 的纯数据节点判定逻辑，避免在核心层重复维护端口语义。
- `LayoutBlock` 拆分至 `internal/layout_models.py`，作为轻量数据结构供 `blocks/`、`utils/` 直接引用，消除了循环导入与运行期按需导入。
- 对上层提供纯逻辑服务，不依赖 UI 或资源，仅处理图模型与基础配置。
- 纯数据图布局流程复用 `layout/utils/data_graph_utils` 的分层结果，若调用方未传入上下文会在内部构建 `LayoutContext`，始终沿用缓存化的边索引。
- 纯数据图的高度估算优先复用 `LayoutContext`，避免为每个节点重复扫描全量边集，在大图上保持 O(N+E) 复杂度。
- `LayoutContext` 在初始化与 clone_for_model 时记录 `graph_signature`，`LayoutService` 同步缓存前会比较签名并仅在必要时克隆，克隆/写回同一张图时不再重复扫描所有节点与边。
- 端口临时提升的回滚阶段会预先构建 `src_node→edges` 映射，命中节点只需线性更新所属边即可完成重命名，大图下的 clone_model=False 路径不再触发 O(N·E) 的全表扫描。
- LayoutContext 仅缓存端口/边索引等只读结构，并同步事件 ID/标题映射，块识别与流程树直接读取同一份缓存，避免重复 BFS；当布局在克隆模型上执行且发生端口提升时，会在原模型上重建 LayoutContext 并复制事件元数据，以确保缓存与调用方图的端口命名一致。
- LayoutContext 维护 `flowCapableNodeIds` 集合，供编排器等场景快速判断某节点是否具备流程口，无需重复扫描端口列表，同时在布局流程结束后会作为 `_layout_context_cache` 写回模型，供流程树或调试工具直接复用。
- 新增只读 `LayoutRegistryContext` 作为布局层对“节点注册表派生信息”（变参规则/实体入参端口集合等）的统一依赖；布局与 UI 端口行规划/高度估算通过该上下文显式注入 workspace_root，或从 `settings.set_config_path(workspace_root)` 注入的单一真源派生，彻底移除基于文件路径猜测根目录的隐式回退，并将上下文缓存到 `model._layout_registry_context_cache` 供后续复用。
- LayoutService 支持按需跳过深拷贝（默认仍克隆模型），同时提供 write-back 选项，可在需要时把布局结果同步回原模型。
- 当布局在克隆模型上执行时，LayoutService 会把 `_layout_block_relationships` 与 `_layout_blocks_cache` 回写到调用方传入的模型实例，供 flow 层与调试工具直接复用。
- `_sync_block_relationship_cache()` 负责在 `compute_layout()` 结束时同步 `_layout_block_relationships` 与 `_layout_blocks_cache`，即便上层跳过克隆也保持语义一致。
- LayoutService 在 `clone_model=False` 且启用端口提升时会记录端口重命名并在布局计算后回滚，始终同步 `_layout_y_debug_info`，并为调用方重新构建 `_layout_context_cache`，避免把克隆模型的上下文直接复用到外部模型。
- `_build_layout_result()` 与 `_write_layout_back()` 仅在检测到原始节点没有出现在任何块内时才使用副本节点的坐标/调试信息做兜底同步，正常情况下原始节点继续保留自身块的布局结果。
- `compute_layout()` 在进入核心算法前会调用 `collapse_duplicate_data_copies()`，将同一原节点在同一块的历史副本合并并删除多余节点，避免重复副本在同一个块内叠加。
- 原始节点只有在自身坐标仍为默认值 `(0,0)` 时才会继承副本的坐标，防止“已有稳定坐标的原节点”被强行移动到副本所在块造成视觉重叠。
- 事件根元数据扩散统一走多源 BFS，核心层一次遍历即可为所有流程节点填充事件 ID/标题，块识别与流程树复用同一份缓存。
- 边索引缓存统一通过 `layout/utils/graph_query_utils.build_edge_indices` 构建，保证与块上下文共享同一套图遍历语义。
- `LayoutOrchestrator` 在块树阶段会将 `LayoutBlock` 列表与块关系快照写入 `model._layout_block_relationships/_layout_blocks_cache`，flow 层无需重新跑布局即可复用顺序和端口映射；若模型上已有 `_layout_context_cache`，编排器会优先复用而不是重新构建索引。
- `LayoutService` 在同步布局缓存时会一并回写 `_layout_context_cache`，UI/流程树复用同一份上下文；对于启用了端口提升的场景，回写阶段会使用原模型重新构建 LayoutContext，避免“副本端口名”被写入调用方。
- 块树阶段通过 `BlockPositioningEngine` 暴露的父集合构建接口，只在事件组入口计算一次父映射并在列索引/堆叠阶段共享，避免重复过滤。
- `LayoutOrchestrator` 发现事件节点后会预计算 ID→标题映射并沿着流程边一次性传播到所有下游流程节点，该扩散过程对事件源进行快照迭代，避免在遍历过程中修改字典导致运行时错误；块识别阶段直接消费该映射即可获取事件元数据，仅孤立流程才回退到局部 BFS，同时会把来自 `engine.configs.settings` 的布局开关（如块紧凑开关）传入 `BlockPositioningEngine` 以保持算法行为与 UI 设置一致。
- 事件标题解析统一调用 `graph_query_utils.resolve_event_title`，配合 `build_event_title_lookup` 一次性构建映射，核心层不再维护手写回退逻辑。
- 纯数据图布局在计算完成后会缓存调用时使用的 `LayoutContext`，后续流程树或调试工具读取同一模型时无需再次构建上下文。
- `LayoutBlock` 记录 `node_width` 等局部几何信息，块定位阶段不再假设默认宽度；块识别协调器的几何常数仅计算一次，并在上下文构建与布局管线之间共享。
- 事件组（按事件流划分）之间的垂直组间距通过 `EVENT_Y_GAP_DEFAULT` 注入到 `LayoutOrchestrator.event_y_gap`，块树阶段按该值在不同事件流之间整体堆叠。
- 自动排版支持“节点间距倍率”（横/纵，百分比）：通过 `engine.configs.settings` 的 `LAYOUT_NODE_SPACING_X_PERCENT/LAYOUT_NODE_SPACING_Y_PERCENT` 配置；`internal/constants.py` 提供统一的倍率与换算函数（`scale_layout_gap_x/scale_layout_gap_y/compute_slot_width_from_node_width`），并引入 `UI_NODE_MIN_WIDTH` 作为横向下界（避免缩小倍率时列宽小于实际渲染宽度导致节点重叠）；布局编排器与纯数据图布局复用该倍率逻辑，默认 100% 完全保持旧结果。
- `LayoutOrchestrator` 采用新的多阶段布局流程：(1) 识别所有块的流程节点（不放置数据节点）；(2) 全局复制阶段：通过 `GlobalCopyManager` 分析跨块共享的数据节点，统一创建副本和重定向边；(3) 数据节点放置阶段：为每个块放置数据节点并计算坐标；(4) 块间排版；(5) 应用最终位置。该流程将数据节点复制逻辑从"边识别边复制"改为"全局分析后统一复制"，解决了原有的复制时机问题。
- `LayoutOrchestrator` 在全局复制完成后、块内排版前可选执行“长连线中转”增强：当 `settings.LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY=True` 时，会扫描长跨度数据边并自动插入中继点将长边拆分为多段短边；默认使用【获取局部变量】作为中转节点，但对源节点为【获取自身实体】的长连线会改为“复制【获取自身实体】查询节点”作为中继点以减少不必要的局部变量中转。中继点使用确定性 ID，并在阶段2通过强制放置映射覆盖 `GlobalCopyManager` 的归属结果，确保节点落在阈值对应的块中参与排版与任务清单生成。
- `LayoutOrchestrator` 在数据节点放置完成后，会额外识别“未被任何流程块放置的纯数据节点连通分量”，并将其作为 **纯数据孤立块** 追加到 `LayoutBlock` 列表中参与块间排版（落入 orphan blocks 放置阶段）；用于复合节点子图中“仅由虚拟输出引脚消费”的数据链等场景，保证这些节点在 UI 中独立成块可见。
- `_execute_global_copy()` 无论是否启用复制，都会创建 `GlobalCopyManager` 并分析数据依赖以确定每个块的数据节点归属；只有启用复制时才执行复制计划。这确保禁用复制时数据节点也能正确分配到唯一的块（第一个使用它的块）。
- 当启用跨块复制并修改了 `model.nodes/model.edges` 后，`LayoutOrchestrator` 会重建 `LayoutContext` 并刷新阶段1缓存的块上下文，避免阶段2读取过期的边索引缓存导致布局不一致。
- 禁用复制后的模型恢复由 UI 层处理：当开关变化时，`settings_dialog.py` 会调用 `schedule_reparse_on_next_auto_layout()`，下次排版时 `graph_editor_controller.py` 的 `prepare_for_auto_layout()` 会从 .py 文件重新解析，得到干净的模型。

## 注意事项
- 保持 API 稳定，并通过 `engine.layout` 顶层进行统一导出。
- 避免在此目录中引入与具体块实现或工具函数的强耦合逻辑，细节可下沉到 `blocks/` 或 `utils/`。
- 若新增算法依赖通用数据结构，应从 `layout/utils` 引入公共实现。


