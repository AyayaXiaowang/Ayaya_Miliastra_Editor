# tests 目录

## 目录用途
存放最小可运行的单元测试与轻量级用例，用于在不依赖完整主窗口或真实资源库的前提下验证关键逻辑是否按预期工作。当前既覆盖 Todo 执行规划与当前步骤解析等纯逻辑能力，也包含对节点图、信号定义以及资源索引（如战斗预设与管理配置 JSON 扫描）的引擎层回归测试，便于在命令行下快速回归。

## 当前状态

- 分类约定（仅对新增测试逐步应用，不强制迁移历史文件）：
  - `tests/ui/`：UI 相关（含 PyQt6 最小构造/冒烟回归）
  - `tests/automation/`：automation 协议/契约类回归（尽量不依赖真实外设环境）
  - `tests/common/`：`app/common` 等轻量共享模块的契约/缓存一致性回归

- Todo 核心逻辑与执行规划：
  - `test_todo_core_logic.py`：围绕 `TodoItem`、`CurrentTodoContext` 以及若干纯逻辑服务（如 `resolve_current_todo_for_leaf`、`resolve_current_todo_for_root`、`plan_execute_from_this_step`、`plan_single_step_execution`、`resolve_graph_data_for_execution`、`plan_recognition_backfill` 等）构造最小用例，覆盖当前 Todo 决策顺序、模板图根 / 事件流根回溯、单步执行错误分支以及识别补写规划等核心行为。
    - 说明：`resolve_graph_data_for_execution` 测试侧通过 `GraphDataService`（`get_shared_graph_data_service(None, None)`）注入，避免测试依赖真实主窗口/资源管理器。
  - `test_todo_execution_service.py`：针对 `TodoExecutionService` 相关规划函数的更小粒度测试，只依赖 `TodoItem` 与 `CurrentTodoContext` 等纯数据结构，通过人为构造的父子关系与 `detail_type` 验证模板图根回溯、从中间步骤起执行（truncate 行为）、“从当前事件流起执行剩余事件流”规划，以及“非受支持步骤类型返回错误”等典型分支。
  - `test_todo_refresh_restore.py`：覆盖任务清单刷新后“恢复当前选中步骤”的优先级规则（selected_todo_id → current_todo_id → detail_info 全量匹配 → graph_id 兜底），用于保护主窗口刷新流程的回归。
  - `test_dynamic_port_steps_semantic_constant_filtering.py`：回归 `DynamicPortStepPlanner.collect_constant_params` 的过滤规则，确保任务清单的“配置参数”步骤不会暴露语义推导用的隐藏稳定 ID（`__signal_id/__struct_id` 及兼容旧键名），且不会把“信号名/结构体名”这类选择端口重复加入通用参数配置步骤。
