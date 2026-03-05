## 目录用途
- 存放“节点图可读 IR”相关的可维护配置与约定（例如节点类型语义映射表）。
- 该目录用于减少重复分析成本：把已确认/高置信度的推断结果落盘，供导出器与后续工具复用。

## 当前状态
- `node_type_semantic_map.json`：内置节点 `node_type_id_int` → 语义/节点名 的映射（含置信度与备注），供“pyugc→GraphModel→Graph Code”的反向生成与 IR 导出复用。
  - 映射既可来自“校准图半自动推断”，也可来自人工整理的 `ID→中文名` 批量导入（用于快速提升覆盖率）。
  - 可用 `ugc_file_tools/commands/report_node_type_semantic_map_invalid_nodes.py` 校验：已填中文节点名必须存在于 `Graph_Generater/plugins/nodes/**` 实现节点库（避免误把复合节点/不存在节点写入映射表）。
  - `graph_generater_node_name` 允许为空：表示该 type_id 暂未映射到 Graph_Generater 节点名（通常因为节点未实现/名称未确认）。
  - 映射覆盖包含信号与结构体等系统节点（例如 `signal.listen`、`struct.*` 相关节点）。
- `校准节点图_节点类型映射_v1.md`：用于让你在游戏里搭建“校准图”的节点/连线清单（导出后可反推 type_id→节点语义）。
  - 映射可通过 `ugc_file_tools/commands/build_node_type_semantic_map_from_calibration.py` 半自动补全（以校准图 + 参考 Graph Code 对齐 flow 链）。
  - 校准图支持包含“同一节点的多种可调用别名”（例如含 `/` 的节点名会出现 `_` 与“去掉 `/`”两种调用写法）；补全脚本会统一写入 canonical 节点名。

## 注意事项
- 映射表以“可更新的当前结论”为准，不记录修改历史；若推断被证伪，直接更新为新的结论。
- 若出现“同一 type_id 在不同图里表现为不同节点”的情况，应优先以校准图/可复现证据为准，并补充备注说明适用范围（server/client、特定版本/资源包）。
- 同一 scope 下 **同名节点必须唯一映射到一个 type_id**，否则写回预检/覆盖报告会判为“歧义映射”并阻断写回；若因版本差异导致同名多 type_id，应只保留一个映射，其余条目的 `graph_generater_node_name` 置空并在 `notes` 里说明。
- 本目录不记录修改历史，仅保持用途/状态/注意事项的实时描述。