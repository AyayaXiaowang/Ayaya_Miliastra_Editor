## 目录用途
- 负责千星沙箱编辑器的自动化执行：截图、OCR、节点/端口识别、坐标换算、键鼠输入、执行步骤编排等全部高危操作。
- 位于应用层（`app/automation`），高度依赖 Windows API、PIL、RapidOCR 等外部环境，仅保证在 Win10 下工作。
- 通过引擎提供的节点/图模型 API 获取逻辑数据，再结合视觉识别与输入控制完成“图执行器”职责。

## 子目录与主模块
- `capture/`：底层能力（DPI 感知、区域配置、截图、OCR、模板匹配、颜色扫描、鼠标操作、缓存）。统一从 `app.automation.capture` 导入。
- `input/`：键鼠输入、睡眠/日志/前景窗口管理与子进程执行（`common.py`, `win_input.py`, `subprocess_runner.py`）。所有时间控制与日志输出均经 `input.common`。
- `vision/`：节点/端口识别、一致化标题映射、一步式识别缓存、OCR 工具封装。运行路径只能通过 `app.automation.vision` 访问视觉结果。
- `editor/`：执行器协议与步骤编排（`executor_protocol.py`, `editor_executor.py`, `editor_exec_steps.py`, `editor_nodes.py`, `editor_connect.py`, `editor_mapping.py`, `editor_recognition/` 子包, `editor_zoom.py`, `executor_utils.py`, `view_mapping.py`）。其中：
  - `executor_protocol.py` 定义执行器相关协议：`EditorExecutorProtocol`（执行与节点/端口查询）、`ViewportController`（视口与坐标系控制）、`EditorExecutorWithViewport`（前两者的组合协议），以及输入/可视化等细分协议，供 UI 与自动化上层通过结构化契约访问能力；
  - `editor_executor.py` 提供标准实现 `EditorExecutor`，结构上同时满足 `EditorExecutorProtocol` 与 `ViewportController`，对外通过公开方法 `ensure_program_point_visible`、`get_program_viewport_rect` 与坐标换算接口暴露视口能力，内部的 `_ensure_program_point_visible` 等下划线方法仅作为本模块内部的实现细节入口，不用于跨模块调用。
  - `editor/automation_step_types.py` 收敛 graph_* 步骤类型与 fast-chain 白名单为纯数据配置，避免步骤字符串在多个模块之间隐式耦合；
- `config/`：节点参数注入、Settings 扫描、分支配置与辅助工具（`config_params.py`, `config_node_steps.py`, `config_params_helpers.py`, `settings_scanner.py`, `branch_config.py`）。
- `ports/`：端口结构、筛选器、变参/字典管理、三维向量输入、类型推断与类型设置（`_ports.py`, `port_picker.py`, `dict_ports.py`, `variadic_ports.py`, `vector3_input_handler.py`, `port_type_inference.py`, `port_type_steps.py`, `port_type_setter.py`, `port_types.py`, `_type_utils.py`）。端口 kind 归一化经 `_ports.normalize_kind_text` 统一输出 `flow/data/settings/select/warning/other`，供端口筛选、类型推断与 Settings/Warning/选择行识别共享，避免在执行器内手写字符串判断；其中 `port_type_steps` 在设置端口类型时，会优先复用结构体定义中的字段类型（例如“以键查询字典值”节点在结构体字段字典上按键查询时，其输出端口“值”的目标类型会优先采用该字段在结构体中声明的规范类型，例如 `GUID列表`），再回退到连线/默认推断，从而保证自动化执行与配置表语义一致；输入/输出两侧的端口类型设置流程拆分为“类型推断 / 端口定位 / UI 设置”三层辅助函数，便于在不依赖真实编辑器的前提下为规则演化和自动化行为添加单元测试。
- `runtime/`：真实执行器适配层（目前为 `real_executor.py`，实现 `EditorExecutorProtocol`）。
- `_static_checks/`：约束依赖边界与识别入口的脚本集合（禁止直接访问 `vision_bridge`、自定义中文正则等）。
- 根目录仅保留 `__init__.py` 与本说明文件，由 `AutomationFacade` 对外提供截图/输入/子进程门面，同时导出 `capture` 与 `input.common` 中的通用工具。

