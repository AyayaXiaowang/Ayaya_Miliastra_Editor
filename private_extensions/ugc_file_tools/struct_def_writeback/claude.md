## 目录用途
- `add_struct_definition_to_gil.py` 的拆分实现区：负责 `.gil` 结构体定义写回（`root4/10/6`）以及相关注册（结构体节点定义/页签等）。

## 当前状态
- `helpers.py`：结构体写回的底层工具函数（结构体 blob/字段编辑 + node_defs/tab 辅助等；包含被其他模块复用的 `_xxx` 函数）。
  - `.gil → dump-json` 的纯 Python 解码与通用树编辑工具已收口到 `ugc_file_tools/gil_dump_codec/dump_json_tree.py`（不落临时文件），避免在不同写回域重复实现导致漂移。
  - 包含 decoded-json 归一化：将非法的 `field_0`（包括“repeated 0”误判形态）转换回等价 `raw_hex`，以保证结构体 blob 可稳定重编码写回。
  - 兼容 node_defs 的名称字段：`entry['1']['200']` 可能是 `str` 或 `{raw_hex, utf8}` 的 text node，模板匹配需同时支持两者。
  - 兼容页签 list 的形态：结构体页签的 `key '5'` 在单元素时可能被 dump 为 dict 标量，需要归一化为 list。
  - 兼容结构体 blob 的形态：`root4/10/6` 的条目可能是 `<binary_data>` 字符串，也可能被 dump 为 dict（单元素 repeated 的标量化）；写回工具需统一支持两者。
- `preset_all_types_test.py`：`add_all_types_test_struct_definition`（全类型字段默认值写回自测）。
- `preset_clone_all_supported.py`：`clone_struct_all_supported_definition`（克隆模板用于二分定位导入失败）。
- `preset_misc.py`：`add_empty_struct_definition` / `rename_struct_definition` / `add_one_string_struct_definition`。
- `gia_export.py`：将“基础结构体（共享根 + 项目根的 *.py）”导出为 `.gia`（StructureDefinition GraphUnit），用于注入/对照。
  - 支持按 `selected_struct_ids` 过滤仅导出选中结构体（供 UI 勾选导出使用）。
  - 导出会先落盘到 `ugc_file_tools/out/`，并**默认复制到真源导入目录** `Beyond_Local_Export`（可通过 `output_user_dir` 覆盖）。
  - 模板驱动：默认会从 `ugc_file_tools/builtin_resources/gia_templates/` 中按导出数量选择一个“内置模板 `.gia`”作为模板（也可显式传 `template_gia`）。
    - 1 个结构体：优先 `struct_defs_1_modern.gia`（若不存在则回退到 `struct_defs_1_legacy_adventure_level_config.gia`）
    - 2/3 个结构体：优先 `struct_defs_2.gia` / `struct_defs_3.gia`
    - 其它：回退到 `struct_defs_6.gia`
  - `struct_id_strategy=auto`：参考模板的 slot 范围，默认从 `max(template_slot)+1` 起步，并避开模板已占用 slot，减少“从 1077936000 起步”带来的潜在导入差异。
  - 结构体字段编码对齐真源样本：
    - `VarDef.def(field_3)` 的默认值使用 `field_(10 + VarType)`（例如 Int=13/Bool=14/Str=16/GUIDList=17/IntList=18/ConfigList=32/StructList=36）。
    - `VarDef.def(field_3).field_2` 为 **单层** `message{field_1=VarType, field_2=subType}`（不能再额外包一层 message，否则导出结构会整体错位）。
    - 空字符串默认值写为 **空 bytes**（`raw_hex=""`），避免写出“显式空文本 message”导致真源解析差异。
  - **单结构体 vs 多结构体（真源差异，必须对齐）**：
    - 单结构体：Root.field_1 为 GraphUnit（非 list）。
    - 多结构体：Root.field_1 为 repeated GraphUnit（list）。
    - 当前导出仅包含 StructureDefinition（不附带 `relatedIds` 与 Root.accessories）。
    - Struct/StructList 需要同时写入 subtype（`field_2`）与默认值的 struct_id（`field_35/field_36.field_501`），否则真源可能整段丢弃。
  - Root.filePath / Root.gameVersion 默认从模板推断（uid/file_guid/gameVersion），并保持分隔符为单个反斜杠 `\\`。
  - 输出文件名清洗规则统一复用 `ugc_file_tools/fs_naming.py`（与节点图 GIA 导出保持一致）。
- 对外入口仍在 `ugc_file_tools/add_struct_definition_to_gil.py`（兼容导入与 CLI）。

## 注意事项
- 不使用 try/except；失败直接抛错便于定位。
- 输出文件参数只接受文件名（basename），由工具统一写入 `ugc_file_tools/out/`，避免 `out/out/...` 路径漂移。
- 写回依赖 dump-json 的“数值键结构”作为可重编码中间表示；dump 已改为纯 Python，不再要求额外 DLL。操作前务必备份 `.gil`。
- 同一存档内需避免 `ugc_ref_id_int / struct_internal_id / node_type_id` 重复。
- `.gia` 的 decoded_field_map/numeric_message 语义辅助统一使用 `ugc_file_tools.gia.varbase_semantics`（避免与 protobuf-like codec 混淆）。



