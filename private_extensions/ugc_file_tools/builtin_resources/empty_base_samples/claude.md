# empty_base_samples（ugc_file_tools/builtin_resources）

## 目录用途
- 放置一组“可作为基底/夹具”的示范 `.gil`，用于导出中心内置 base 与写回链路回归/对齐。

## 当前状态
- `empty_base_vacuum.gil`：**极空基底**（payload_root 仅少数字段），用于覆盖“极空 base”兼容与 bootstrapping 场景。
- `empty_base_with_infra.gil`：**带基础设施的空存档**（含基础实体/模板/UI 默认布局等），用于导出中心的“内置空存档 base”；并包含节点图/信号相关段的最小空壳（例如 `root10` 内含“复合节点”页签记录）与额外基础标记（例如 `PropertyTransform`）；同时包含 `root4/11/9={1:1}` 的基础标记，更适合作为增量写回/导出起点。
- `empty_base_no_node_graph_signals_shell.gil`：对照用空存档样本（节点图/信号段更“纯空”），用于排查“base 是否需要 bootstrap 段”的差异。
- `empty_base_composite_tabs_shell.gil`：对照用空存档样本（包含“复合节点”页签空壳，但不含后续新增的基础标记），用于二分定位 base 差异。
- `two_structs_sample.gil`：结构体相关最小示范样本。
- `simple_player_template_sample.gil`：玩家模板相关最小示范样本。

## 注意事项
- 本目录样本视为输入；工具输出应落到 `ugc_file_tools/out/`，避免覆盖样本。

