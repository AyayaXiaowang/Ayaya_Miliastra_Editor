## 目录用途
存放“节点图解析/语义阶段/管线推导”相关测试：覆盖 GraphCodeParser 的解析稳定性、语义元数据写入阶段约束、同进程多次解析的状态隔离，以及节点管线 scope 推导等核心行为。

## 当前状态
- `test_realtime_reparse_state_isolation.py`：回归同进程内连续解析多个 Graph Code 文件时解析器状态必须隔离，避免跨次解析泄漏导致建模错误。
- `test_semantic_metadata_single_writer.py`：回归语义元数据（`signal_bindings/struct_bindings`）只允许在语义 Pass 单一阶段生成，并用 AST 扫描守卫禁止多源写入回归。
- `test_signal_template_graph.py`：解析公开模板 `模板示例_信号全类型_发送与监听`，验证监听信号事件节点的绑定信息与输出端口覆盖情况。
- `test_loop_local_variable_modeling.py`：解析公开测试图 `测试_局部变量计数`，验证循环体内变量更新能被正确建模为【获取/设置局部变量】写回。
- `test_branch_local_variable_modeling.py`：解析公开测试图 `测试_局部变量_分支设置`，验证 if-else 分支合流变量赋值能被正确建模为【获取局部变量】初始化 + 两侧分支【设置局部变量】写回。
- `test_nested_controlflow_parsing.py`：回归复杂嵌套控制流（for 内 match/break、match 分支仅含纯数据节点、for 内 if-else 写回）在解析时的流程边与局部变量建模稳定性。
- `test_composite_match_controlflow_parsing.py`：回归 match over 复合节点流程出口在循环 break、纯数据分支接续、return 分支终止等场景下的流程连线与局部变量合流建模。
  - 注意：该类测试依赖“演示项目”作用域下的复合节点定义（例如 `多分支_示例_类格式`），运行前需切换 `active_package_id="演示项目"` 并清理 NodeRegistry 缓存，避免复合节点未加载导致解析退化为普通 match。
- `test_strict_parse_fail_closed.py`：回归严格模式（fail-closed）：遇到 Python 原生方法调用、复合 match 无有效分支等无法可靠建模的写法时，应直接拒绝解析（抛错），避免静默产错图。
  - 同时回归 validate 入口：`validate_file` 必须将 IR 层收集到的 `ir_errors` 作为 error 暴露，避免“UI 严格模式拒绝加载但校验通过”。
  - 校验用例中若使用【设置/获取节点图变量】，需同步在代码级 `GRAPH_VARIABLES` 中声明对应变量，避免被“图变量声明规则”提前拦截而掩盖 IR 相关错误。
- `test_graph_core_logic.py`：节点图核心纯模型回归（端口规划与 NodeDef 代理构建等），不依赖 PyQt。
- `test_node_pipeline_scope_inference.py`：回归节点管线 scope 推导规则。
- `test_node_pipeline_alias_scope_resolution.py`：回归节点管线 alias 的作用域解析规则。
- `test_scope_aware_node_name_index_from_library.py`：回归 scope-aware 节点名索引必须指向当前作用域可用的 NodeDef，并覆盖关键节点（角度/弧度转换、设置局部变量、基础算术）端口命名契约，避免 UI 连线缺失。
- `test_reverse_generate_graph_code_roundtrip.py`：回归“反向生成 Graph Code（阶段1线性事件流）”的往返语义一致：从公开模板图解析出 GraphModel，再生成 Graph Code 并正向解析，最终用语义签名比较确保节点/连线/变量/关键元数据一致。
- `test_reverse_generate_graph_code_roundtrip_controlflow.py`：回归“反向生成 Graph Code（结构化控制流）”：覆盖双分支/多分支/循环/break，以及复合节点多流程出口（match）与默认出口线性接续等场景的往返语义一致。

## 注意事项
- 解析类测试应尽量使用仓库内跟踪的模板/示例文件作为输入，避免引用本地私有资源。
- 模板/测试节点图位于 `assets/资源库/项目存档/<package_id>/节点图/<server|client>/...`（资源库目录已包化）。