## 运行与协作
1. UI 发起执行 → `AutomationFacade` 或 `app.automation.editor.editor_executor.EditorExecutor` 接管任务。
2. `app.automation.editor.editor_exec_steps` 根据 todo 类型分派给 `editor_nodes`、`editor_connect`、`config`、`ports` 等模块。
3. 视觉能力统一经 `capture` + `vision`：截图/模板/OCR 先由 `capture` 完成，再由 `vision` 做识别与缓存管理，识别后若画布发生变化必须调用 `vision.invalidate_cache()`。
4. 所有键鼠输入、等待、日志由 `input` 子包提供，禁止直接 `time.sleep` 或 `print`。
5. 端口类型、参数值与分支配置通过 `ports`、`config` 的分步骤实现；Settings 扫描/映射要复用现有工具，避免在执行器内部堆叠杂项逻辑。
6. 运行时监控依赖执行器上的公开接口 `emit_visual`（内部统一委托 `_emit_visual`）：凡截图/OCR/模板匹配都要推送叠加层（节点区域、命中框、点击点等）供 UI 诊断。

## 注意事项
- 不新增 `try/except` 用来吞没异常；一切故障直接抛出，由 UI/调用者决定是否重试。
- 只能通过 `app.automation.capture` 获取截图、OCR、模板匹配与鼠标原语；禁止引用拆分前的 `editor_capture.py` 路径或工具脚本。
- `input.common` 提供 `ExecutionOptions`、`wait_until`、`sleep_seconds`、`ensure_foreground`、`log_start/log_ok/log_fail` 等统一入口；新增等待/日志时务必复用。
- `vision` 是识别唯一入口，且会记录所有标题映射/近似命中日志；如果识别失败优先检查 `vision.invalidate_cache()` 是否遗漏。
- 端口筛选、类型推断与 Warning 区域查找均有现成函数，严禁复制粘贴到执行器或 UI。
- 所有逻辑默认编辑器处于 50% 缩放、单实例前景窗口；修改拖拽/吸附策略时必须同步考虑多屏、高 DPI 与颜色吸附的容差。
- `_static_checks/` 中的规则需要与实现同步更新；新增跨层依赖前先扩充脚本。
- 跨模块访问执行器时，只能依赖协议方法：视口相关能力通过 `ViewportController` / `EditorExecutorWithViewport` 暴露，执行与节点查询通过 `EditorExecutorProtocol` 暴露；禁止在 UI 或 `config/`、`ports/` 等上层直接调用形如 `executor._ensure_*` 的私有方法。
- 步骤编排层避免直接读写执行器的 token/缓存内部字段，统一通过执行器公开的 view-state 方法判断是否需要“连线预热/可见节点同步”，减少隐式状态机耦合。
- Windows 控制台编码不可控，打印日志一律使用 `input.common.safe_print`。
- 与视口或坐标相关的调试与可视化入口（例如可见节点调试截图）依赖已建立的程序↔编辑器坐标映射；在仍处于未校准或快速映射失败的状态下，这类入口应及早短路并输出友好提示，而不是继续依赖未初始化的缩放比例与原点信息。

## 当前状态速览
- 目录按功能拆分为 `capture` / `input` / `vision` / `core` / `config` / `ports` / `runtime` 等子包，自动化入口统一通过 `app.automation` 暴露。
- `AutomationFacade` 作为轻薄门面，截图接口会根据是否传入区域自动选择全屏抓取或绝对区域抓取，其余高级功能需直接引用对应子包。
- 根包仅导出 `AutomationFacade` 及基础工具（如 `capture` 与 `input.common` 中的公共函数），不再提供诸如 `editor_capture` 一类的旧路径别名，调用方应统一通过 `app.automation.capture` 导入截图与输入原语。
- `RealExecutor` 默认实现 `EditorExecutorProtocol`，若需要自定义执行器，可在 `runtime/` 内按协议新增实现并在 UI 层注入。

---
本说明仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。

