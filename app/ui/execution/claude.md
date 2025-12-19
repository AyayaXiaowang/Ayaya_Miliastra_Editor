## 目录用途
- 聚合“真实执行节点图”的 UI 侧逻辑：执行计划、执行线程、监控面板与各类执行策略。
- 负责把 `TodoItem` 列表转换为真实编辑器中的键鼠操作序列，并在右侧监控面板中展示截图、日志与调试信息。

## 当前状态
- 顶层入口：
  - `runner.py`：封装执行入口与生命周期管理，对外提供“执行整图 / 仅此一步”等接口。
  - `planner.py`：根据图模型与选择的树节点生成待执行的 Todo 步骤序列。
  - `guides.py`：为部分步骤生成“只读指引”，不触发真实自动化。
- 执行线程与策略：
  - `thread.py`：在后台顺序执行步骤，负责整体流程编排（缩放确认 → 视口映射 → 逐步执行 → 回退重试），所有与自动化执行器的实际交互都集中在这里；当步骤执行失败且检测到 OCR 模板 profile 与当前显示设置不匹配时，会在监控日志输出一次性提示，引导用户调整分辨率/缩放到已提供的模板 profile。
  - `strategies/anchor_selector.py`：根据步骤列表选择一个合适的锚点节点，用于视口相关推断（优先创建类步骤的节点，其次连接、配置等）。
  - `strategies/execution_coordinator.py`：围绕 `EditorExecutor` 协调缩放检查与“识别+几何拟合”的快速视口映射，并在必要时提供额外的一步识别校验。
  - `strategies/step_skip_checker.py`：根据节点可见性与端点距离判断某些步骤是否可以安全跳过（例如目标节点已经存在、连线两端距离过远等）。
  - `strategies/retry_handler.py`：在步骤失败时尝试以最近成功锚点为基准回退视口并重试步骤。
  - `strategies/step_summary_builder.py`：为每一步构建人类可读的摘要文本，写入执行监控日志。
- 监控面板：
  - `monitor/` 子包包含执行监控面板本体与截图/日志/可视化等辅助模块，统一负责展示执行过程中的截图叠加、步骤日志与暂停/继续/终止控制。

## 注意事项
- 执行线程不负责节点图业务逻辑，只关心“如何按顺序调用 `EditorExecutor` 与策略对象”；任何与资源、存档或图编辑相关的逻辑都应放在上层控制器或模型层。
- 线程内部不使用 `try/except` 静默吞错，所有异常都应直接向上抛出，由外层统一记录或提示。
- 新增执行阶段时，应优先通过 `strategies/` 新建或扩展策略类，再在 `thread.py` 中以清晰的阶段顺序调用，避免在一个方法中混杂过多职责。
- 与自动化执行器的交互必须始终通过协议约定的接口（如 `ensure_zoom_ratio_50`、`verify_and_update_view_mapping_by_recognition`、`execute_step` 等），不要在 UI 层直接访问底层截图或输入实现。

# 执行子系统

## 目录用途

统一管理所有执行相关的模块，包括执行驱动器、执行线程、策略类、监控面板等；在执行节点图步骤时，为自动化执行器提供必要的上下文信息（如步骤序列与节点创建顺序），以便在创建节点时能够过滤“未来步骤中的节点”作为前置参考。

目录结构统一收拢在 `ui/execution/` 子包，将执行驱动器、执行线程、执行计划器、执行指引、策略类与监控面板集中管理。

## 当前状态

### 目录结构

```
ui/execution/
├── __init__.py             # 统一导出所有公共接口
├── claude.md               # 本文档
├── runner.py               # 执行驱动器（主入口）
├── thread.py               # 执行线程
├── planner.py              # 执行计划器
├── guides.py               # 执行指引
├── strategies/             # 策略类子模块
│   ├── __init__.py
│   ├── anchor_selector.py
│   ├── execution_coordinator.py
│   ├── retry_handler.py
│   ├── step_skip_checker.py
│   └── step_summary_builder.py
└── monitor/                # 执行监控面板子模块
    ├── __init__.py
    ├── panel.py
    ├── actions_recognition.py
    ├── execution_control.py
    ├── focus_controller.py
    ├── log_view.py
    ├── panel_app.ui.py
    ├── preview_dialog.py
    ├── screenshot_worker.py
    ├── visual_overlays.py
    └── visual_renderer.py
```

### 模块列表

#### 主要执行类

