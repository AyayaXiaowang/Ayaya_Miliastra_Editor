# ugc_file_tools/graph 目录说明

## 目录用途
- 存放 `ugc_file_tools` 的 **Graph / GraphModel / NodeGraph** 领域公共逻辑（偏“语义层/库逻辑”），供 `.gil` 写回与 `.gia` 导出等多条链路复用。
- 该目录的代码应尽量保持“可单测、少 IO、无 UI 依赖”，避免被 `commands/`（入口层）反向依赖。

## 当前状态
- `port_types.py`：GraphModel payload 的端口类型补齐与标准化入口（写回/导出共用）：
  - 直接复用引擎侧 `EffectivePortTypeResolver` 生成 `input_port_types/output_port_types`（有效类型快照）；
  - 同时补齐 `input_port_declared_types/output_port_declared_types`（声明类型快照）；
  - `*_port_types` 只允许写入 resolver 的有效类型输出；推断缺失时显式写入 `"泛型"`（禁止回退写入 declared）。
  - 标准化入口 `standardize_graph_model_payload_inplace(...)` 负责补齐 `graph_variables` 与 `edge.id`，避免导出/写回各自兜底导致口径分叉。
  - NodeDef 定位默认以 `node_def_ref` 为唯一真源；title → NodeDef.name 回退仅在显式开启 `allow_title_fallback=True` 的离线迁移/兼容诊断场景使用，交付边界默认禁用以避免漂移固化。
- `port_type_gap_report.py`：GraphModel payload 的端口类型缺口报告（纯逻辑）：枚举仍为“泛型家族”的端口并做少量 fail-fast 分级（供导出/写回链路落盘 report 与诊断）；gap item 需标注 `evidence_source`，并在 `node_def_ref.kind="event"` 时携带 `event_mapping(event_key/mapped_builtin_key)` 证据。
- `model_ir.py` / `model_files.py`：GraphModel/GraphCode 相关的公共模型与文件处理工具。
- `pyugc_graph_model_builder.py`：**pyugc → GraphModel** 单一真源：将 `节点图/原始解析/pyugc_graphs/graph_*.json` 转换为 `engine.graph.models.GraphModel`。
- `code_generation.py` / `code_generation_impl.py`：从项目存档目录批量生成 Graph Code：
  - GraphModel → Graph Code 的生成统一调用 `app.codegen.ExecutableCodeGenerator`（工具层仅做薄封装/调用）。
  - 当 `node_type_semantic_map.json` 缺少映射导致无法构建 GraphModel 时，会生成“可校验的占位节点图”，避免链路被全量阻断。
- `node_graph/`：NodeGraph 子域（`.gia` 内嵌 NodeGraph 结构）的公共逻辑：
  - `ir_parser.py`：解析 `.gia` NodeGraph → Graph IR 的语义抽取器。
  - `pos_scale.py`：节点坐标缩放/偏移等与编辑器视口语义对齐的工具。
  - 端口类型/VarType 推断：统一位于 `ugc_file_tools/node_graph_semantics/port_type_inference.py`（避免导出/写回分叉）。

## 注意事项
- 本目录属于“语义层/库逻辑”，禁止放置 pipeline 编排与落盘流程；入口与编排应位于 `pipelines/` 或 `commands/`。
- 跨域共享规则若能保持纯函数（无 IO），优先考虑进一步下沉到 `ugc_file_tools/contracts/`，作为更强约束的契约层。

