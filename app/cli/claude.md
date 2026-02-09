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
- `run_app.py` 作为 UI 启动入口：仅负责 CLI 参数解析与 workspace_root 推导（`--root` / `--print-workspace` / `--diagnose`），以及 settings 注入与启动开关（`--quiet` / `--log-file` / `--no-ocr-preload` / `--no-ui-freeze-watchdog` / `--no-safety-dialog`）；具体 UI 启动装配委托给 `app.bootstrap.ui_bootstrap`：确保 **OCR 预热发生在 PyQt6 导入之前**（避免 DLL 冲突），创建 `QApplication`、应用主题、安装全局异常钩子（控制台输出 + UI 错误弹窗 + 可复制 traceback）、记录应用前后台状态变化、可选启用 UI 卡死看门狗（超阈值 dump 全线程堆栈到 `settings.RUNTIME_CACHE_ROOT/ui_freeze_traceback.log`），然后创建并展示 `MainWindowV2`；安全声明在控制台与 UI 弹窗双重提示（弹窗支持“不再提醒”，状态写入 `settings.SAFETY_NOTICE_SUPPRESSED`）。
- `graph_tools.py` 额外提供 `validate-ui`：扫描项目存档 `管理配置/UI源码/*.html`，静态校验 UI 变量引用（moustache 占位符 + Workbench 进度条绑定 data-*）是否遵循规范，用于在导出/打包前提前发现 UI 变量引用问题。
- `graph_tools.py` 提供 `extract-ui-defaults`：从 UI HTML 的 `data-ui-variable-defaults` 抽取默认值，并按 `lv.xxx` 拆分导出为 `xxx` 字典 JSON（同时输出“保留原类型 / 全部字符串化”两份），用于一键同步 UI 字典默认值到工具链/写回阶段。
- `graph_tools.py` 提供 `apply-ui-defaults`：将 UI HTML 的 `data-ui-variable-defaults` 一键写入项目存档的关卡变量默认值文件（`管理配置/关卡变量/自定义变量/UI_关卡变量_自动生成.py`），用于在导出前补齐关卡实体自定义变量的默认结构与默认值。
 - 支持 `--all`：扫描 `管理配置/UI源码/` 下所有 HTML（仅处理包含该属性的页面）并合并写入。
 - 注意：进度条绑定（`data-progress-*-var`）只允许标量变量名（`lv.xxx / ps.xxx`，变量名不含 `.`），禁止写成 `lv.dict.key`。字典键默认结构请在 `data-ui-variable-defaults` 中显式声明；进度条镜像标量变量可交给 `validate-ui --fix` 自动生成/升级。
 - 默认只增/改不删；如需自动删键，可加 `--prune-managed-keys`（仅删除“曾由 defaults 管理过、且本轮已不再声明”的键），避免误删无关内容。
- `graph_tools.py` 提供 `audit-custom-vars`：扫描节点图源码中对实体自定义变量的读写调用（`获取自定义变量/设置自定义变量`），输出 where-used 报告（JSON + Markdown）到 `app/runtime/cache/variable_audit/<package_id>/`，用于重构改名与“变量挂载点/使用点”快速定位（只做静态分析，不影响运行时）。
- `graph_tools.py` 提供 `validate-all`：一键全量校验（不短路，汇总退出码）：
 - `validate-project`：项目存档级资源/挂载关系校验（可选 QuickFix：`--fix/--fix-dry-run`）
 - `validate-ui`：UI源码变量占位符语法 + 来源闭包校验（可选 QuickFix：`--fix/--fix-dry-run`）
 - `validate-graphs`：节点图/复合节点校验（可选 QuickFix：`--fix/--fix-dry-run`）；`validate-all` 默认仅将 **error** 视为失败，warning/info 会输出但不阻断（需要“0 warning 才通过”可加 `--fail-on-warning`）
