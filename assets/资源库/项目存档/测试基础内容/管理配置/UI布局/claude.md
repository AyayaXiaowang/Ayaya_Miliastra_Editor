## 目录用途
- 本目录存放项目存档 `测试基础内容` 的 **UI布局**（资源类型：`管理配置/UI布局`），每个 `*.json` 文件对应一个布局资源。
- 布局用于组织“固有内容模板 + 自定义控件组模板”的引用关系，并可对支持的模板做局部显隐覆盖。

## 当前状态
- `默认布局.json`：默认布局，引用本包的固有内容模板（包含 `语音`）。
- `示例_UI布局_全字段.json`：示例布局，用于展示布局字段结构。

## 注意事项
- 每个布局必须包含 `layout_id` 与 `layout_name`，并包含：
  - `builtin_widgets[]`：固有内容模板 ID 列表
  - `custom_groups[]`：自定义控件组模板 ID 列表
  - `visibility_overrides{}`：局部显隐覆盖（键为模板 ID；仅对支持 `supports_layout_visibility_override=true` 的模板生效）
- `builtin_widgets/custom_groups` 引用的模板 ID 应存在于同包的 `管理配置/UI控件模板` 资源中，否则综合校验会报错。
- 允许额外字段用于承载更完整的 UI 结构数据；UI 模型会尽量保留未知字段。

