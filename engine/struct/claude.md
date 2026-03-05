## 目录用途
结构体系统领域层：集中提供“结构体定义”的只读仓库与与校验协作的公共接口，供解析器、校验器与 UI 统一复用。

## 当前状态
- 对外入口：`engine.struct.get_default_struct_repository()`。
- 结构体定义由 `engine.resources.definition_schema_view` 从资源库的“共享根 + 当前项目存档根”作用域聚合加载：
  - `assets/资源库/共享/管理配置/结构体定义/**.py`
  - `assets/资源库/项目存档/<package_id>/管理配置/结构体定义/**.py`（允许覆盖共享同 ID 定义）
- 仓库在边界处对结构体 payload 做**结构归一化**：兼容旧/新两种结构体 schema，并统一输出 `{type: "Struct", struct_type, struct_name, fields}` 视图；无法归一化的定义会进入 `get_errors()` 供校验层前置报错。
- 结构体定义只保留 `struct_name` 作为唯一名称字段（中文、稳定引用名）；仓库解析与引用以 `STRUCT_ID/struct_name` 为准。
- 对 ID 类型字段默认值做强校验：当结构体字段 `param_type` 为 `GUID/配置ID/元件ID`（及其列表类型）且提供 `default_value` 时，要求其为可解析的 **1~10 位纯数字**（列表逐元素校验），禁止 UUID 字符串或空字符串占位；不满足将进入 `get_errors()`。

## 注意事项
- 严禁在调用方自行解析结构体 payload（例如到处 `payload.get("value")` / `payload.get("struct_ype")`）；必须通过仓库 API 获取字段、类型与 ID 解析结果。
- 历史字段（如 `struct_ype` / `value` / `lenth` / `key`）仅作为旧 schema 输入形态存在，调用侧不应依赖其结构；新定义应优先使用 `struct_type/struct_name/fields/field_name/length` 结构。


