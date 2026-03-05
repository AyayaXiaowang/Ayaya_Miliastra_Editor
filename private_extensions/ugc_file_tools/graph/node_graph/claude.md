# ugc_file_tools/graph/node_graph 目录说明

## 目录用途
- NodeGraph 子域语义层：面向 `.gia` 内嵌的 NodeGraph（GraphUnit/pins/edges/variables 等）与其与 GraphModel(JSON) 的互通规则。
- 该目录承载“跨导出/写回共用”的 NodeGraph 语义工具，避免把规则散落在 `gia_export/` 或 `node_graph_writeback/` 导致分叉。

## 当前状态
- `ir_parser.py`：从 `.gia` / `.gil payload` NodeGraph 结构抽取 Graph IR（供诊断/对照工具与导入器复用）。
  - Graph IR 的 pin 摘要会额外包含 ConcreteBase(10000) 的诊断字段（`varbase_cls_int` / `concrete_index_of_concrete_int` / `concrete_inner_cls_int`），便于排查反射/泛型端口的实例化(indexOfConcrete)问题。
- `gia_graph_ir.py`：读取节点图 `.gia` 文件，提取其中的 NodeGraph GraphUnits 并输出“Graph IR dict 列表”（供导入/生成 Graph Code 复用）。
- `graph_ir_to_graph_model.py`：将 Graph IR（`.gia` 语义）转换为 `engine.graph.models.GraphModel` + codegen metadata。
  - 端口 index 规则：数据端口 index 不包含流程口；对 `拼装列表/拼装字典` 等变参节点做 index→端口名的特殊映射（与引擎校验/导出侧保持一致）。
  - 会同步 Graph IR 的 `graph_variables` 到 `GraphModel.graph_variables`（用于生成 Graph Code 的 `GRAPH_VARIABLES`，并支撑【获取/设置节点图变量】类型推断）。
  - 会将 pins 的 `type_expr` 归一化为 `GraphModel.metadata.port_type_overrides`，用于 codegen 生成更准确的中文类型注解（避免泛型端口回退到默认字符串）。
- `gil_payload_graph_ir.py`：从 `.gil` payload（section10 groups 的 NodeGraph blobs）**直接解析** Graph IR（in-memory）。
  - 供 `commands/parse/parse_gil_payload_to_graph_ir.py` 与 pytest golden/roundtrip 用例复用，避免入口脚本复制 blob 扫描与解码逻辑。
  - `.gil` 容器切片与 header meta 提取统一复用 `ugc_file_tools.gil_dump_codec.gil_container`，降低口径漂移风险。
- `pos_scale.py`：节点坐标缩放/居中等与编辑器画布语义对齐的工具函数。
- 端口类型/VarType 推断：统一位于 `ugc_file_tools/node_graph_semantics/port_type_inference.py`（shared semantics）。

## 注意事项
- 本目录不承载 `.gia` 具体导出流程或 `.gil` 写回流程；流程编排分别位于 `gia_export/` 与 `node_graph_writeback/`。
- 对外复用优先暴露“无下划线”的公开 API；跨模块禁止 `from ... import _private_name`。