- `local_graph_sim.py`：节点图 + UI 本地测试入口
  - `serve`：启动本地 HTTP server，用浏览器承载 UI HTML，并支持“点击注入 -> 图逻辑执行 -> UI patch 回显（显隐/状态切换）”
    - 可选启动后自动发送一次信号用于首帧初始化
    - 支持 `--present-players` 配置在场玩家数量（影响“等待其他玩家/投票门槛/在场玩家列表”等逻辑）
    - 支持 `--extra-graph/--extra-owner`：在同一会话中额外挂载多个节点图（主图联动服务图/流程图等）
  - `click/emit-signal`：一次性注入 UI 点击或发送信号并输出 patches（不启动 server），用于快速回归与脚本化验证
    - 支持 `--extra-graph/--extra-owner` 多图挂载
    - 支持 `--dump-state`：同时输出实体/变量快照（包含挂载关系与实体自定义变量）

# 注意事项
- PowerShell 环境下逐行执行命令，不使用 `&&`。
 - 典型入口：
  - `run_app.py`：启动应用主窗口（推荐命令：`python -X utf8 -m app.cli.run_app`）。
  - `convert_graph_to_executable.py`：将节点图导出为可执行代码（推荐命令：`python -X utf8 -m app.cli.convert_graph_to_executable`）。
  - `graph_author_tools.py`：Graph Code 写作辅助入口（生成节点函数 `.pyi` 类型桩、生成/刷新 `GV.xxx` 变量名常量块）（推荐命令：`python -X utf8 -m app.cli.graph_author_tools --help`）。
- `graph_tools.py`：便携版工具入口（校验/诊断），用于打包产物中的 `Ayaya_Miliastra_Editor_Tools.exe`；冻结运行时默认以 exe 所在目录为工作区根目录（要求 `assets/` 与 exe 同级外置），提供 `validate-graphs` / `validate-file` / `validate-project` 等命令；默认目标覆盖资源库多根目录布局（`共享/` + `项目存档/<package_id>/`）下的节点图与复合节点（`validate-package` 仅作为兼容旧名保留，不再对外推荐）。
 - `validate-all`：全量校验入口（覆盖项目存档、UI源码变量、节点图/复合节点），用于“写一个资源就能顺带发现关联处问题”的统一校验工作流；支持 `--package-id` 仅校验单个存档，默认不传则校验全部项目存档并对节点图/复合节点做全量扫描。
  - `setup-doc-links`：为已有项目存档补齐共享文档 Junction（`文档/共享文档` → `assets/资源库/共享/文档`），实现“零复制共享”。
  - `cleanup-external-dumps`：清理资源库下的外部解析产物目录（例如 `assets/资源库/存档包`），避免把外部工具输出混进资源库语义；支持 `--action move/delete` 与 `--dry-run`。
  - `validate-graphs` CLI 运行器统一复用 `engine.validate.graph_validation_cli_runner`：targets 收集/路径归一化复用 `engine.validate.graph_validation_targets`，编排复用 `engine.validate.graph_validation_orchestrator`（含 legacy 归属校验与可选复合结构补齐），报告复用 `engine.validate.graph_validation_cli_reporting`；`--json` 模式仅输出 JSON；Windows 控制台 UTF-8 输出流包装复用 `engine.utils.logging.console_encoding`。
  - `validate-graphs` 支持可选 QuickFix（默认关闭）：`--fix/--fix-dry-run` 用于在校验前补齐可自动修复的缺失项（例如 GRAPH_VARIABLES 未声明的节点图变量）。
  - `validate-file` 复用 `engine.validate.node_graph_validator.validate_file` 执行单文件校验，并统一使用 `format_validate_file_report` 生成文本报告，确保工具输出与节点图脚本自检口径一致；同样支持 `--fix/--fix-dry-run` 对单文件执行 QuickFix。
  - `validate-file --strict`：在打印报告前额外先执行一次 `GraphCodeParser(strict=True)` 的 fail-closed 严格解析（含作用域切换与 NodeRegistry 刷新），用于对齐资源加载/批量导出链路并提前发现 strict 下会拒绝解析的问题。
  - `validate-project` 支持可选 QuickFix（默认关闭）：`--fix/--fix-dry-run` 用于修正“目录即分类”的代码级管理资源声明（例如结构体定义放在 `基础结构体/` 或 `局内存档结构体/` 下时，自动对齐其 `STRUCT_TYPE` 与 `STRUCT_PAYLOAD.struct_type/struct_ype`）。
