# App/Models

## 目录用途
为应用层提供与"界面流程"相关的数据与配置抽象（如任务生成、包校验、视图模式）。不包含任何图形控件或 PyQt 依赖，可在非 GUI 环境运行。

## 分层定位（与 ui/ 的边界）
- 本目录属于"应用层模型抽象"，只包含协议/数据结构/算法与模式配置。
- 应用层界面位于 `app/ui/`，按需依赖本目录暴露的抽象。
- 依赖方向必须是单向：`app/ui -> app/models`；严禁 `app/models -> app/ui`，并禁止引入 `PyQt6/*`。

## 关键文件
- `todo_item.py`：任务项数据结构（树形层次、完成度/进度计算等）
- `todo_detail_info_accessors.py`：Todo `detail_info` 字段访问器（`get_detail_type/get_graph_id/get_node_id/require_field`）。UI/模型统一通过该文件读取关键信息，避免散落 `detail_info.get(...)`；其中 `require_field` 用于强约束必填字段，缺失/空值直接抛错以暴露数据问题。
- `todo_detail_info_schema.py`：**detail_info schema 单一真源与运行时校验器**（`get_detail_info_schema/validate_detail_info`），声明每种 detail_type 的必填字段与类型约束；覆盖节点图动态端口新增步骤（`graph_add_variadic_inputs/graph_add_dict_pairs/graph_add_branch_outputs`）等；`TodoGenerator` 在生成阶段以 strict 模式校验 detail_info，新加/改动 detail_type 必须同步补齐 schema。
- `todo_generator.py`：单一 orchestrator，借助内部 builder 细分模板/实例/资源/独立图任务的构建，统一排序与复用；节点图展开提供 `expand_graph_tasks()` 静态入口以满足 UI 懒加载，并支持可选注入 `PackageIndexManager` 以复用索引与缓存；懒加载展开支持可选 `progress_callback(stage, completed, total)` 回调，用于 UI 侧驱动“百分比进度条”；节点图任务生成统一通过 `GraphTaskCoordinator` 调用 `TodoGraphTaskGenerator`；模板“自定义变量”不再作为独立任务段落生成（变量定义已迁移为关卡变量代码资源）；实例属性表中的变量覆写以 `{variable_id, variable_name, variable_type, value}` 结构输出；在描述“为模板添加组件”的任务时，组件名称与说明统一来自 `engine.configs.components.component_registry` 暴露的注册表，避免在模型层重复维护组件文案；`_add_todo` 以 `todo_id` 去重并原地更新既有对象，保证 UI 构树引用稳定，避免重复树项与“幽灵步骤”。
- `resource_task_configs.py`：声明战斗/管理资源→任务的配置映射，统一字段/引导/描述，供 `todo_generator.py` 直接消费
- `package_loader.py`：封装 `ResourceManager`/`PackageIndexManager` 交互（图名解析、候选图检索、预览上下文），屏蔽具体实现细节；优先使用调用方注入的 `PackageIndexManager` 单例，避免在模型层重复 new 导致索引/清单状态分叉。
- `todo_graph_task_generator.py`：节点图任务生成器（human/ai 两种模式）；仅做 orchestrator，将复合节点、事件流、边索引分别交给 `todo_graph_tasks/`；提供 `create_graph_root_todo` 供懒加载/即时展开共享结构；图数据通过 `GraphDataService` 写入进程内 payload cache 并在 detail_info 中仅保存 `graph_data_key`（不再把整张图塞进 detail_info），并在图根下统一生成“信号概览”等与信号系统相关的任务；支持可选注入 `progress_callback(stage, completed, total)`，在“解析模型/生成复合节点指引/生成事件流”等阶段持续汇报进度，用于 UI 超大图展开时的 0–100% 百分比进度条（异常不吞没，仍会抛出）。
- `todo_builder_helpers.py`：TodoItem 构建辅助函数（提供节点图任务步骤的标准化构建器，解耦任务生成逻辑；部分图步骤会在 detail_info 中附带 `node_category`，供 UI 在不加载 GraphModel 的情况下也能用“节点类别色”渲染任务树；动态端口新增步骤依赖 `NodeTypeHelper.describe_dynamic_port_behavior()` 返回的行为判定，按模式选择变参/键值/流程分支的子步骤）
- `todo_node_type_helper.py`：节点类型推断辅助（判断节点是否包含泛型端口，分别枚举需要设置类型的输入/输出端口；NodeDef 定位统一以 `NodeModel.node_def_ref` 为唯一真源，禁止通过 `title` 猜；workspace_root 推断优先使用 `settings.set_config_path(...)` 注入的单一真源，必要时回退到 `engine.utils.workspace` 的统一推断；按工作区路径复用节点库缓存并跟踪 `node_library.json` 签名以自动失效；在枚举端口时以 GraphModel 中实际存在的端口名为准，会将 `0~99`、`键0~49` 等范围占位通过类型规则展开为 `0`/`1`/`键0`/`键1` 等具体端口名；`describe_dynamic_port_behavior()` 提供统一的动态端口分类结果，供任务生成器/预览流程共用，并对信号语义节点（`semantic_id=signal.*`）跳过“新增动态端口”推断）。
- `todo_block_index_helper.py`：为节点图 Todo 步骤提供 BasicBlock 块索引与块归属判定逻辑，抽象出 `node_id -> block_index` 与 Todo→块索引的纯模型工具，供任务生成与 UI 层按相同规则分块展示与排序。
- 项目存档校验不在本目录提供入口；请统一使用 `engine.validate.ComprehensiveValidator`（CLI 入口：`app.cli.graph_tools validate-project`；`validate-package` 仅作为兼容旧名保留；UI 也复用引擎侧校验结构）。
- `view_modes.py`：主窗口视图模式与右侧标签配置（集中化，消除硬编码；字符串标识与枚举名称保持一致，`_VIEW_MODE_TO_STRING`/`_STRING_TO_VIEW_MODE` 负责双向映射，并覆盖所有枚举值含 PACKAGES 模式；`_INDEX_TO_VIEW_MODE` 提供常量时间的索引→枚举查找；`RIGHT_PANEL_TABS` 声明确认各模式的基础标签集合，例如节点图库下挂载“图属性 + 信号/结构体/变量”两个只读标签、图编辑器下挂载“图属性”标签，复合节点模式下挂载“复合节点属性/虚拟引脚”标签，验证模式下挂载“验证问题详情”标签；“执行监控”标签只作为可选值，实际是否插入由 UI 根据当前选中的 Todo 类型按需控制；战斗预设模式下的“玩家模板 / 职业 / 技能”详情标签不通过该映射固定挂载，而是由 UI 根据当前选中对象调用 `_ensure_player_editor_tab_visible/_ensure_player_class_editor_tab_visible/_ensure_skill_editor_tab_visible` 动态插入或移除，避免在仅选中玩家模板时仍显示空的“职业/技能”页签）
- `todo_structure_helpers.py`：Todo 树结构的共用操作（如安全追加子节点），供任务生成/遍历流程复用
- `todo_graph_tasks/`：节点图子任务拆分实现所在子目录，包含事件流遍历、边索引以及动态端口/参数与类型步骤的规划逻辑，仅依赖 `engine.graph` 与 `app.models` 内部工具，不直接持久化资源或访问 UI；内部 `EventFlowEmitters`/`DynamicPortStepPlanner` 负责将信号节点的“绑定信号/配置参数”拆分为结构化 Todo（信号节点不再生成“设置类型”步骤，其端口类型完全由信号定义决定），其中绑定信号步骤会附带当前图中该节点所用信号的参数名列表，便于任务清单与执行摘要中展示“参数数量”与参数名提示；类型步骤仅围绕声明为“泛型/泛型列表/泛型字典”等的端口生成指引，显式跳过已具备具体类型声明的输入/输出端口，避免在任务清单中出现多余的类型设置说明；输入侧的类型步骤会严格以 Todo 中的参数列表为准决定要处理的端口集合，而输出侧在存在泛型输出端口时会自动补齐对应的类型明细，以便在没有常量示例值时仍然能够为输出端口给出清晰的类型提示。
- `ui_navigation.py`：UI 级导航请求模型，定义 `UiNavigationRequest` 数据结构与若干工厂方法，用于在不依赖 PyQt 的前提下集中表达“从资源 ID 到目标视图模式及聚焦位置”的导航意图；工厂方法覆盖验证问题（含图/复合节点/管理配置等多种 detail 类型）、图库/项目存档页“跳到实体属性面板”、Todo 跳转与 Todo 预览跳转等常见场景，避免 UI 层分散手写 `resource_kind/desired_focus` 组合；`NavigationCoordinator` 在 UI 层消费该模型，将各来源统一映射到 ViewMode 切换与具体选中/定位行为。
- `edit_session_capabilities.py`：编辑会话能力模型 `EditSessionCapabilities`（`can_interact/can_persist/can_validate`）。用于将“只读/可交互/可保存/可校验”的语义收敛为单一真源，供 UI 各层统一注入与消费，避免 controller/view/scene 各自维护独立 bool 开关导致语义漂移。

