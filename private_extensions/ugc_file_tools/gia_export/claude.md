# ugc_file_tools/gia_export 目录说明

## 目录用途
- 存放 `.gia` 导出/写回相关的“按资产类型分域”的核心实现，避免与 `.gil` 写回混放导致边界含混。

## 当前状态
- `node_graph/`：节点图 `.gia`（AssetBundle/NodeGraph，对齐 NodeEditorPack `gia.proto`）导出能力。
- `structs.py`：结构体定义 `.gia`（StructureDefinition GraphUnit）导出门面（转发到 `struct_def_writeback/gia_export.py`）。
- `signals.py`：信号 `.gia`（信号相关 node_def GraphUnit）导出门面（转发到 `signal_writeback/gia_export.py`）。
- `layout_asset.py`：布局资产 `.gia`（UI Layout Asset）导出门面（转发到 `ui_patchers/layout/layout_asset_gia.py`）。
- `decorations.py`：实体/装饰物/资产包 `.gia` 门面（同时暴露语义重编码与 wire-level 保真路径；也包含对既有装饰物 `.gia` 的 merge/center 变换）。
- `wire_patch.py`：`.gia` wire-level 保真补丁门面（例如仅替换 Root.filePath）。
- `qrcode_entity/`：二维码方块墙实体 `.gia` 生成（Entity Asset，依赖 `qrcode/Pillow/protobuf`；提供可 import 的稳定入口，供 `unified_cli entity qrcode` 使用）。
- `templates.py`：元件模板 `.gia` 导出（含自定义变量）：
  - 基于 base bundle 做“结构克隆 + 小范围字段补丁”，补丁资源名、内部 name record（record.field_11 内嵌 message 的 field_1 写入 name）、override variables group1（自定义变量列表）与 Root.filePath。
  - 默认使用内置 base（`builtin_component_template_base_field_map.json`），UI/CLI 可选传入真源 base `.gia` 覆盖（用于对齐不同版本/不同模板差异）。
- 为每个模板分配稳定的 `template_root_id_int`（`0x4040xxxx` / 1077936xxx，low16 落在 `0x4000~0x7FFF`），避免 low16>=0x8000 在部分真源/工具链中被当作 int16 负数而导致“不可见/不识别”。
  - 自定义变量值结构统一复用 `ugc_file_tools/custom_variables/value_message.py`（单一真源）：`var_type_int + 10` 的值字段号；字典/配置ID等特殊结构按样本写入；不支持类型会 fail-fast 抛错。
- `templates_instances.py`：wire-level “元件模板+实体摆放(实例)” bundle.gia 的双向转换（元件↔实体）。
- `player_templates.py`：玩家模板 `.gia` 导出（含自定义变量）：
  - template-driven：基于真源导出的 base 玩家模板 `.gia` 克隆结构，对主资源条目写入名称/ID 与 override variables group1；
  - 同步更新 role editor（`(角色编辑)`）相关资源的 root_id_int 与引用（按 old_id→new_id 全局替换），并按 base 名称前缀同步改名（例如 `默认模版(角色编辑)` → `<新名>(角色编辑)`）；
  - 自定义变量来源由上层 pipeline 决定（典型：玩家模板 JSON 的 `metadata.custom_variable_file` 引用的变量文件扁平化写入 group1）。

## 注意事项
- 不使用 try/except：失败直接抛错（fail-fast）。
- `.gia` 容器封装统一复用 `ugc_file_tools.gia.container`；protobuf-like 编解码统一复用 `ugc_file_tools.gil_dump_codec.protobuf_like`。