- `validate-ui`：扫描项目存档 `管理配置/UI源码/*.html`，校验 UI 变量引用的**语法 + 来源闭包**：
  - 文本占位符语法：仅允许 `{{ps./p1~p8./lv.}}` 与 `{1:ps.}` 两种形式，路径段不得包含空白。
  - 进度条绑定语法：支持 `data-progress-current-var/min-var/max-var="ps./p1~p8./lv."`（不带 `{{}}` 外壳），其中 min/max 允许数字常量（如 `0/100`）。**绑定表达式必须为标量变量名（单段）**，禁止 `lv.dict.key` / `ps.dict.key`。
  - `lv.*`：必须能解析到【关卡变量/自定义变量】中的 `variable_name`；若为文本占位符的字典键路径（`lv.dict.key`），则要求默认值结构中存在对应键（进度条绑定不支持字典键路径）。
  - 玩家变量：
    - `ps.*`：共享玩家变量（不区分玩家槽位），必须在**所有玩家模板**引用的变量文件集合中都存在（避免导出后“某些模板缺变量才暴露”）。
    - `p1~p8.*`：按玩家槽位区分，只要求在对应槽位的玩家模板中存在（允许不同槽位模板变量类型不同）。
    - 若为字典键路径同样检查默认值键存在性（校验范围同上）。
    - 玩家模板槽位集合以 `PackageIndex.resources.combat_presets.player_templates` 的顺序为准（覆盖共享 + 当前存档）；若 UI 中出现玩家占位符但当前包未配置任何玩家模板，则视为无法闭包校验并直接报错提示补齐模板。
  - 并支持 `--fix/--fix-dry-run`：根据 UI 引用自动生成/补齐变量定义文件，且会以“追加”方式更新玩家模板 `metadata.custom_variable_file`（支持字符串或列表，多文件引用不覆盖既有引用），用于在导出/打包前提前发现并修复 UI 变量引用问题；同时会清理不再被 UI 源码引用的 `metadata.category=UI自动生成` 变量，避免变量文件长期堆积。
  - 玩家模板 `metadata.custom_variable_file` 支持 **字符串或列表**：列表表示引用多个变量文件；`validate-ui --fix` 会在不丢失既有引用的前提下追加自动生成文件。
- CLI 输出的“运行生成文件”提示需包含 `-X utf8` 且对路径加引号，避免中文路径/空格路径在 PowerShell 下解析异常。
- 导入规范：默认统一从 `engine` 导入，如 `from engine import GraphCodeParser, get_node_registry, log_info`；UI 相关统一使用 `app.ui.*`（不再制造顶层包名 `ui`，避免同一模块被导入两份）。
- 所有 CLI 入口的 `workspace_root` 推断与 settings 初始化应统一走 `engine.utils.workspace`：用 `resolve_workspace_root(--root)` 推断工作区根目录，并在导入/调用布局、缓存等依赖 workspace_root 的逻辑前调用 `init_settings_for_workspace(workspace_root=..., load_user_settings=...)`（UI 入口需 load；纯校验/导出工具通常只 set_config_path 不 load），避免 settings 未初始化导致布局/注册表上下文构建失败或缓存路径漂移。
- 错误输出：优先使用 `output_stream = sys.__stdout__ or sys.stdout`，避免直接访问 `sys.__stdout__` 引发可空属性检查，并兼容无原始流缺失的场景。
- 对外入口必须在启动阶段提示“仅用于离线教学/禁止接入官方服务器”的安全声明；`run_app.py` 已在控制台与 UI 弹窗双重提示，新增入口需保持一致。
- 安全声明弹窗提供“不再提醒”按钮，状态由 `settings.SAFETY_NOTICE_SUPPRESSED` 管理，需要复用该配置以确保提示一致。

