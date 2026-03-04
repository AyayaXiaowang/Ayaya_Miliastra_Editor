## 目录用途
存放“示例项目模板”项目存档的元件库模板（`TemplateConfig`）JSON 资源（`template_id` → 模板定义），用于新建项目时复制为初始模板集合。

## 当前状态
- 目录内包含模板复制时的基础示例模板与测试台模板。
- 模板的默认挂载节点图使用 `default_graphs`（graph_id 列表），其余字段按 `engine.graph.models.package_model.TemplateConfig` 结构组织。

## 注意事项
- `template_id` 需稳定且全局唯一（建议带包名后缀）；复制模板到新项目时，需按新包名调整 ID。
- `metadata.guid` 使用纯数字 ID（可用字符串包裹数字）表示；同一项目存档内需保持唯一，避免影响 GUID 索引/选择与引用解析。
- 模板变量不在模板 JSON 内直接定义；如需变量请在【管理配置/关卡变量】中用代码集中声明，并在模板 `metadata.custom_variable_file` 中绑定变量文件（`VARIABLE_FILE_ID`）。
- JSON 需保持 UTF-8 与合法语法；不要在资源目录中提交生成物（如 `__pycache__`）。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。


