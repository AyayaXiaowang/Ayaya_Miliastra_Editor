# 项目根目录

## 项目定位
- 面向原神 UGC 的离线沙箱编辑器（非真实编辑器），用代码化的 Graph Code 与 JSON 资源管理整套存档（节点图、资源与配置）的完整生命周期。
- 核心功能：节点图/复合节点 Graph Code 引擎；资源与项目存档管理；任务清单与执行监控；自动化执行桥（OCR+键鼠）与教学导向 UI。

## 目录用途
工程根目录，承载核心逻辑、UI、资源库与工具脚本的入口；`README.md` 面向最终用户，从“节点图维护/协作/重构痛点与 AI 教学优势”视角介绍产品定位，并汇总依赖环境（含自动化执行已验证的分辨率/缩放组合）、run_app 启动方式、节点图开发流程、常用工具说明、BUG 反馈交流入口与主要目录结构；同时包含常见问题（FAQ）：AI 画图方式、千星沙箱执行流程、自动同步范围、常用快捷键、UI 只读策略等。

## 关键子目录
- `engine/`：引擎核心层（图模型、节点规格、布局、验证、纯逻辑），提供稳定公共 API
- `plugins/`：插件层（节点实现 `@node_spec`，静态注册）
- `app/`：应用装配（UI、CLI、运行态管理）
- `assets/`：只读资源（模板、预设、OCR模板等）
- `release/`：本地打包产物目录（默认忽略，可随时删除重建）
 - `common.css`：私有 Web 工具复用的基础样式（dark reset + 主题变量 + 常用类），供 `private_extensions/**.html` 直接引用

## 运行启动
```bash
python -X utf8 -m app.cli.run_app
```
推荐环境：Windows 10/11 + Python 3.10 - 3.12（项目使用 match/case、PEP 604 等 3.10+ 语法特性，推荐 3.10.x 作为基线；当前依赖锁不支持 Python 3.13）。
说明：本仓库多数 CLI/校验脚本要求以模块方式运行（`python -m ...`）以确保 `__package__/__spec__` 正确；若直接运行 `.py` 文件提示“请使用模块方式运行”，按提示改用 `-m` 即可。

### VSCode 调试入口（运行当前文件 / F5）
- `run_app_debug.py`：面向 VSCode/IDE 调试的启动脚本（内部通过 `runpy` 以模块方式执行 `app.cli.run_app`）
- 更短命令：`python -X utf8 -m app`

## 当前架构要点
- **分层结构**：engine（纯逻辑）/ plugins（可插拔实现）/ app（UI/CLI/运行态）/ assets（只读资源）
- **公共 API**：外部代码统一通过 `engine` 顶层导入，如 `from engine import GraphModel, get_node_registry, GraphCodeParser, validate_files`
- **节点发现（V2 AST 管线）**：节点实现位于 `plugins/nodes/**.py`，由 `engine.nodes.pipeline` 通过 AST 解析 `@node_spec` 构建节点库（**只解析不导入**），避免导入副作用与运行时动态扫描
- **Graph Code**：节点图统一采用类结构 Python，由 AST/Graph Code 引擎解析与生成，用于静态建模、校验与排版，不在本地执行节点实际业务逻辑。
- **设计目的**：默认假设 Graph Code 多数由 AI/脚本编写，人类主要负责审阅与补充注释；引擎只关心“有哪些节点、如何连线和如何排版”，节点真实执行语义完全由官方编辑器/游戏环境负责。
- **索引+资源库分离**：项目存档索引仅存引用，资源独立存储；统一由 `ResourceManager` 读写
- **节点库访问**：统一入口 `engine.get_node_registry(workspace).get_library()`；不要在 UI/工具侧自行扫描 `plugins/nodes/**`
- **导入入口终局**：不再使用历史兼容入口（如 `core.*` 等），所有代码统一使用 `engine.*` / `app.*` / `plugins.*` 等正式路径

