## 目录用途
命令行入口集合：解析参数后调用 `engine` / `plugins` 的公共能力，提供校验、诊断、导出等离线工具；同时承载 UI 启动入口（以模块方式运行）。

## 当前状态
- 推荐 UI 启动命令：`python -X utf8 -m app.cli.run_app`（启动装配由 `app.bootstrap` 执行）。
- 工具入口主要集中在 `app.cli.graph_tools`；子命令的实现与注册按领域拆分在 `app/cli/commands/`。
- 读取代码资源（如 `自定义变量注册表.py`）的 CLI（例如 `sync-custom-vars`）统一使用 AST 静态提取（`engine.resources.auto_custom_variable_registry`），避免 import 执行顶层代码与副作用；其中 `sync-custom-vars` 已调整为 refs-only：仅同步引用点与第三方存放实体资源，不再生成 `自动分配_*.py` 变量文件。
- 自定义变量注册表的 `owner` 直接填实体/元件 ID 或 `player`/`level` 关键字（支持 `str | list[str]` 多 owner）；`sync-custom-vars` 按 owner 值在实体摆放/元件库中查找实体并追加变量文件引用到对应模板。
- UI 占位符校验（`validate-ui`）为只读校验（不写盘、不提供 `--fix` 自动生成变量定义），并跳过 `UI源码/__hook_tests__/` 夹具目录；支持 typed dict alias（例如 `字符串-整数字典`），允许 `lv.<字典变量>.<key>` 的一层键路径校验。
- `local_graph_sim.py`：本地节点图模拟器 CLI（serve/click/emit-signal）；`serve` 支持 `--ready-file` 将启动后的 URL/端口写入 JSON，供 UI 父进程读取。

## 注意事项
- 统一使用模块方式运行（`python -m ...`），避免 `__package__` 与工作区根目录推导异常。
- PowerShell 不支持 `&&`，文档/输出中的命令应按行给出。
- `workspace_root` 推导与 settings 初始化需在调用依赖工作区的逻辑前完成，且应复用 `engine.utils.workspace` 的统一入口。