1. **runner.py** - 执行驱动器
   - `ExecutionRunner`: 负责驱动执行流程，管理线程生命周期
   - 发射信号：`finished`、`step_will_start`、`step_completed`、`step_skipped`
   - `start(..., fast_chain_mode=False)`: 支持由入口明确开启“快速链模式”，将参数透传给执行线程

2. **thread.py** - 执行线程
   - `ExecutionThread`: 在后台顺序执行节点图步骤
   - 职责：锚点选择、画布缩放检查、快速映射、锚点校准、逐步执行，并在初始化时基于当前步骤列表构建“节点首次创建步骤索引”映射（node_id → step_index），注入到执行器中，供自动化内核在创建节点时过滤掉尚未到达的“未来创建步骤”节点，避免这些节点参与前置参考或邻居偏移推断
   - **跨轮复用保护**：执行器实例会被监控面板复用；每轮执行开始会调用 `executor.reset_created_node_tracking()`（若存在）清空“已创建节点 tracking”，仅清除锚点选择用的创建顺序记录，不重置坐标映射，避免用户回退到更早步骤后误把未来步骤/同名节点当作锚点
   - 在 `_build_node_first_create_step_index()` 中会通过 `monitor.log` 记录每个“创建节点”步骤的 `step_index/todo_id/title/node_id`，便于在执行日志中直接定位某个 node_id 的“首次创建步骤”来源
   - 在 `_execute_steps_loop()` 中会在每步开始设置 `_current_step_index` 后输出当前 `step_index/todo_id/title/type/node_id` 的上下文日志，并在每步内部维护一次“单步可见节点映射”缓存，供零节点守卫与跳过检查复用，避免对同一帧画面重复构建可见节点映射；对于执行结果，约定创建类步骤在首轮执行与自动重试均失败时视为致命错误直接终止本轮执行，而连接/配置等非创建类步骤在多次尝试仍失败时会被标记为“跳过”并继续后续步骤
   - 当 `fast_chain_mode=True` 时，会临时打开 `executor.fast_chain_mode`，并在每步开始前注入步骤类型，仅对连接/参数步骤跳过缓冲等待；节点创建是否跳过完全由执行器内部的可见性判断负责，不再存在单独的“严格创建模式”切换
   - 启动阶段始终先尝试“快速映射”（识别+几何拟合）检查当前画面的节点分布；若快速映射失败且选出了有效锚点，再退化为使用锚点完成坐标校准与视口定位

3. **planner.py** - 执行计划器
   - `ExecutionPlanner`: 将任务清单转换为可执行步骤序列
   - `plan_steps(current_todo, todo_map)`: 静态方法，返回严格按顺序的执行步骤列表；当在模板图根下发现多个 `event_flow_root` 时，会按顺序串联所有事件流的子步骤，确保“执行整张节点图”覆盖整图而不是只跑第一个事件流

4. **guides.py** - 执行指引
   - `ExecutionGuides`: 提供执行相关的用户指引
   - `log_composite_guide(monitor_panel, detail_type, info)`: 静态方法，输出复合节点相关步骤的指引信息

#### 策略类（strategies/）

1. **anchor_selector.py** - 锚点选择器
   - `AnchorSelector`: 多层退化策略选择锚点节点
   - `AnchorInfo`: 锚点信息封装（标题、坐标、节点ID、跳过标记）
   - 策略：创建类步骤 → 连接步骤 → 合并连接 → 参数配置

2. **step_summary_builder.py** - 步骤汇总构建器
   - `StepSummaryBuilder`: 根据步骤信息生成可读摘要文本
   - 支持所有步骤类型：创建、连接、配置、动态端口等

3. **execution_coordinator.py** - 执行协调器
   - `ExecutionCoordinator`: 管理执行前的校准、快速映射和单步验证
   - `CalibrationResult`: 校准结果封装

4. **step_skip_checker.py** - 步骤跳过检查器
   - `StepSkipChecker`: 判断步骤是否需要跳过执行
   - `SkipDecision`: 跳过决策封装（是否跳过、原因）
   - 规则示例：
     - 单步执行模式下，仅真正执行目标步骤，其余步骤以“单步执行模式：仅执行当前选中步骤，其余步骤用于提供上下文但实际跳过”原因跳过
     - 单步模式下，若目标步骤是“创建节点”（`graph_create_node` / `graph_create_and_connect`）且通过识别确认该节点已在当前画面存在（按 GraphModel.node_id 匹配），则跳过该创建步骤并在执行监控中给出“目标节点已存在，跳过创建”的原因
     - 校准阶段若已创建/确认锚点节点，则跳过首个创建步骤以避免重复创建
     - 连接类步骤在执行前统一通过 `executor.will_connect_too_far` 做距离评估，过远则直接跳过并给出人类可读原因

