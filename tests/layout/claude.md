## 目录用途
存放“自动排版/分块/跨块复制”相关测试：验证块识别顺序、块间/块内布局策略、数据节点归属与跨块复制约束等，确保布局结果稳定且不产生折返线/孤立副本等 UI 问题。

## 当前状态
- **块识别与顺序**
  - `test_block_identification_bfs_ordering.py`：回归块识别采用 BFS 顺序，避免兄弟分支初始化节点被编号到最后一个块导致 UI 分块错位。
- **块间布局**
  - `test_block_vertical_centering.py`：回归块间（多父合流/多子分叉）垂直居中与同列局部互换约束，避免整列重排破坏结构。
  - `test_block_column_x_avoids_data_foldback.py`：回归列左对齐模式下跨块 data 依赖不出现“右→左折返”边（跳出循环回边除外）。
  - `test_template_validation_edge_native_expr_mix_has_no_foldback_edges.py`：回归“测试_边界_原生表达式混合上限”在解析+排版后不出现折返边，覆盖链限流与复杂表达式混合场景。
  - `test_composite_int_list_slice_has_no_foldback_edges.py`：回归复合节点 `composite_整数列表_切片` 自动排版后不出现折返边（覆盖【获取局部变量】初始值上游归属场景）。
  - `test_forge_hero_weapon_browse_layout_has_no_foldback_edges.py`：回归复合执行节点的“流程→数据”输出不会被排到左侧导致折返边（锻刀英雄_武器展示与选择_变量变化）。
- **块内布局**
  - `test_block_internal_data_y_relaxation.py`：回归块内数据节点 Y 轴收敛策略与布局确定性（相同输入输出相同坐标），覆盖多父合流场景。
- **数据节点归属与复制**
  - `test_data_node_placement.py`：回归数据节点归属判定逻辑（首次实际消费它的块）。
  - `test_global_copy_forbidden_nodes.py`：回归跨块复制禁用节点（如【获取局部变量】）的 owner 块归属与不生成副本规则；同时确保普通纯数据节点仍可按规则生成副本并重定向边。
- `test_local_variable_relay_inserter.py`：回归“长连线中转（获取局部变量）节点”插入器：当同一块内 **flow→flow** 数据边跨越过多流程节点时应生成 relay 节点并按阈值落在中间槽位，替换为链式短边；并验证 relay node_id 编码的 slot 会在块内 X 轴分配阶段被优先采用；多个远端消费者来自同一源端口时应共用 relay 链，避免重复插入；同时覆盖 **纯数据节点作为源（如【以GUID查询实体】）→ 多个远端流程消费者** 的按节点跨度拆分逻辑；并验证“方案B（清理→重建）”在已有 relay 结构的模型上再次执行时不会叠加漂移、不会产生 relay 自环，且最终结构稳定。
  - `test_no_isolated_data_copies.py`：回归“校验通过后布局/复制阶段不应生成无任何数据输出引用的跨块数据副本”。

## 注意事项
- 尽量复用仓库内公开模板/示例节点图作为稳定输入，避免依赖本地私有资源。
- 公开模板/测试节点图位于 `assets/资源库/项目存档/<package_id>/节点图/<server|client>/...`（资源库目录已包化，不再使用 legacy 的 `assets/资源库/节点图/...`）。
- 回归用例优先选择 `示例项目模板` 下的模板/测试图作为输入，避免引用未纳入版本管理的项目存档（例如本地“演示项目”）。
- 布局/复制相关测试通常更“集成”，断言应聚焦在关键不变量（例如无折返边、无孤立副本、居中关系）。


