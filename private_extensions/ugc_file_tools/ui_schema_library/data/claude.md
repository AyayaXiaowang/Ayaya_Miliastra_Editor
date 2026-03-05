## 目录用途
- 存放 UI schema library 的自动沉淀数据（由 `ui_schema_library/recorder.py` 生成）。
- 产物包含：
  - `index.json`：schema 索引（结构签名 → 统计/示例/来源/模板 record 文件）
  - `records/`：每个 schema 的代表性模板 record（原样 JSON，含 `<binary_data>` blob）

## 当前状态
- 初始为空；当你运行带 `--enable-dll-dump` 的解析（额外 dump-json 并提取 UI 数据）后，会自动生成/更新。
- `index.json.schemas[*].label` 可用于人工/工具标注“已确认的模板”（例如 `progressbar` / `textbox` / `item_display`）；`ui import-web-template` 会优先复用这些模板以减少对外部样本存档的依赖。
- `index.json.families[*]` 为观测汇总：把 protobuf-like message 的 blob/dict 两种形态归并为同一 `family_id`，用于查看“同一控件概念下的多种写法/变体”。

## 注意事项
- 该目录数据来自真实 `.gil` 的 dump-json 解析结果，可能包含你项目的私有 UI 信息；默认仅建议在本地工作区内保存与复用。
- 可随时删除重建；删除后再次解析会重新沉淀（但会失去已沉淀的“可复用模板 record”）。

