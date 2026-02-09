## 目录用途
存放“仓库护栏/基础契约”相关测试：覆盖导入路径单一真源、代码生成 bootstrap 约束、节点库加载护栏与全仓语法可编译性，防止结构/约束回退造成长期隐患。

## 当前状态
- `test_import_path_single_source_of_truth.py`：导入路径守门：确保 `<repo>/app` 不在 `sys.path`，且 `app/ui` 不会被当成顶层 `ui.*` 导入，避免 `ui.*` 与 `app.ui.*` 双导入。
- `test_codegen_sys_path_bootstrap.py`：回归代码生成 bootstrap：生成代码仅注入 `PROJECT_ROOT`，不得注入 `APP_DIR`。
- `test_no_core_subpackages.py`：目录命名护栏：全仓禁止出现名为 `core`（大小写不敏感）的子目录。
  - 允许跳过发布产物目录（如 `release/`）内的第三方依赖（例如 PyInstaller onedir 内置的 `numpy/core`）。
- `test_python_syntax_compilable.py`：全仓 `.py` 文件 `compile` 级语法检查（不执行代码），避免潜伏 SyntaxError 绕过常规 import 路径。
- `test_node_registry_load_guards.py`：NodeRegistry 加载护栏：同线程递归加载必须显式报错、跨线程并发访问必须等待加载完成。
- `test_type_registry_alignment.py`：回归类型体系单一事实来源：类型清单/别名/验证层与配置层规则需与 `engine/type_registry.py` 对齐。
- `test_no_ui_direct_in_memory_graph_payload_cache_import.py`：UI 缓存分叉护栏：`app/ui` 禁止直接 import `app.common.in_memory_graph_payload_cache`，app 层也仅允许 GraphDataService 桥接入口；路径展示统一使用 `engine.utils.path_utils.normalize_slash` 保持输出稳定。
- `test_node_stub_pyi_up_to_date.py`：节点函数 `.pyi` 类型桩护栏：确保 `plugins/nodes/{server,client}/__init__.pyi` 与 `engine.nodes.stubgen.generate_nodes_pyi_stub(...)` 输出严格一致，避免节点端口签名/补全提示与节点库漂移。
- `test_gia_export_enum_mapping.py`：私有扩展 `.gia` 导出契约回归：枚举中文选项必须可稳定映射到 enum item id，且导出模块可被导入（避免 NameError/循环依赖）。
- `test_gia_export_composite_pin_index.py`：私有扩展 `.gia` 复合节点导出契约回归：调用复合节点（kind=22001）时 pins 必须写 `compositePinIndex(field_7)`，并与 CompositeDef 的 `pinIndex(field_8)` 对齐，避免端口错位。
- `test_project_export_gia_signal_collection.py`：项目存档导出节点图 `.gia` 的信号收集护栏：必须同时覆盖 `发送信号/监听信号`（信号名为字符串常量），避免漏打包信号 node_def 依赖导致导入后信号参数端口无法展开并断线。
- `test_gia_export_multibranch_cases_outflows.py`：私有扩展 `.gia` 多分支导出契约回归：`Multiple_Branches(type_id=3)` 必须写入 `cases` 列表（InParam index=1），并严格限制 `OUT_FLOW` 数量为 `1 + len(cases)`（避免 NodeEditorPack 画像补齐出“最大分支数”导致端口漂移/错连）。

## 注意事项
- 护栏类测试应尽量避免污染仓库工作区；需要写入时使用 `tmp_path` 工作区。