- 节点图与信号相关样例：
  - `test_signal_template_graph.py`：使用 `GraphCodeParser` 解析模板图 `模板示例_信号全类型_发送与监听`，验证监听信号事件节点的绑定信息与参数端口覆盖情况，确保 IR 与模板代码保持一致。
  - `test_semantic_metadata_single_writer.py`：回归“语义元数据单一写入阶段”约束，验证 `GraphSemanticPass` 对 `signal_bindings/struct_bindings` 的覆盖式生成与幂等性，并用 AST 扫描守卫禁止 Parser/IR/UI 多源写入回归。
  - `test_signal_code_param_names.py`：通过最小 Graph Code 片段直接调用 `validate_files`，验证【发送信号】在代码层面使用的参数名必须存在于信号定义中，额外参数名会作为错误被报告，合法参数名不会报错，并校验 Graph Code 中【信号名】参数必须使用信号名称而非 ID。
  - `test_unknown_node_call_rule.py`：通过最小 Graph Code 片段直接调用 `validate_files`，验证形如 `未知函数(self.game, ...)` 的“疑似节点调用”会被识别并报告为错误，避免拼写错误或不存在节点名被静默跳过。
  - `test_event_handler_name_rule.py`：通过最小 Graph Code 片段直接调用 `validate_files`，验证内置事件回调必须命名为 `on_<事件名>`（禁止 `on_定时器触发时_XXX` 这类追加后缀写法），并确认信号事件不强制回调名。
  - `test_event_name_rule.py`：通过最小 Graph Code 片段直接调用 `validate_files`，验证事件名即使通过模块顶层字符串常量传入也必须可解析为内置事件或信号；未知事件名必须报错。
  - `test_on_method_name_rule.py`：通过最小 Graph Code 片段直接调用 `validate_files`，验证只要定义了 `def on_XXX`，`XXX` 就必须为内置事件名或已定义信号名/ID（即使没有注册也会报错），防止伪事件入口潜伏。
  - `test_pull_eval_reevaluation_hazard_rule.py`：构造“简单误用 + 复杂控制流误用（for/match/if）+ 不触发对照”三类 Graph Code，验证校验器会对“读-改-写自定义变量后仍复用同一【获取自定义变量】节点实例”的模式报告 `CODE_PULL_EVAL_REEVAL_AFTER_WRITE` warning，并避免对安全写法产生误报。
  - `test_graph_variable_rules.py`：构造临时 Graph Code 覆盖图变量声明缺失与 GRAPH_VARIABLES 中类型非法的分支，并额外验证 GRAPH_VARIABLES 默认值中包含负数字面量（如 `-1.0`）时元数据提取结果正确，确保代码级声明成为唯一的变量与类型校验来源。
  - `test_type_registry_alignment.py`：回归“类型体系单一事实来源”约束，确保变量类型清单、结构体字段允许类型、验证层与配置层的 datatype_rules、端口常量与别名字典解析等均与 `engine/type_registry.py` 对齐，防止新增/调整类型时出现跨模块漂移。
  - `test_local_variable_rules.py`：围绕局部变量相关校验规则构造最小 Graph Code 与复合节点示例，验证【获取局部变量→设置局部变量】模式下必须为“初始值”提供有效数据来源。
- 复合节点 pin_type 策略回归：`test_composite_pin_type_policy.py` 通过 `validate_files` 构造最小类格式与 payload 复合节点源码片段，验证“泛型/列表/泛型列表/泛型字典”只能作为编辑期占位，成品校验必须报错；并同时验证 Any/通用旧别名与 Python 内置类型名（int/float/str/bool/list/dict）同样会报错。
- 复合节点模板校验：`test_composite_multi_pins_template.py` 解析 `composite_多引脚模板_示例.py`，检查虚拟引脚类型/方向、分支流程出口映射和关键计算节点（加法、数值比较、列表长度/取值）均按设计生成。
- 复合节点文件发现一致性回归：`test_composite_file_discovery_policy.py` 回归“复合节点定义文件筛选规则单一事实来源”，确保 `engine.nodes.composite_file_policy`、复合节点管线 discovery、以及 `CompositeNodeManager` 加载集合一致，避免入口间漂移。
- 节点图核心逻辑：`test_graph_core_logic.py` 针对信号/结构体节点的端口规划与 NodeDef 代理构建进行纯模型验证，无需 PyQt。
- 数据节点分块逻辑：`test_data_node_placement.py` 使用 Mock 上下文测试 `DataNodeOwnershipResolver` 的归属判定逻辑，覆盖流程节点消费、数据节点消费、孤立节点归属、跨块边界跳过等场景，确保数据节点被分配到"首次实际消费它的块"。
- Todo UI 与任务树联动行为的最小验证：
  - `test_todo_tree_node_highlight.py`：在最小 `QTreeWidget` / `TodoTreeManager` 环境下验证节点预览点击联动时的高亮与置灰逻辑：直接调用 `highlight_steps_for_node` 以及通过任务清单预览面板的 `node_clicked` 信号，确认相关步骤集合解析正确，`_current_node_highlight_ids` 与 `_node_filter_active` 状态更新符合预期，并在树项上打上用于富文本委托的置灰标记，保证“从图到步骤”的反向联动在不启动完整主窗口的前提下即可被回归。
