# tests 目录

## 目录用途
存放最小可运行的单元测试与轻量级用例，用于在不依赖完整主窗口或真实资源库的前提下验证关键逻辑是否按预期工作。当前既覆盖 Todo 执行规划与当前步骤解析等纯逻辑能力，也包含对节点图、信号定义以及资源索引（如战斗预设与管理配置 JSON 扫描）的引擎层回归测试，便于在命令行下快速回归。

## 当前状态

- 分类目录（按领域拆分；具体用例说明见各目录内 `claude.md`）：
  - `tests/validate/`：校验层/语法约束与规则类回归（`validate_files` 等入口）。
  - `tests/layout/`：自动排版、分块、跨块复制与布局不变量回归。
  - `tests/graph/`：解析器/语义 Pass/同进程重解析隔离与节点管线推导回归。
  - `tests/composite/`：复合节点发现策略、管理器依赖护栏与模板示例回归。
  - `tests/todo/`：Todo 核心逻辑与执行规划回归。
  - `tests/resources/`：资源库/索引/扫描策略回归。
  - `tests/tooling/`：仓库护栏与基础契约（导入路径、codegen bootstrap、全仓编译等）。
  - `tests/ui/`：UI 相关（含 PyQt6 最小构造/冒烟回归）。
  - `tests/automation/`：automation 协议/契约与视觉参数边界回归（尽量不依赖真实外设环境）。
  - `tests/common/`：`app/common` 等轻量共享模块的契约/缓存一致性回归。
  - `tests/_helpers/`：测试辅助模块（非测试用例），用于路径等公共逻辑收敛。


## 测试编写规则（重构友好）

- 测试应锁住**行为/契约**（输入 → 输出 / 退出码 / 报告 schema / 文件落盘结果），而不是锁住**内部结构**（私有函数、调用顺序、临时数据结构）。
- 优先覆盖稳定边界：
  - `engine.*` 公共 API（解析/校验/布局/资源索引等）
  - `app.cli.graph_tools` CLI（返回码 + `--json` 报告 schema）
  - 关键模型的序列化格式与不变量（例如 manifest diff 规则、布局折返边约束等）
- 谨慎使用 mock：仅在隔离外设/OCR/线程时序等不确定性时使用；mock 目标应是“边界接口”，避免对内部实现做调用次数/顺序断言导致重构阻塞。
- 用例输入必须可复现：优先使用仓库内公开模板示例（`assets/资源库/**/模板示例_*`），或在 `tmp_path` 下构造最小工作区/样例文件；禁止依赖本地私有资源与真实编辑器环境。


## 注意事项

- 当前大多数测试仍为纯逻辑测试，不创建 `QApplication` 实例；个别测试会通过 `GraphCodeParser` 和信号 Schema 视图访问节点库与信号定义代码资源，但不会修改实际资源文件，可在命令行通过 `pytest tests` 或 `python -m pytest tests` 运行。
- 资源可用性约束：测试应避免依赖任何“未被版本管理 / 可能为本地私有”的资源库内容；需要资源时优先：
  - 使用已公开的 `assets/资源库/**/模板示例_*` / `示例_*` 文件；或
  - 在 `tmp_path` 下构造最小资源目录与样例文件（例如 JSON 资源索引扫描类测试）。
  - 对“信号名称可解析”的规则测试，应使用仓库内已跟踪的示例/测试信号（例如 `测试信号_全部参数类型`），避免引用本地私有信号导致 CI 环境缺失。
- 如后续新增需要 UI 的测试（例如针对具体 QWidget 的交互），应在对应测试文件中显式创建和销毁 `QApplication`，并在导入任何 PyQt6 / UI 模块前完成 RapidOCR / onnxruntime 的初始化以避免 DLL 冲突。
- 导入规范：逻辑相关功能优先从 `app.models`、`app.ui.todo` 等应用层模块或 `engine` 公共 API 导入，避免在测试中直接依赖内部实现细节；如需节点定义或资源视图，应通过引擎提供的注册表与资源管理器构造最小上下文，而不是在测试中自行加载整套资源库。

## Pytest 启动配置

- `conftest.py` 仅将项目根目录加入 `sys.path`，确保可稳定导入 `app.*` / `engine.*`。
- **不要将 `<repo>/app` 加入 `sys.path`**：否则会导致 `ui.*` 与 `app.ui.*` 并存、同名类被加载两份而出现 `isinstance` 异常；因此测试代码应统一使用 `app.ui.*` 导入路径，而不是 `ui.*`。
- Windows 下的导入顺序约束：若环境存在 `rapidocr_onnxruntime`，tests 根 `conftest.py` 会在任何可能的 UI 导入前优先预热 RapidOCR，避免 PyQt6 / onnxruntime DLL 冲突导致随机崩溃。
- `conftest.py` 会调用 `settings.set_config_path(PROJECT_ROOT)` 并 `settings.load()`，为依赖 workspace_root 的引擎模块（如布局/节点库）提供单一真源，避免测试环境出现隐式路径回退导致的不稳定行为。
- 路径推导：测试中如需仓库根目录请使用 `tests._helpers.project_paths.get_repo_root()`，避免依赖 `Path(__file__).parents[...]`（测试分目录后深度会变化）。
- `tests/` 作为 Python package（包含 `__init__.py`）：确保 `tests._helpers.*` 在不同 pytest import-mode / site-packages 环境下都能稳定解析为本仓库目录（避免被外部同名包遮蔽）。
- 临时跳过清单：`tests/conftest.py` 内维护 `DISABLED_TEST_MODULES_REL`，会在 collection 后将对应测试模块统一标记为 `skip`，用于按需求暂时不执行“依赖本机样本/资源路径或口径未收敛”的用例；删除名单条目即可恢复执行。

---
注意：本文件不记录任何修改历史，仅描述 tests 目录的用途、当前状态与使用注意事项。


