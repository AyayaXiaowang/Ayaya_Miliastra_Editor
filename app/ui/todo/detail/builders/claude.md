## 目录用途
- 本目录承载 Todo 右侧详情面板的“结构化文档构建器”插件。
- 每个模块负责一组 `detail_type`（或前缀/谓词规则），并在导入时向 registry 注册 builder。

## 当前状态
- 详情文档的入口仍是 `app.ui.todo.todo_detail_renderer.TodoDetailBuilder.build_document()`，但其内部不再使用长链 if 分发，而是通过 `todo_detail_builder_registry` 查找已注册的 builder。
- 内置 builder 以“按领域拆分”的方式分布在本目录多个模块中（例如 root/category、template/instance、graph 相关等）。
- 模板“添加组件”（`detail_type="template_components_table"`）的详情说明来自 `engine.configs.components.component_registry.COMPONENT_DEFINITIONS`（通用组件注册表）。
- 领域通用 builder（如 combat/management 前缀）对 `info["data"]` 的形态保持兼容：支持 dict 与 list 两种常见结构，避免在用户高频切换任务时因数据格式差异导致详情构建崩溃。
- combat/management 的通用详情默认仅展示“字段/条目预览”，并将完整原始数据放入可折叠的“原始数据（data）”区，避免详情页被大 JSON 淹没。
- 节点图变量步骤（`detail_type="graph_variables_table"`）在详情文档中仅输出简短说明与引导文案，不在详情里渲染完整变量表格；变量清单浏览由右侧“图属性 → 节点图变量”承载。
- 节点图步骤的详情覆盖了 schema 中的全部 `graph_*` 与 `composite_*` 类型：默认输出可操作的定位字段（graph_id/node_id/端口等），原始 detail_info/params 等通过折叠区提供，便于排查而不打扰阅读。

## 注意事项
- 新增 detail_type 时：优先新增一个 builder 并在本目录注册；不要回到中心化 if-chain。
- Builder 代码应保持无 Qt 依赖，返回 `DetailDocument`；具体渲染由 `TodoDetailView` 完成。
- 避免在模块顶层导入重型依赖（例如规则总表/大常量表）；需要时在 builder 函数内延迟 import，配合 registry 的按需加载策略降低 UI 卡顿。
- 不使用 try/except 吞异常；构建失败直接抛出，方便定位问题。