- 设置对话框与调试开关：`test_auto_layout_logging_setting.py` 覆盖两部分：其一，使用最小 `QApplication` 验证 SettingsDialog 将“图编辑器详细日志”开关写入 `settings.GRAPH_UI_VERBOSE`；其二，直接驱动 AutoLayoutController 在 verbose 开启且验证返回错误时会打印错误到 stdout，确保自动排版按钮的调试输出链路可被回归。
- UI/automation 冒烟级回归：
  - `ui/test_ui_library_pages_smoke.py`：复用 `tools.smoke_test_ui_libraries` 的同源逻辑，在 pytest 下构造资源库关键页面（元件库/实体摆放/节点图库/存档库）并完成一次 refresh/筛选，提供 UI 高频改动的最小回归保护。
  - `ui/test_window_close_save_policy.py`：回归“退出不强制全量保存”的保存策略，避免外部资源刷新后被静默覆盖。
  - `ui/test_save_conflict_policy.py`：回归保存冲突策略（expected_mtime + 覆盖开关），对齐 VSCode 等编辑器的“外部修改保护”。
  - `common/test_in_memory_graph_payload_cache_contract.py`：回归 `app.common.in_memory_graph_payload_cache` 的 cache_key 规则、detail_info 的 `graph_data/graph_data_key` 解析优先级，以及按图/按图根失效语义，避免任务清单预览/执行链路的缓存一致性回退。
  - `automation/test_executor_protocol_contract.py`：对 `EditorExecutorProtocol`/`ViewportController` 的关键方法做反射级签名一致性检查，并验证关键模块使用协议类型注解，避免跨模块回退到具体实现类导致耦合膨胀。
- 自动化截图 ROI 边界回归：`test_roi_config_bounds.py` 验证 `app.automation.capture.roi_config.get_region_rect` 对派生 ROI（如“节点图缩放区域”）返回的矩形始终在图像范围内，避免识别框越界与 OCR 空图问题。
- 资源索引命名策略回归：`test_resource_name_filename_sync_policy.py` 覆盖“扫描阶段是否允许将文件名回写到 JSON.name”的策略边界，确保默认缓存文件名策略下 UI 改名不会被索引扫描回滚；同时对“保存时以 name 驱动物理文件名”的类型保留同步能力。
- 块间排版（块与块之间）居中：`test_block_vertical_centering.py` 直接构造 `LayoutBlock` 与父子关系，验证 `BlockPositioningEngine` 在“多父合流 / 多子分叉”场景下能把目标块放在邻居块组的垂直中间，并避免因同列无约束大块而把应居中的块顶下去。
  - 同文件额外包含“分叉子块列内顺序只能做局部互换”的回归用例：确保按端口顺序调整分叉子块时不会把同列的非兄弟块整体挤走（防止整列重排导致结构被破坏）。
- 块内数据节点 Y 轴收敛：`test_block_internal_data_y_relaxation.py` 使用资源库节点图 `特效朝向_最后一次攻击者` 做解析/布局/校验回归，并构造最小“多父合流”用例验证 `DataYRelaxationEngine` 能把目标节点拉回父节点中心附近且保持确定性。
  - 同文件额外覆盖模板 `模板示例_踏板开关_信号广播` 的回归：定位（向量加法 + 获取节点图变量）输入到同一 `三维向量缩放` 的实例，断言被连节点 Y 落在两父节点 Y 区间内，防止块内多父场景出现“目标节点跑到父节点之上/之下”。
- Todo 详情与富文本 token 的结构化回归：
  - `test_todo_detail_viewmodel.py`：纯逻辑构造 `DetailDocument` 与任务树富文本 tokens，覆盖根/分类/模板/绑定信号等典型 detail_type 以及富文本 token 的颜色、背景与计数逻辑。
