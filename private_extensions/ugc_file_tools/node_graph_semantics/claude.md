# ugc_file_tools/node_graph_semantics 目录说明

## 目录用途
- 存放 **节点图“共享语义层”**：为 `.gia` 导出（`gia_export/node_graph`）与 `.gil` 写回（`node_graph_writeback`）提供共同依赖的规则与编码构件（single source of truth）。
- 目标：让导出/写回两条链路只依赖该层 + `contracts/`，避免相互跨域 import，降低“改一处牵一片”的耦合风险。

## 当前状态
- 该目录承载从 `node_graph_writeback/` 上移的可复用模块（纯规则/编码，不含 pipeline/IO）：
- `var_base.py`：VarType/VarBase 构造与常量强制转换（含字典/列表/结构体等）；并对齐真源的 0 值编码细节（如 Float=0.0 常用 empty bytes；id-like 的 0 常用 alreadySetVal=1 + empty bytes），同时对输入常量做兼容修正：Int=0 必须显式写入 nested message（否则部分节点如【获取列表对应值.序号】在编辑器中会显示为空）；Vector 的 empty VarBase 会保持 VectorBaseValue 的 message 结构（便于 roundtrip 到 IR 为 `[None,None,None]` 而不是 `None`）。Bool 常量对齐真源：true 写 `field_106.field_1=1`，false 写 `field_106=empty bytes`（不显式写 0）；在“仅写回类型/作为 type carrier”的空值场景（例如 ConcreteBase.inner 的空值），Bool/Enum(14) 也按真源使用 empty bytes。对“具体枚举 VarType”(enum_id，如 `受击等级=28`) 的占位值会从 node_data 的 EnumList 取第一项 item_id，缺失则直接抛错（fail-fast）。并明确 **enum_id 与内建 VarType_id 存在小号段冲突**，因此空值构造会先匹配内建类型（列表/字典/结构体等）再回退到“具体枚举”分支，避免把 `字符串列表(11)` 之类误编码为 EnumBaseValue。
  - `dict_kv_types.py`：字典（VarType=27）K/V 类型解析与默认值推断。
    - 兼容端口名形态：`字典_字符串到整数` / `字符串到整数`（用于 GraphModel 类型快照缺失但端口命名携带语义时的 K/V 提取）。
  - `enum_codec.py`：枚举常量（中文选项→enum item id）解析。
  - `signal_binding.py`：发送/监听/向服务器发送信号的 META binding 规则与导出/写回计划（single source of truth）。
  - `pin_rules.py`：端口 index/ConcreteBase.indexOfConcrete 等规则（含少量节点特例）；indexOfConcrete 推断优先 genshin-ts ConcreteMap，缺失/未命中时回退 node_data TypeMappings（`S<T:...>`）；并兼容 `L<R<T>>` 列表反射端口在仅拿到“列表容器 VarType(L<T>)”时回退到“元素 VarType(T)”以命中映射（例如【拼装列表】字符串列表的 indexOfConcrete=1 来自 TypeMappings(S<T:Str>)）。
  - slot_index→pin_index 映射包含少量“端口布局不一致”的节点特例：例如【创建元件】在 `.gil` 底层端口布局存在隐藏输入槽，GraphModel 端口从“是否覆写等级”开始需整体偏移以避免 pins 错位。
- `type_inference.py`：基于连线的端口类型兜底推断（兼容 GraphModel 仅携带 `effective_input_types/effective_output_types` 快照或缺失 `*_port_types` 时的反推证据读取）。
    - 反推补丁：当下游字典修改节点的 `字典` 端口仍为 `泛型字典` 时，允许利用其 `键/值` 的常量证据拼出别名字典（如 `字符串_字符串字典`）用于反推上游输出端口类型，避免上游泛型输出回退到 NodeEditorPack 默认类型（常见为整数）并写坏 `.gil`。
- `port_type_inference.py`：端口类型文本/泛型/常量/连线 → server VarType 的统一推断（写回/导出共用）；`get_port_type_text` 取证据优先级为 `*_port_types → effective_*_types → *_port_declared_types`；`infer_input_type_text_by_dst_node_and_port` 兼容接地/裁剪形态：可用 `graph_variables(name→type)` 作为【获取/设置节点图变量】`变量值` 的类型证据，并对【获取局部变量】`值` 在输出字段缺失时允许从 `初始值` 快照反推（避免字典KV/局部变量 concrete 推断退化）。
  - 增补：提供从 NodeEditorPack `TypeExpr`（如 `D<Str,Int>`）提取字典 K/V VarType 的公开解析函数，供 `.gia` 导出与 `.gil` 写回在 GraphModel 类型快照缺失时复用。
- `type_binding_plan.py`：类型/实例化(concrete)决策 Plan（字典 KV、`S<T:D<K,V>>` 与 `S<T:...>` 的 concrete/indexOfConcrete、拼装字典 concrete 选择、以及 Variant/Generic 的 concrete runtime_id 决策；并对 Variant/Generic 的候选类型做归一化：当同时收集到 `L<T>` 与 `T` 时优先使用 `T` 以避免 runtime_id 回退为 generic；并支持对 `S<T:D<K,V>>` 节点（例如【获取自定义变量】/【设置自定义变量】/【获取节点图变量】的 `变量值`）按别名字典(K/V) 反推 concrete_id 与 `indexOfConcrete`（同时兼容从 `变量值` 输入端口或输出端口取证据），避免真源导入回退为默认类型；对字典 K/V 双泛型节点（如【以键查询字典值】）会按 TypeMappings 同步输出端口的 `indexOfConcrete`，避免泛型输出回退为默认类型）。
  - 字典 K/V 双泛型节点（如【以键查询字典值】）当 “字典” 端口缺少别名字典文本时，允许用 `键` 输入与 `值/默认值` 的 VarType 反推 (K,V)，以支撑 `.gia` 字典 VarBase 必须携带 K/V 的要求。
  - `nep_type_expr.py`：NodeEditorPack `TypeExpr` 的反射端口判定（`R<T>` / `L<R<T>>` / `D<R<K>,R<V>>`）。
  - `layout.py`：节点稳定排序与坐标缩放/居中策略（供导出/写回统一复用）。
  - `graph_generater.py`：NodeDef 加载与流程端口判定等桥接 helper（仅公共 API）。
  - `graph_model.py`：GraphModel(JSON) 归一化 helper（兼容 wrapper）。
  - `type_id_map.py`：节点类型映射构建（node_type_semantic_map → node_def_key(canonical) → type_id_int），供导出/写回/pipeline 共同复用。
  - `genshin_ts_node_schema.py`：genshin-ts/NodeEditorPack schema 索引（用于 indexOfConcrete 推断/预检；端口类型校验兼容仅携带 `*_types` 快照字段的 GraphModel 形态）。

## 注意事项
- 该目录**只放纯语义/规则/编码**：禁止放导出/写回流程编排（pipeline）、落盘 IO、或 UI/CLI 入口。
- 允许依赖 `ugc_file_tools/contracts/`（契约层）；禁止反向依赖 `gia_export/*` 或 `node_graph_writeback/*`（避免循环与边界坍塌）。
- 不使用 try/except；失败直接抛错（fail-fast）。

