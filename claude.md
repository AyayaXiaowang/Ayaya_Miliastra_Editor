# 项目根目录

## 项目定位
- 面向原神 UGC 的离线沙箱编辑器（非真实编辑器），用代码化的 Graph Code 与 JSON 资源管理整套存档（节点图、资源与配置）的完整生命周期。
- 核心功能：节点图/复合节点 Graph Code 引擎；资源与功能包管理；任务清单与执行监控；自动化执行桥（OCR+键鼠）与教学导向 UI。

## 目录用途
工程根目录，承载核心逻辑、UI、资源库与工具脚本的入口；`README.md` 面向最终用户，从“节点图维护/协作/重构痛点与 AI 教学优势”视角介绍产品定位，并汇总依赖环境（含自动化执行已验证的分辨率/缩放组合）、run_app 启动方式、节点图开发流程、常用工具说明、BUG 反馈交流入口与主要目录结构；同时包含常见问题（FAQ）：AI 画图方式、千星沙箱执行流程、自动同步范围、常用快捷键、UI 只读策略等。

## 关键子目录
- `engine/`：引擎核心层（图模型、节点规格、布局、验证、纯逻辑），提供稳定公共 API
- `plugins/`：插件层（节点实现 `@node_spec`，静态注册）
- `app/`：应用装配（UI、CLI、运行态管理）
- `assets/`：只读资源（模板、预设、OCR模板等）
- `tools/`：工具脚本（验证、生成、扫描、清理）

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
- **分层结构**：engine（纯逻辑）/ plugins（可插拔实现）/ app（UI/CLI/运行态）/ assets（只读资源）/ tools（工具脚本）
- **公共 API**：外部代码统一通过 `engine` 顶层导入，如 `from engine import GraphModel, get_node_registry, GraphCodeParser, validate_files`
- **静态注册**：节点实现通过 `plugins/nodes/registry.py` 静态注册表接入，避免运行时动态扫描
- **Graph Code**：节点图统一采用类结构 Python，由 AST/Graph Code 引擎解析与生成，用于静态建模、校验与排版，不在本地执行节点实际业务逻辑。
- **设计目的**：默认假设 Graph Code 多数由 AI/脚本编写，人类主要负责审阅与补充注释；引擎只关心“有哪些节点、如何连线和如何排版”，节点真实执行语义完全由官方编辑器/游戏环境负责。
- **索引+资源库分离**：功能包索引仅存引用，资源独立存储；统一由 `ResourceManager` 读写
- **节点库访问**：统一入口 `engine.get_node_registry(workspace).get_library()`；不要直接 `load_all_nodes`
- **导入入口终局**：`core.*` 与 `tools.engine.*` 不再作为导入入口，所有代码统一使用 `engine.*` / `app.*` / `plugins.*` 等正式路径

## 验证与工具
- 功能包校验：`python -X utf8 -m tools.validate.validate_package`
- 节点图/复合图校验：`python -X utf8 -m tools.validate.validate_graphs --all`（或传入单个/通配符路径仅校验指定图）
- Windows 便携版打包（exe，`assets/` 外置）：`powershell -ExecutionPolicy Bypass -File tools/packaging/build_windows_exe.ps1`（本地私有脚本，默认不进仓库；产物写入 `release/`）
- 缓存清理：`python -X utf8 -m tools.clear_caches --clear [--rebuild-index] [--rebuild-graph-caches]`
- 校验入口规范：校验相关脚本只保留在 `tools/validate/`，避免出现重复入口与转发层噪音。
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
- 根目录允许放置临时分析产物（例如 `project_file_paths.txt` 一类清单文件）辅助排查，但保持可清理、不可作为长期依赖。
- 本地打包/分发用的压缩包建议统一输出到 `release/`（可随时删除重建，避免与源码混放）。
- 本地运行产物与个人状态文件统一视为“噪音文件”，应被忽略且在文件树中隐藏（见根目录 `.gitignore` 与 `.cursorignore`）。
  - 资源库采用“默认忽略 + 白名单放行（示例_/模板示例_）”策略时，仍必须继续忽略 `__pycache__/`、`*.pyc` 等编译缓存；若曾被 git 跟踪，需要用 `git rm --cached` 从索引移除。
  - 节点图目录内 `_prelude.py/.pyi` 属于“前导脚本/类型桩”，用于让生成的节点图代码使用 `from _prelude import *` 时能自动注入 `sys.path` 并向编辑器暴露节点函数/占位类型；该文件需要被精确白名单放行并随仓库分发。
  - 资源库节点图目录提供 `assets/资源库/节点图/校验节点图.py` 作为“只校验资源库节点图”的快捷入口；该脚本也需要被白名单放行以便协作分发。
  - 节点图目录下的 `claude.md`（节点图根、server、模板示例、client 及其常用子目录）也通过精确白名单放行，确保协作时目录规则文档可见，同时不扩大资源库其它内容的入库范围。