- 目录命名守卫：`test_no_core_subpackages.py` 扫描仓库目录树，确保不再出现名为 `core`（大小写不敏感）的子目录，防止“core 目录名”带来的长期认知噪音回归。
- tools 工具链冒烟：`test_tools_smoke.py` 以子进程方式执行关键 `tools.*` 入口（`check_impl_node_specs`、`lint_node_impls`、`check_duplicate_config_names`、`clear_caches --rebuild-index`），确保在当前仓库结构下“可模块执行且不崩”，为后续接入 CI 提供基线保护。
- 全仓语法可编译守卫：`test_python_syntax_compilable.py` 递归扫描仓库内所有 `.py` 文件并执行纯 `compile` 语法编译检查，避免“未被 import 的文件”潜伏 SyntaxError（尤其是高版本语法在 CI=3.10 下不兼容）绕过常规用例。
- NodeRegistry 加载护栏：`test_node_registry_load_guards.py` 覆盖“同线程递归加载必须显式报错、跨线程并发访问必须等待加载完成（不能返回空库）”，用于避免节点库出现隐式半成品状态。
- 复合节点管理器反向依赖护栏：`test_composite_manager_no_registry_backedge.py` 回归“CompositeNodeManager 工厂不得隐式调用 NodeRegistry / CompositeNodeLoader 解析子图必须显式注入 base_node_library”，避免循环依赖与缓存不一致引发的节点缺失。
- UI 缓存分叉护栏：`test_no_ui_direct_in_memory_graph_payload_cache_import.py` 扫描 `app/ui` 的 import 语句（覆盖 `import app.common.in_memory_graph_payload_cache` / `from app.common import in_memory_graph_payload_cache` / `from app.common.in_memory_graph_payload_cache import ...`），并进一步要求 `app/` 内仅允许 `GraphDataService` 作为唯一桥接入口，避免未来新增“绕过门面”的失效入口。
- 导入路径守门：`test_import_path_single_source_of_truth.py` 与 `test_codegen_sys_path_bootstrap.py` 确保测试环境与生成代码不会把 `<repo>/app` 注入 `sys.path`，从机制上避免 `ui.*` 与 `app.ui.*` 双导入导致的“同名类不是同一个类”。

## 注意事项

- 当前大多数测试仍为纯逻辑测试，不创建 `QApplication` 实例；个别测试会通过 `GraphCodeParser` 和信号 Schema 视图访问节点库与信号定义代码资源，但不会修改实际资源文件，可在命令行通过 `pytest tests` 或 `python -m pytest tests` 运行。
- 展示型发布策略：测试应避免依赖任何“未随仓库分发”的私有资源库内容；需要资源时优先：
  - 使用已公开的 `assets/资源库/**/模板示例_*` / `示例_*` 文件；或
  - 在 `tmp_path` 下构造最小资源目录与样例文件（例如 JSON 资源索引扫描类测试）。
  - 对“信号名称可解析”的规则测试，应使用仓库内已跟踪的示例/测试信号（例如 `测试信号_全部参数类型`），避免引用本地私有信号导致 CI 环境缺失。
- 如后续新增需要 UI 的测试（例如针对具体 QWidget 的交互），应在对应测试文件中显式创建和销毁 `QApplication`，并在导入任何 PyQt6 / UI 模块前完成 RapidOCR / onnxruntime 的初始化以避免 DLL 冲突。
- 导入规范：逻辑相关功能优先从 `app.models`、`app.ui.todo` 等应用层模块或 `engine` 公共 API 导入，避免在测试中直接依赖内部实现细节；如需节点定义或资源视图，应通过引擎提供的注册表与资源管理器构造最小上下文，而不是在测试中自行加载整套资源库。

## Pytest 启动配置

- `conftest.py` 仅将项目根目录加入 `sys.path`，确保可稳定导入 `app.*` / `engine.*`。
- **不要将 `<repo>/app` 加入 `sys.path`**：否则会导致 `ui.*` 与 `app.ui.*` 并存、同名类被加载两份而出现 `isinstance` 异常；因此测试代码应统一使用 `app.ui.*` 导入路径，而不是 `ui.*`。
- `conftest.py` 会调用 `settings.set_config_path(PROJECT_ROOT)` 并 `settings.load()`，为依赖 workspace_root 的引擎模块（如布局/节点库）提供单一真源，避免测试环境出现隐式路径回退导致的不稳定行为。

---
注意：本文件不记录任何修改历史，仅描述 tests 目录的用途、当前状态与使用注意事项。