5. **retry_handler.py** - 回退处理器
   - `RetryHandler`: 封装失败重试逻辑
   - `RetryResult`: 重试结果封装

#### 监控面板（monitor/）

详见 `monitor/claude.md`；监控面板内的“检查页面 / 定位镜头 / 拖拽测试”统一复用 `EditorExecutor` 的截图、识别与视口拖拽能力，用于观察与验证执行期间的真实画面与坐标映射，不引入独立的自动化执行路径。

### 导入示例

**推荐导入方式：**

```python
# 主要执行类
from app.ui.execution import ExecutionRunner, ExecutionPlanner, ExecutionThread

# 使用执行计划器
steps = ExecutionPlanner.plan_steps(current_todo, todo_map)

# 使用执行指引
ExecutionGuides.log_composite_guide(monitor_panel, detail_type, info)

# 策略类
from app.ui.execution.strategies import AnchorSelector, RetryHandler

# 监控面板
from app.ui.execution.monitor import ExecutionMonitorPanel
```

**兼容性导入（通过父包重新导出）：**

```python
# 直接从 app.ui.execution 导入策略类（通过 __init__.py 重新导出）
from app.ui.execution import AnchorSelector, ExecutionCoordinator

# 使用类静态方法，而不是函数别名
from app.ui.execution import ExecutionPlanner, ExecutionGuides
steps = ExecutionPlanner.plan_steps(current_todo, todo_map)
ExecutionGuides.log_composite_guide(monitor_panel, detail_type, info)
```

### 设计原则

- **单一职责**：每个策略类专注一个领域
- **依赖注入**：策略类通过构造函数接收依赖（executor、graph_model、monitor）
- **结果封装**：使用明确的结果类（AnchorInfo、SkipDecision、RetryResult）传递状态
- **状态隔离**：锚点记录、重试状态等封装在对应的策略对象内

## 注意事项

1. **导入路径**：旧代码中使用 `from app.ui.execution_runner import ...` 的需要更新为 `from app.ui.execution import ...`
2. **线程安全**：所有策略类均在同一后台线程中使用，无需考虑线程安全
3. **状态管理**：`RetryHandler` 维护最近成功锚点，`ExecutionCoordinator` 不维护状态
4. **错误处理**：遵循 UI 层约定，不使用 try/except，错误直接抛出或通过返回值传递
5. **扩展性**：如需新增执行策略（如智能跳过、自动恢复等），可新建独立策略类并在 `thread.py` 中组合使用
6. **类封装与向后兼容**：`ExecutionPlanner` 和 `ExecutionGuides` 使用静态方法封装功能，同时保留原函数名作为别名，确保旧代码继续工作

## 边界信息与微小细节

### 锚点选择的退化逻辑
- 多层退化确保即使清单中没有创建步骤，也能基于连接或配置步骤找到锚点
- 若所有策略都失败（返回无效 AnchorInfo），协调器会在校准阶段检测并终止

### 跳过检查的触发时机
- 跳过检查在每步 **执行前** 进行，而非在规划阶段
- 这允许动态判断（如节点距离、可见性）影响执行流程

### 重试的单次限制
- 失败后会按配置自动进行“回退重试”，最大次数由 `engine.configs.settings.REAL_EXEC_MAX_STEP_RETRY` 控制（默认 3，配置为 0/负数表示不自动重试）。
- **`step_completed` 仅表示某一步的最终结果**：重试过程中只输出日志，不重复发射 `step_completed`，避免监控统计与任务树选中产生错位。

### 快速映射与锚点校准的互斥
- 快速映射成功时会跳过锚点校准，这意味着 `RetryHandler` 的初始锚点为 `None`
- 若快速映射后某步失败，回退重试会因无锚点而直接终止（设计如此，因为快速映射已确保全局映射正确）

### 单步模式的特殊路径
- 单步模式（`len(steps)==1`）在未快速映射时会额外进行一次识别与几何校验
- 这确保单步执行的鲁棒性，即使在画面已偏移的情况下也能自动校正