## 验证与工具
- 节点图/复合节点校验（源码环境）：`python -X utf8 -m app.cli.graph_tools validate-graphs --all`
- 节点图单文件自检（源码环境）：`python -X utf8 -m app.cli.graph_tools validate-file <图文件路径>`
- 项目存档校验（目录模式，源码环境）：`python -X utf8 -m app.cli.graph_tools validate-project [--package-id <id>]`（`validate-package` 为兼容旧名）
- release（无 Python）：使用 `Ayaya_Miliastra_Editor_Tools.exe validate-graphs/validate-file/validate-project`（`validate-package` 为兼容旧名）
- 内部构建/迁移/清理等“杂项工具链”不随仓库公开分发（已加入 `.gitignore`），避免与产品必备校验能力混杂。
- 后台输入/OCR/执行桥：统一入口 `app.automation.*`，不再提供 `core.automation` 兼容层。

## 注意事项
- **UI 仅支持查看**：信号、结构体、复合节点、节点图在 UI 中仅允许查看，不支持修改；所有修改必须在对应的 Python 源文件中进行。
- OCR 引擎预加载：在任何 PyQt6 导入前导入 `rapidocr_onnxruntime`，避免 DLL 冲突。
- 根入口/主程序不使用 `try/except`；错误直接抛出，由 `sys.excepthook` 处理。
- 控制台输出使用 ASCII 安全替换（仅符号），中文不变。
- 根入口与 CLI/工具脚本的控制台输出统一经由 `engine.utils.logging.logger`（`log_info/log_warn/log_error`）；
  - 信息级输出可通过 `engine.configs.settings.settings.NODE_IMPL_LOG_VERBOSE` 控制；
  - CLI/工具脚本默认在入口开启信息级输出，确保用户可见进度与结果。
- 外部进程调用请使用 `app.automation.input.subprocess_runner.run_process(...)`（返回 `ProcessResult`）。
- 端口类型设置：泛型家族端口必须在“设置类型”步骤选定具体类型；最终点击前做硬性校验。
- 图变量与实体输入校验统一由 `app.runtime.engine.node_graph_validator` 与 `engine.validate` 负责。
- 根目录允许放置临时分析产物（例如 `project_file_paths.txt` 一类清单文件）辅助排查，但保持可清理、不可作为长期依赖；临时调试脚本建议使用 `.tmp_*.py` 命名并保持忽略。
- 本地打包/分发用的压缩包建议统一输出到 `release/`（可随时删除重建，避免与源码混放；默认应忽略，仅版本化 `release/claude.md`）。
- 打包产物与临时工作目录应保持忽略（见 `.gitignore` 与 `.cursorignore`）。
- 本地运行产物与个人状态文件统一视为“噪音文件”，应被忽略且在文件树中隐藏（见根目录 `.gitignore` 与 `.cursorignore`）。
 - 资源库采用“默认忽略 + 白名单放行（示例_/模板示例_）”策略；其中 `assets/资源库/项目存档/` 默认忽略，仅版本化 `assets/资源库/项目存档/示例项目模板/`；仍必须继续忽略 `__pycache__/`、`*.pyc` 等编译缓存。若曾被 git 跟踪，需要用 `git rm --cached` 从索引移除。
  - 节点图脚本不再依赖资源库内的本地 prelude 文件（也不再对白名单放行本地 prelude 文件）：统一在文件头部注入 workspace_root（project_root + assets）到 `sys.path`，并直接导入 `app.runtime.engine.graph_prelude_{server|client}`；从而避免“每个项目都要维护一份 prelude”的协作成本。
 - 资源库节点图目录允许存在 `校验节点图.py` 作为“只校验本目录下节点图”的快捷入口；该脚本也需要被白名单放行以便协作分发。
  - 共享节点图目录（`assets/资源库/共享/节点图`）下的 `claude.md`（节点图根、server、模板示例、client 及其常用子目录）通过精确白名单放行，确保协作时目录规则文档可见，同时不扩大资源库其它内容的入库范围。
- 插件目录的版本化策略：`plugins/nodes/**` 为公共节点实现并入库；`plugins/` 下除 nodes 与必要文件外默认忽略，便于放置本地私有扩展而不误提交（见 `.gitignore`）。
  - 即使 `plugins/nodes/**` 作为源码目录需要入库，也必须继续忽略其中的 `__pycache__/`、`*.pyc` 等编译缓存（否则会造成工作区“文件污染”与误提交风险）。
