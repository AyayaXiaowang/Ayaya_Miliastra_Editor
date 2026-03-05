## 目录用途

- 存放 `ugc_file_tools` 默认使用的 `dtype.json`（字段/类型描述），供 `.gil/.gia` 解析与导出链路读取。

## 当前状态

- `dtype.json`：从上游 `Genshin-Impact-UGC-File-Converter` 工程同步而来，作为本仓库内置且可版本化的默认 dtype 资源。

## 注意事项

- `dtype.json` 需与目标版本匹配，否则解析结构可能错位。
- 本目录仅承载数据资源，不包含转换器实现代码。

