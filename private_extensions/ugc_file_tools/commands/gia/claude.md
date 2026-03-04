# ugc_file_tools/commands/gia 目录说明

## 目录用途
- `commands/` 下的“`.gia` 工具分类导航视图”：按 `.gia` 相关主题聚合入口实现，便于浏览与维护。
- 注意：对外稳定入口仍以 `ugc_file_tools.commands.<tool_name>`（位于 `commands/` 顶层的薄 wrapper）为准；本目录承载对应实现模块。

## 当前状态
- `gia_to_readable_json.py`：导出 `.gia` 为可读 JSON（用于分析/对照）。
- `gia_patch_file_path_wire.py`：wire-level 只替换 Root.filePath 的保真补丁。
- `gia_build_decorations_bundle.py` / `gia_build_decorations_bundle_wire.py`：装饰物挂件 `.gia` 生成（语义重编码 / wire-level）。
- `gia_build_asset_bundle_decorations.py`：资产包类装饰物 `.gia` 生成。
- `gia_build_entity_decorations_wire.py`：wire-level 生成“带装饰物的实体类” `.gia`（含 relatedIds/packed list/parent bind 修正）。
- `gia_merge_and_center_decorations.py`：wire-level 装饰物合并/居中：支持 `keep_world(默认)`（移动 parent 并补偿装饰物 local，装饰物世界坐标不动）与 `move_decorations`（直接平移装饰物）两种策略；多 parent 可合并挂到同一空物体。
- `gia_convert_component_entity.py`：wire-level 元件模板 ↔ 实体摆放 bundle.gia 转换（Root.field_1 templates / Root.field_2 instances）。
- `gia_export_decorations_variants.py`：批量导出变体用于二分定位导入约束。
- `gia_graph_ir_to_gia.py`：Graph IR JSON → `.gia` 写回/生成入口。

## 注意事项
- 本目录脚本应保持“入口薄、逻辑下沉”：复杂逻辑应下沉到 `ugc_file_tools/gia/*` 或 `ugc_file_tools/gia_export/*`。
- 不使用 try/except；失败直接抛错。
- 本目录实现模块不作为独立 CLI 入口：直接执行会提示改用统一入口（对外稳定入口仍为 `ugc_file_tools.commands.<tool_name>`）。
- `--copy-to-beyond-export` 默认目录由 `ugc_file_tools.beyond_local_export.get_beyond_local_export_dir()`（基于 `Path.home()`）推导，避免写死盘符/用户名。