- 公开仓库中的 `claude.md` 视为公开文档：不要写入任何私有/绝密实现细节；本地私有扩展建议放在工作区根目录 `private_extensions/`（默认忽略不入库）并在该目录中维护仅本机可见的说明文件。
- 文档规范：目录级规则/注意事项统一写在 `claude.md`；除 `docs/` 与少量明确的索引/诊断文档外，不在代码目录散落其他 Markdown。各目录 `claude.md` 只维护“目录用途 / 当前状态 / 注意事项”（不记录历史）。
- **安全声明**：本项目包含通过截图/OCR + 键鼠模拟，在《原神》客户端内的千星沙箱（UGC 编辑器）执行编辑操作的能力，用于将任务清单步骤同步到编辑器。请遵守官方用户协议与相关规则，并自行评估风险；不支持、也不鼓励将自动化用于 UGC 编辑器之外的任何游戏玩法场景。
 - 执行与视口能力的跨模块访问必须通过协议与公开 API：执行相关能力通过 `EditorExecutorProtocol` 等协议访问，视口与坐标系相关能力通过 `ViewportController` / `EditorExecutorWithViewport` 协议访问；禁止在 UI、配置或策略层直接调用 `executor._ensure_*` 等下划线私有方法，应由静态检查脚本在开发期守护。

## 状态恢复与清单同步
- 最近打开存档：记录在 `app/runtime/package_state.json` 的 `last_opened_package_id`。
- 任务清单：在“任务清单”页面切换项目存档或保存设置后自动刷新。

## 当前状态
- 工程处于 **Beta** 迭代中；API、校验规则与文件结构可能快速演进，但分层结构已稳定，统一通过 `engine/*`、`app/*`、`plugins/*` 作为主要入口。
- `README.md` 已包含 BUG 反馈交流QQ群：1073774505。
- `README.md` 已包含常见问题（FAQ）：AI 如何“画”节点图、如何在千星沙箱执行、自动同步范围、全局热键（Ctrl+[ / Ctrl+] / Ctrl+P）。
- `README.md` 的“运行环境”不强制 PowerShell 版本；常用命令只要求终端能运行 `python/pip`（打包 `.ps1` 脚本仍需用 PowerShell 执行）。
- 节点图源码（如 `assets/资源库/共享/节点图/` 与 `assets/资源库/项目存档/<package_id>/节点图/` 下的 Graph Code 文件）主要依赖引擎验证与自检；类型检查配置通过 `pyrightconfig.json` 控制，避免将节点图 DSL 语法误判为常规 Python 类型错误。
- 依赖已提供“直接依赖清单 + 版本约束锁”：`requirements.txt`（直接依赖）、`constraints.txt`（关键依赖钉死）、`requirements-dev.txt`（测试/开发）。
- 全仓 `claude.md` 不维护集中巡检清单文件；以各目录 `claude.md` 的“实时现状描述”为准。

## 发布与使用要点
- 仓库中只包含引擎、插件、应用装配和示例资源，运行期缓存与个人配置由本地环境自动生成和管理。
- 仓库分发策略：项目通常以“整仓（除 ignore）”形式发布到 GitHub；面向使用者的公开文档入口为 `docs/用户必读.md`。`tests/` 用于 CI 回归；私有资源仍通过 `.gitignore` 保持不公开。
- 运行期缓存统一位于 `settings.RUNTIME_CACHE_ROOT`（默认 `app/runtime/cache/`）且应被忽略；任何将缓存写入到其它目录的情况都应视为工作区根目录注入错误，需要先修正启动/脚本入口的 `workspace_path` 传参。
- `user_settings.json` 为本地设置文件：默认落在 `app/runtime/cache/user_settings.json`。
- 资源库 `assets/资源库/` 既可用于随仓库分发的示例资源，也可作为本地工作的资源根目录；默认仅版本管理一小部分“示例/模板示例”与 `assets/资源库/项目存档/示例项目模板/`，其余本地工作内容通过 `.gitignore` 策略保持私有。
- 运行期缓存缺失不影响首次启动，必要时会在使用过程中自动生成或通过工具重建。
- GitHub 基础协作与回归：`.github/workflows/ci.yml`（Windows：节点库护栏 + 文档一致性 + pytest），`CONTRIBUTING.md`（贡献指南），`SECURITY.md`（安全反馈与范围）。
- 许可：本项目遵循 GNU General Public License v3.0；详见根目录 `LICENSE`。

—— 本文件仅描述当前的“目录用途 / 当前状态 / 注意事项”，不保留修改记录。
