# tests/tooling

## 目录用途

存放“仓库护栏/基础契约”相关测试：覆盖导入路径单一真源、代码生成 bootstrap 约束、节点库加载护栏与全仓语法可编译性，防止结构/约束回退造成长期隐患。

## 当前状态

- `test_import_path_single_source_of_truth.py`：导入路径守门：确保 `<repo>/app` 不在 `sys.path`，且 `app/ui` 不会被当成顶层 `ui.*` 导入，避免 `ui.*` 与 `app.ui.*` 双导入。
- `test_codegen_sys_path_bootstrap.py`：回归代码生成 bootstrap：生成代码仅注入 `PROJECT_ROOT`，不得注入 `APP_DIR`。
- `test_no_core_subpackages.py`：目录命名护栏：全仓禁止出现名为 `core`（大小写不敏感）的子目录。
  - 允许跳过发布产物目录内的第三方依赖（例如 PyInstaller onedir 内置的 `numpy/core`）。
- `test_python_syntax_compilable.py`：全仓 `.py` 文件 `compile` 级语法检查（不执行代码），避免潜伏 SyntaxError 绕过常规 import 路径。
- `test_validate_graphs_all_includes_port_type_regression_samples.py`：`validate-graphs --all` 的 targets 收集范围回归：必须包含 `assets/资源库/项目存档/测试项目/.../回归/端口类型/` 下的最小回归样本目录，且这些样本单文件校验可通过（避免依赖默认不对外的业务存档目录）。
- `test_port_type_title_fallback_scan_command_logic.py`：离线迁移诊断入口回归：确保 `private_extensions.ugc_file_tools` 可 alias 到顶层 `ugc_file_tools`，并验证 `scan-title-fallback` 的核心判定逻辑（仅 title 可解析时标记为 title_fallback_hit）。
- `test_port_type_event_migration_scan_command_logic.py`：离线迁移诊断入口回归：验证 `scan-event-migration` 的核心判定逻辑（event 节点按 `category/title -> builtin_key` 划分为可迁移、缺字段、或映射 key 未命中）。
- `test_node_registry_load_guards.py`：NodeRegistry 加载护栏：同线程递归加载必须显式报错、跨线程并发访问必须等待加载完成。
- `test_type_registry_alignment.py`：回归类型体系单一事实来源：类型清单/别名/验证层与配置层规则需与 `engine/type_registry.py` 对齐。
- `test_no_ui_direct_in_memory_graph_payload_cache_import.py`：UI 缓存分叉护栏：`app/ui` 禁止直接 import `app.common.in_memory_graph_payload_cache`，app 层也仅允许 GraphDataService 桥接入口；路径展示统一使用 `engine.utils.path_utils.normalize_slash` 保持输出稳定。
- `test_node_stub_pyi_up_to_date.py`：节点函数 `.pyi` 类型桩护栏：确保 `plugins/nodes/{server,client}/__init__.pyi` 与 `engine.nodes.stubgen.generate_nodes_pyi_stub(...)` 输出严格一致，避免节点端口签名/补全提示与节点库漂移。
- `test_writeback_ui_guid_registry_autoload.py`：写回遗留入口的 UI registry 自动加载回归：当 graph_model.json 位于 out/ 目录时，仍应能从 JSON 元信息推断 workspace/package 并加载“运行时缓存 registry”（用于占位符解析/诊断；主写回流程以 base `.gil` UI records 为真源）。
- `test_project_writeback_ui_before_graphs.py`：写回管线顺序护栏：当同时启用 UI + 节点图写回时，必须先写 UI 再写节点图（graphs 的 input 必须来自 UI 写回后的 current_input）；并兼容 UI Workbench bundle 写回新增的 `layout_conflict_resolutions` 参数（用于冲突策略透传）。
  - 该用例不依赖真实 `.gil` bytes：会 stub 掉“base `.gil` payload 读取 + 基础设施缺口探测”，只锁住 pipeline 的编排顺序与 input 传递契约。
