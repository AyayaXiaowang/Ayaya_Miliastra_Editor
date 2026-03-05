## 目录用途
- 本目录存放项目存档 `测试基础内容` 的 **UI控件模板**（资源类型：`管理配置/UI控件模板`），每个 `*.json` 文件对应一个模板资源。
- UI 只负责加载/展示与编辑已知字段；未知字段允许保留，用于承载更完整的结构化 UI 数据。

## 当前状态
- 包含一组固有内容模板（`builtin_*__测试基础内容`，含 `语音.json`）以及一个示例全字段模板 `示例_UI控件模板_全字段.json`。
- 固有内容中仅部分模板支持在布局层进行“局部显隐覆盖”，其余模板在布局中不可被隐藏（应通过 `supports_layout_visibility_override` 标记）。

## 注意事项
- 每个模板必须包含 `template_id` 与 `template_name`，并包含 `widgets[]`（每个 widget 至少包含 `widget_id/widget_type/widget_name/position/size`）。
- `supports_layout_visibility_override` 用于控制“界面布局”面板里是否允许对该模板勾选可见性；缺省视为支持（`true`）。
- `widgets[].settings` 用于承载控件类型化配置（如进度条 shape/style/color 及变量绑定等）。

