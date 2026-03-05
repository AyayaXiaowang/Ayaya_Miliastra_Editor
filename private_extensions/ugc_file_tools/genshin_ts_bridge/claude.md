## 目录用途
- 从（临时拉取到）`private_extensions/third_party/genshin-ts` 及其携带的 NodeEditorPack 第三方数据中提取**更贴近真源存档口径**的枚举与节点画像，用于：
  - 结构体字段 `type_id`（`VarType`）的集中对齐与生成；
  - 节点图写回/校验所需的 `node_type_id → 端口画像（输入/输出数量与类型表达式）` 导出；
  - 为后续“Graph_Generater（用户侧） ↔ 真源存档（.gil/.gia）”建立可追溯桥接数据源。

## 当前状态
- `paths.py`：集中维护 genshin-ts/NodeEditorPack 的关键文件路径（以 Graph_Generater 根目录为锚点）。
- `parse_gia_proto.py`：解析 `gia.proto` 中的 `enum VarType` / `enum ClientVarType`。
- `export_struct_type_ids.py`：导出/校验结构体字段 `param_type(中文) → VarType(type_id)` 映射，并生成 JSON 报告到 `private_extensions/ugc_file_tools/refs/genshin_ts/`。
- `export_node_schema.py`：从 NodeEditorPack 的 `node_data/node_pin_records.ts` / `node_data/node_id.ts` 导出节点画像 JSON（节点名/ID/输入输出类型表达式/reflectMap）。
  - 同时导出 `node_data/concrete_map.ts` 的 ConcreteMap（pins→maps）：用于写回阶段计算 `indexOfConcrete`（泛型/反射端口）。

## 注意事项
- 本目录以“真源口径”为准：优先相信 `gia.proto` 与 NodeEditorPack 数据，而不是 Graph_Generater 的展示层命名。
- 不使用 try/except：解析失败直接抛错，避免静默生成错误映射导致写回存档不可导入。
- 输出统一落在 `private_extensions/ugc_file_tools/refs/genshin_ts/`（可随时删除重建）。
- `third_party/genshin-ts/` 可能不存在：日常工具链仅消费 `refs/genshin_ts/*.report.json`；若需要重建报告，则需先把上游临时拉回该目录。
- 报告文件默认不写入溯源绝对路径字段（例如 `sources/*`、`gia_proto_path`），避免泄露本机路径；不影响运行期解析与校验。
- 运行方式（在仓库根目录 `Graph_Generater/` 执行）：
  - 结构体 type_id（VarType）映射报告：
    - `python -X utf8 -m private_extensions.ugc_file_tools.genshin_ts_bridge.export_struct_type_ids`
    - 输出：`private_extensions/ugc_file_tools/refs/genshin_ts/genshin_ts__struct_field_type_ids.report.json`
  - 节点画像（node schema）报告：
    - `python -X utf8 -m private_extensions.ugc_file_tools.genshin_ts_bridge.export_node_schema`
    - 输出：`private_extensions/ugc_file_tools/refs/genshin_ts/genshin_ts__node_schema.report.json`