示例导入：
```python
from app.models import TodoItem, TodoGenerator
from app.models.view_modes import ViewMode, VIEW_MODE_CONFIG, RIGHT_PANEL_TABS
```

## 面向开发者的要点
- 仅依赖 engine 核心模块；禁止图形依赖。
- 产物面向 UI 展示（结构化、可分页/分级），但不直接耦合 UI 组件。
- 节点图任务生成支持三种步骤模式：人类模式（连线并创建）；AI-先配置后连线（按块批处理：创建→（动态端口）→类型→参数，最后统一连线）；AI-逐个节点模式（逐节点：创建→（动态端口）→类型→参数，最后统一连线）。
- 事件流遍历依赖 `deque` 队列，禁止手写 `list.pop(0)` 以免在大图中退化为 O(n²)。
- UI 懒加载节点图时复用 `TodoGenerator.expand_graph_tasks(..., graph_root=existing_root, attach_graph_root=False)`，即可仅生成子步骤并更新根任务 `detail_info`，避免重复写入 `TodoGenerator.todos`。
- 图任务 Detail 统一包含 `task_type`，生成的所有子 Todo（含动态端口/连接）沿用该类型，保证统计/过滤一致。

## 异常处理约定
- 本目录不使用 `try/except` 吞没错误；生成/校验中的异常直接抛出，由调用者决定处理方式，避免隐性回退。

---

注意：本文件不记录任何修改历史。请始终保持对"目录用途、当前状态、注意事项"的实时描述。