- 文档规范：每个目录仅保留一个 `claude.md`；其余 Markdown 文档已清理。请在各目录的 `claude.md` 中维护“目录用途、当前状态、注意事项”的实时描述（不记录历史）。
- **安全声明**：本项目包含通过截图/OCR + 键鼠模拟，在《原神》客户端内的千星沙箱（UGC 编辑器）执行编辑操作的能力，用于将任务清单步骤同步到编辑器。请遵守官方用户协议与相关规则，并自行评估风险；不支持、也不鼓励将自动化用于 UGC 编辑器之外的任何游戏玩法场景。
 - 执行与视口能力的跨模块访问必须通过协议与公开 API：执行相关能力通过 `EditorExecutorProtocol` 等协议访问，视口与坐标系相关能力通过 `ViewportController` / `EditorExecutorWithViewport` 协议访问；禁止在 UI、配置或策略层直接调用 `executor._ensure_*` 等下划线私有方法，相关约束由 `tools/check_executor_private_access.py` 静态检查脚本守护。

## 状态恢复与清单同步
- 最近功能包：记录在 `资源库/功能包索引/packages.json` 的 `last_opened_package_id`。
- 任务清单：在“任务清单”页面切换功能包或保存设置后自动刷新。

## 当前状态
- 工程处于 **Beta** 迭代中；API、校验规则与文件结构可能快速演进，但分层结构已稳定，统一通过 `engine/*`、`app/*`、`plugins/*` 作为主要入口。
- `README.md` 已包含 BUG 反馈交流QQ群：1073774505。
- `README.md` 已包含常见问题（FAQ）：AI 如何“画”节点图、如何在千星沙箱执行、自动同步范围、全局热键（Ctrl+[ / Ctrl+] / Ctrl+P）。
- `README.md` 的“运行环境”不强制 PowerShell 版本；常用命令只要求终端能运行 `python/pip`（打包 `.ps1` 脚本仍需用 PowerShell 执行）。
- 节点图源码（如 `assets/资源库/节点图/` 下的 Graph Code 文件）主要依赖引擎验证与自检；类型检查配置通过 `pyrightconfig.json` 控制，避免将节点图 DSL 语法误判为常规 Python 类型错误。
- 依赖已提供“直接依赖清单 + 版本约束锁”：`requirements.txt`（直接依赖）、`constraints.txt`（关键依赖钉死）、`requirements-dev.txt`（测试/开发）。
- `claude_audit.md` 记录全仓 `claude.md` 巡检清单与完成状态，便于逐项核对。

## 发布与使用要点
- 仓库中只包含引擎、插件、应用装配和示例资源，运行期缓存与个人配置由本地环境自动生成和管理。
- 展示型发布策略：`docs/` 与 `projects/` 不随仓库分发；`tests/` 公开并用于 CI 回归。公开目录的 `claude.md` 会被版本管理；私有目录仍通过 `.gitignore` 保持不公开。
- 运行期缓存统一位于工作区根目录 `app/runtime/cache/` 且应被忽略；任何将缓存写入到其它目录的情况都应视为工作区根目录注入错误，需要先修正启动/脚本入口的 `workspace_path` 传参。
- `user_settings.json` 为本地设置文件：默认落在 `app/runtime/cache/user_settings.json`。
- 资源库 `assets/资源库/` 既可用于随仓库分发的示例资源，也可作为本地工作的资源根目录；默认仅版本管理一小部分“示例/模板示例”与官方教学用资源（包含少量模板示例节点图依赖的信号定义），其余本地工作内容通过 `.gitignore` 策略保持私有。
- 运行期缓存缺失不影响首次启动，必要时会在使用过程中自动生成或通过工具重建。
- GitHub 基础协作与回归：`.github/workflows/ci.yml`（Windows + pytest），`CONTRIBUTING.md`（贡献指南），`SECURITY.md`（安全反馈与范围）。
- 许可：本项目遵循 GNU General Public License v3.0；详见根目录 `LICENSE`。

—— 本文件仅描述当前的“目录用途 / 当前状态 / 注意事项”，不保留修改记录。
