## 目录用途
存放“测试项目”历史遗留的关卡变量文件（legacy）。这些文件通常用于迁移参考或对照，不作为当前存档运行时的主要变量真源。

## 当前状态
- 当前存档主流程优先使用 `管理配置/关卡变量/自定义变量注册表.py` + `sync-custom-vars` 生成的 `自动分配_*.py`（例如 `auto_custom_vars__player__测试项目` / `auto_custom_vars__level__测试项目`）。
- 本目录文件可能仍被工具链扫描用于校验/对照，但不应在模板 `metadata.custom_variable_file` 中继续引用。

## 注意事项
- 如需修改“正在使用”的变量定义，请改 `自定义变量注册表.py` 并运行 `python -X utf8 -m app.cli.graph_tools sync-custom-vars --package-id 测试项目`。
- 本目录仅保留必要的历史上下文，避免继续扩张；新增变量请写入正式目录 `自定义变量/`。