- `test_gia_export_enum_mapping.py`：扩展（`ugc_file_tools`）`.gia` 导出契约回归：枚举中文选项必须可稳定映射到 enum item id，且导出模块可被导入（避免 NameError/循环依赖）。
- `test_gia_export_composite_pin_index.py`：扩展（`ugc_file_tools`）`.gia` 复合节点导出契约回归：调用复合节点（kind=22001）时 pins 必须写 `compositePinIndex(field_7)`，并与 CompositeDef 的 `pinIndex(field_8)` 对齐，避免端口错位。
- `test_project_export_gia_signal_collection.py`：项目存档导出节点图 `.gia` 的信号收集护栏：必须同时覆盖 `发送信号/监听信号`（信号名为字符串常量），避免漏打包信号 node_def 依赖导致导入后信号参数端口无法展开并断线。
- `test_gia_export_multibranch_cases_outflows.py`：扩展（`ugc_file_tools`）`.gia` 多分支导出契约回归：`Multiple_Branches(type_id=3)` 必须写入 `cases` 列表（InParam index=1），并严格限制 `OUT_FLOW` 数量为 `1 + len(cases)`（避免 NodeEditorPack 画像补齐出“最大分支数”导致端口漂移/错连）。
- `test_gia_export_asset_bundle_golden_snapshot.py`：扩展（`ugc_file_tools`）`.gia` 导出金样快照：以固定 GraphModel(JSON) 作为输入，对导出的 AssetBundle message（结构）做快照对比，并对 `export_tag` 的时间戳做归一化以保证可回归。
  - 节点类型映射构建统一复用 `ugc_file_tools.node_graph_semantics.type_id_map`（单一真源），避免测试侧依赖写回实现域。
- `test_gil_writeback_sync_with_gia_rules.py`：`.gil` 写回与 `.gia` 关键口径对齐回归（含 `发送信号/监听信号/向服务器节点图发送信号` 的 signal meta binding、kernel index、runtime concrete 对齐）。
  - `.gil` 静态发送信号绑定保持 generic runtime（不照搬 `.gia` runtime 提升），避免空存档导入兼容性问题。
  - 当写回侧命中 signal-specific type_id 时，节点实例 type_id 直接使用 base 信号表里的 id（常见 0x4000xxxx/0x4080xxxx，对齐 after_game），不再额外 OR 到 0x6000xxxx/0x6080xxxx。
  - generic 信号节点会清理模板遗留 flow `field_7`，防止信号参数端口显示错位。
  - 信号 META binding 不依赖 `__signal_id`：仅要“信号名字符串常量 + 无 data 入边”即可启用（回归用例覆盖）。
  - `以键查询字典值(Query_Dictionary_Value_by_Key, 1158)`：按字典 K/V 命中 concrete_id，并写出输出端口 `值` 的 `indexOfConcrete`（来自 TypeMappings），避免泛型输出回退为默认“实体”。
- `test_gil_writeback_pipeline_signal_specific_type_id_opt_in_plumbing.py`：写回管线策略护栏：pipeline 必须显式暴露 `prefer_signal_specific_type_id` 开关且不得在内部调用点写死 False（避免策略无法切换）。
- `test_gil_writeback_dict_port_type_alignment.py`：端口类型对齐回归：
  - 字典 K/V：当 `键/值` 在 GraphModel 中仍为“泛型”时，`constants_writeback` 与 `edges_writeback` 都必须跟随 “字典” 端口推断到的 (K,V) 收敛 VarType，避免被 `"123"` 这类字面值兜底推断覆盖导致与 GIA 口径不一致。
  - data-link：`edges_writeback` 写连线时必须忽略 `input_constants` 的字面值，避免“已连线端口”被常量兜底推断写错类型。
  - 兼容 GraphModel 仅携带 `input_types/output_types` 快照或上游缺失 `output_port_types` 的形态：仍应能反推字典别名并稳定收敛键/值类型。
