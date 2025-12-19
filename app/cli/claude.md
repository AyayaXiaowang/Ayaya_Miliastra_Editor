# 目录用途
CLI 与批处理入口（解析参数→调用 `engine` / `plugins` → 输出结果）。

# 公共 API
无（仅可执行入口）。

# 依赖边界
- 允许依赖：`engine/*`（通过公共 API）、`plugins/*`
- 禁止依赖：`core/*`（应使用 `engine` 公共 API 替代）、实现业务规则（规则必须在 `engine`）

# 当前状态
- 解析/校验等能力优先使用 `engine` 公共 API（`from engine import ...`）；运行时绑定的源码生成器位于 `app.codegen`，CLI 在需要“导出可运行代码”时可从 `app.codegen` 导入。
- 所有 CLI 入口脚本均位于本目录；根目录不再提供同名 Python 薄包装脚本，但允许提供 OS 级便捷启动入口（如 `run_app.bat` / `run_app.ps1`），其内部仍必须使用 `python -m ...`
- CLI 工作流主要围绕“AI/脚本写 Graph Code → 引擎解析/校验/排版 → 自动化脚本在真实编辑器中搭图”设计，仅做静态建模与生成，不在本地执行节点实际业务逻辑。
- `run_app.py` 作为 UI 启动入口，负责预热 OCR 引擎、在创建 `QApplication` 之前加载并应用用户设置（含界面主题模式与日志详细程度），统一在启动阶段通过 `settings.NODE_IMPL_LOG_VERBOSE` 打开信息级日志以确保控制台可见关键进度，然后创建主窗口；安全声明弹窗统一通过 `ui.foundation.dialog_utils` 的封装接口弹出，包含“我已知晓/不再提醒”两种选择，并将“不再提醒”状态写回 `settings.SAFETY_NOTICE_SUPPRESSED`；同时兼容 PyInstaller 冻结运行：默认以 **exe 所在目录** 作为工作区，并在启动阶段 `chdir` 到该目录（要求外置 `assets/` 与 exe 同级）。

# 注意事项
- PowerShell 环境下逐行执行命令，不使用 `&&`。
 - 典型入口：
  - `run_app.py`：启动应用主窗口（推荐命令：`python -X utf8 -m app.cli.run_app`）。
  - `convert_graph_to_executable.py`：将节点图导出为可执行代码（推荐命令：`python -X utf8 -m app.cli.convert_graph_to_executable`）。
- CLI 输出的“运行生成文件”提示需包含 `-X utf8` 且对路径加引号，避免中文路径/空格路径在 PowerShell 下解析异常。
- 导入规范：默认统一从 `engine` 导入，如 `from engine import GraphCodeParser, get_node_registry, log_info`；UI 相关统一使用 `app.ui.*`（不再制造顶层包名 `ui`，避免同一模块被导入两份）。
- 所有 CLI 入口应在导入/调用布局、缓存等依赖 workspace_root 的逻辑前调用 `settings.set_config_path(workspace_root)`，避免 settings 未初始化导致布局/注册表上下文构建失败。
- 错误输出：优先使用 `output_stream = sys.__stdout__ or sys.stdout`，避免直接访问 `sys.__stdout__` 引发可空属性检查，并兼容无原始流缺失的场景。
- 对外入口必须在启动阶段提示“仅用于离线教学/禁止接入官方服务器”的安全声明；`run_app.py` 已在控制台与 UI 弹窗双重提示，新增入口需保持一致。
- 安全声明弹窗提供“不再提醒”按钮，状态由 `settings.SAFETY_NOTICE_SUPPRESSED` 管理，需要复用该配置以确保提示一致。

