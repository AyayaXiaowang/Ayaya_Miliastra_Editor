## 目录用途
布局通用工具与辅助模块：承载与具体块实现解耦的公共算法（图查询、坐标分配、跨块复制、结果回写/合并等），供 `engine.layout.internal` 与 `engine.layout.blocks` 复用。

## 当前状态
- **图查询与语义工具**：`graph_query_utils` 统一提供流程/数据语义判定、边索引构建、事件标题解析、数据链遍历（含 `ChainTraversalBudget`）以及 `InputPortLayoutPlan`（UI 与布局共享端口行数/换行口径）。流程口/流程边判定以 `NodeModel.effective_input_types/effective_output_types` 为真源，名称规则仅作兼容回退，避免动态端口依赖关键字猜测。
- **坐标分配**：`CoordinateAssigner` 为块内写回入口；X 轴列索引在 `coordinate_assigner_x`，数据节点坐标规划在 `coordinate_assigner_data`；可选的块内数据 Y 松弛在 `data_y_relaxation`（受 settings 开关控制）。
- **跨块数据复制**：`GlobalCopyManager` 负责在块识别完成后统一生成复制计划并应用；copy-on-write 边索引代理在 `edge_index_proxies`；副本身份解析与排序单一真源为 `copy_identity_utils`。
- **长连线中继**：`local_variable_relay_inserter`（及 `local_variable_relay/`）负责插入确定性的 relay 节点链路以缩短过长数据线，并避免结构累积漂移。
- **结果合并单一真源**：`augmented_layout_merge` 负责把增强布局差分合并回原模型并回填坐标/调试信息，供资源层与 UI 复用。

## 注意事项
- 工具函数保持无副作用或副作用可控；尽量“先生成计划、再统一写回”，并保证遍历/排序确定性。
- 新增公共算法优先落在本目录，避免在 `blocks/` 或调用方重复实现；禁止引入 `app/*`、`plugins/*` 等跨层依赖。
