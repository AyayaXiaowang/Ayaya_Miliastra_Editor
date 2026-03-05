## 目录用途
- 存放 `ugc_file_tools` 的**内置 `.gia` 结构模板**（可公开、可版本化）：用于信号/结构体/布局资产等导出链路的“模板驱动（深拷贝 + 定点 patch）”。
- 该目录属于 `builtin_resources/`：工具链会直接引用并 fail-fast 校验存在性。

## 当前状态
- `signals/`：信号相关模板（导出/示例生成用）。
- `struct_defs_6.gia` / `struct_defs_3.gia` / `struct_defs_2.gia` / `struct_defs_1_modern.gia` / `struct_defs_1_legacy_adventure_level_config.gia`：结构体导出模板集合（含 accessories/relatedIds 等结构真源）。
- `layout_asset_template.gia`：布局资产导出/打包的结构模板（非 NodeGraph `.gia`）。

## 注意事项
- 模板应保持最小化与可公开：只作为结构夹具，不应包含未授权业务内容。
- 旧目录 `builtin_resources/资产/` 已停用并建议在对外仓库中忽略（见根目录 `.gitignore`）。