- `test_gil_writeback_local_var_and_dict_type_inference_regressions.py`：写回推断回归（局部变量/字典）：
  - 【获取局部变量】`初始值` 为纯数字字符串时，GUID 空占位补丁必须 **按类型证据触发**（不应无条件把常量写成 GUID）。
  - 【对字典设置或新增键值对(948)】当上游为【获取节点图变量】且其输出端口类型缺失/仍为泛型时，必须能从 `graph_variables(name→type)` 反推出别名字典类型，写出 concrete runtime_id，并写出 dict OUT_PARAM(MapBase KV) 以避免编辑器回退为默认字典。
  - 【获取自定义变量】当输出被实例化为别名字典时：
    - OUT_PARAM 必须写出 MapBase(K,V)（即便 out_port 名为“变量值”），避免回退为默认类型；
    - 若该节点满足 `TypeMappings: S<T:D<K,V>>`（单泛型 T=字典），还必须按 TypeMappings 写入节点 concrete runtime_id 与 OUT_PARAM 的 `indexOfConcrete`（常见为 20），否则编辑器可能回退为整数。
- `test_gil_writeback_snapshot_fields_fallbacks.py`：快照字段兼容回归：
  - OUT_PARAM：当仅存在 `output_types`（缺失 `output_port_types`）时，泛型输出端口仍应写出正确 var_type。
  - 动态端口：`拼装列表` 在缺失 `output_port_types` 时仍应能从 `output_types` 识别列表别名，并把元素 pins 写成正确 VarType。
- `test_contract_node_graph_type_mappings.py`：口径契约层单测：node_data TypeMappings 的 token/文本解析与 concrete/indexOfConcrete 映射解析应保持稳定（覆盖 `S<T:D<K,V>>` 与 `S<T:...>` 的 in/out indexOfConcrete；供 `.gia` 导出与 `.gil` 写回共同复用）。
- `test_gil_writeback_dict_outparam_requires_kv_failfast.py`：fail-closed 合约回归：当 declared 为“泛型字典”但端口有效类型仍停留在“字典/泛型字典”（无法解析 K/V）时，写回侧必须直接报错，禁止静默回退导致编辑器显示错误字典类型。
- `test_vector3_none_constant_writeback.py`：Vector3 常量允许 `None` 的回归：`raw_value=None` 必须被编码为“未设置”(VectorBaseValue empty bytes)，避免写回节点图阶段因强制转换报错。
- `test_gil_writeback_assembly_dict_concrete_id.py`：拼装字典写回 concrete 选择回归：
  - 当键端口常量为 `ui_key:`（数值语义）时，`.gil` 写回需按 `K/V` 映射选中实例化 concrete（例如 `Int-Int -> 1830`），不回退 generic(1788)。
  - 当 `键0/值0` 缺少可证据类型（无显式类型/无常量/无入边反推）时，写回应保留模板已有 concrete，避免无证据重推导致实例化漂移。
- `test_ui_state_group_missing_show_optional_writeback_policy.py`：节点图写回 UIKey 预检契约：缺失 UIKey 默认不再阻断写回，缺失项回填为 0（包含 `UI_STATE_GROUP__*__*__group` 与普通 UIKey）。
- `test_gia_export_ui_state_group_missing_optional_policy.py`：节点图 `.gia` 导出 UIKey 回填契约：`UI_STATE_GROUP__*__*__group` 缺失默认放行并回填为 0；但非状态组 UIKey 仍保持缺失即报错（除非显式开启 allow_unresolved）。
- `test_writeback_id_ref_placeholders_missing_optional_policy.py`：节点图写回占位符契约：`entity_key:` / `component_key:` 在缺失映射时允许继续写回并回填为 0（不阻断流程）。

## 注意事项

- 护栏类测试应尽量避免污染仓库工作区；需要写入时使用 `tmp_path` 工作区。
