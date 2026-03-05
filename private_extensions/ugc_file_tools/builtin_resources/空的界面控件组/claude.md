## 目录用途
- 存放 `ugc_file_tools` UI 写回/导入链路所需的**内置控件组模板 `.gil`**（可公开、可版本化）。
- 这些文件会被 `web_ui_import_*` 与部分写回/导入逻辑作为“结构真源/克隆原型/兜底 seed”直接读取；缺失应 fail-fast 抛错。

## 当前状态
- `进度条样式.gil`：UI 段 bootstrap 的兜底 seed（当 base 缺失 `root4/9` 或极空 base 需补齐其它 `root4` 段时使用）；同时作为“关卡实体自定义变量写回”的 seed（用于补齐/查找 `root4/5/1` 内 `name=关卡实体` 的 entry）。
- `道具展示.gil`：道具展示控件模板/样本（用于从 UI record_list 中选择可克隆 record；并作为 workbench 回归测试的 base 存档）。
- `文本框样式.gil`：TextBox 控件模板/样本（用于在 ui_schema_library 未沉淀 textbox 时提供一次性 seed，避免依赖 `save/` 真源样本库）。

## 注意事项
- 保持最小化：仅保留链路必需的 `payload_root` 顶层字段与必要 record；避免携带演示布局/业务内容。
- 额外实验/真源样本请放入 `ugc_file_tools/save/`（默认忽略，不进入对外仓库）。

