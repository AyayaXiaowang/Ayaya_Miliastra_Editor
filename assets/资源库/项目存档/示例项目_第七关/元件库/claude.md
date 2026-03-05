## 目录用途
项目存档 `示例项目_第七关` 的元件模板库：存放 Template JSON（每文件一个模板），供实体摆放/实例与项目索引引用。

## 当前状态
- 目录仅保留本存档独占的模板资源；跨包复用的模板应集中到目标存档或共享根，避免 `template_id` 冲突。
- 模板可包含默认挂载节点图、组件配置与 `metadata` 等字段。
- 当项目存档启用 `管理配置/关卡变量/自定义变量注册表.py` 时，部分模板会在 `metadata.custom_variable_file` 引用注册表派生的稳定变量文件 ID（如 `auto_custom_vars__ref__*__示例项目_第七关` / `auto_custom_vars__data__*__示例项目_第七关`），由 `sync-custom-vars` 维护。
- `布质门帘_1077936129.json`：作为第七关门实体模板，默认挂载 `server_test_project_level7_door_controller`（门开关与关闭完成广播）。
- 选关预览“关卡展示元件”：第 4/5/8 关提供合并后的单母体模板（`第四关展示元件`/`第五关展示元件`/`第八关展示元件`），用于替代历史 `展示元件1/2` 的双元件组合；展示元件名称在本目录内保持唯一，避免 `component_key:<name>` 解析歧义。

## 注意事项
- JSON 使用 UTF-8；引用以 `template_id` 为主键，文件名仅用于浏览。
- 不要手工随意改名/移动/删除文件；通过资源管理器或工具入口维护索引与归属。
- 若 `metadata.guid` 用于绑定/查找，同一存档作用域内必须唯一。
- 修改后跑一次：`python -X utf8 -m app.cli.graph_tools validate-project --package-id <package_id>`。
