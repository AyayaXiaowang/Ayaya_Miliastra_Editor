"""Todo 详情文档构建器插件包。

每个模块通过 `app.ui.todo.todo_detail_builder_registry` 注册一个或多个 detail_type 的构建器。
新增 detail_type 时优先新建模块并注册，避免修改中心分发文件造成冲突。
"""


