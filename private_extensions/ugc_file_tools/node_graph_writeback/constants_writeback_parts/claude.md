# constants_writeback_parts 目录说明

## 目录用途

- 存放 `node_graph_writeback/constants_writeback.py` 的“分阶段/按职责”实现，避免 `constants_writeback.py` 单文件继续膨胀。
- 该子包仅供 `constants_writeback.py` 入口编排调用；外部模块不应直接依赖这里的私有阶段函数。

## 当前状态

- 入口：`node_graph_writeback/constants_writeback.py`（保持旧 import 路径稳定；负责参数校验与阶段编排）。
- 分阶段实现按职责拆分：
  - `context.py`：写回上下文的构建（node_data/NEP 画像/连线推断/信号节点判定；兼容 server_send 的标题差异）。
- `stage_prepare_node.py`：单节点写回前的准备（端口列表、信号绑定判定、候选类型收集等）；信号 META binding **不依赖隐藏字段 `__signal_id`**，仅要“信号名为字符串常量且该端口无 data 入边”即可启用，避免参数 pins 整体错位；动态端口节点补丁：`拼装列表` 写回 pin0(数量)；`拼装字典` 写回 pin0(len，键/值端口数量，并按 Plan 支持特例不写)；字典 KV / `S<T:D<K,V>>` concrete+indexOfConcrete / 拼装字典 concrete 的“决策 Plan”统一复用 `ugc_file_tools.node_graph_semantics.type_binding_plan`，避免与导出侧分叉；并且 **Variant/Generic concrete 收敛不强依赖 NodeEditorPack**：当 NEP 缺失/画像缺失，或端口 pin_def 无法命中时，会回退使用 GraphModel 的 `input_port_types/input_types` + 连线推断收集候选类型，避免 runtime_id 退化导致 data-edge 丢失。
  - 兼容：监听信号“事件节点”（GraphModel: `node_def_ref.kind=event` 且 title/key=信号名）在 prepare 阶段会回退使用【监听信号】NodeDef，以便后续阶段能按同口径修剪 records（尤其是禁止保留 OutParam 占位，避免端口错位）。
  - 对齐真源：当 base `.gil` 能提供 `signal_name -> signal_index` 映射时，发送信号/监听信号/向服务端发送信号三类节点在命中静态绑定后都会携带 `signal_binding_signal_index_int`，供后续阶段写入 `node.field_9(signal_index)`（signal-specific runtime 下必需）。
  - 对齐 after_game：为 `对字典设置或新增键值对` 补齐 `值` 端口的占位 InParam(index=2) pin（当模板样本缺失该 record 时），避免 missing pins。
- `stage_inparam_constants.py`：input_constants → InParam pins 写回（含 enum 常量映射与结构体字段写回特例；端口类型读取兼容 `input_port_types/input_types`；信号静态绑定下会按信号规格覆写参数 VarType，并在 base 映射可用时写入参数 pins 的 compositePinIndex；同时对齐真源：信号参数 pin 的 i2(kernel) 与 slot_index 一致，避免 kernel=0 导致参数端口错位）；【获取局部变量】`初始值` 的“纯数字字符串→GUID 空占位”补丁为**按类型证据触发**（仅当端口已能确定为 GUID 时生效，避免误伤整数/布尔初始值）。
  - Create_Prefab（`创建元件`）：对齐真源端口口径，补齐『是否覆写等级』InParam 的 PinIndex2(kernel)=7；当覆写等级为 False 时，跳过/删除 `等级/单位标签索引列表` 常量 pins，避免多余端口落盘导致编辑器/真源解释错位。
  - 反射/泛型端口常量写回：当端口在 NodeDef 中声明为 `R<T>`/泛型家族（declared generic）时，常量写回会落盘 `ConcreteBase + indexOfConcrete` 作为类型载体（即便最终 VarType 已能确定），避免“连线/常量混用”时运行态按错误类型解释 pin。
  - 复合节点/结构体等需要稳定 pin 映射的节点：会从 `record_id_by_node_type_id_and_inparam_index` 补齐常量 InParam record 的 `field_7`（persistent_uid/compositePinIndex），避免“仅连线端口有 field_7、常量端口缺失”导致端口映射错位。
  - 额外兜底：对信号节点参数端口强制 `kernel_index==shell_index`，避免在未命中 META binding 或外部画像漂移时写出 `pin_index2=0` 造成多参数端口错位/串号。
    - 额外约定：当 `input_constants[port]=None` 时表示“该端口不写常量/保持缺省”，写回阶段会跳过强制转换并在模板克隆场景下删除该 pin 的纯常量 InParam record，避免出现 `None→整数` 之类的写回崩溃。
    - 对齐 after_game：对 `对字典设置或新增键值对.值` 端口，`input_constants[值]=None` 不会删除模板占位 pin record（保持端口结构稳定）。
  - `stage_signal_meta.py`：信号节点 META pin 写回与 records 修剪（对齐真源样本）。
    - generic runtime（300000/300001/300002）：当 base 映射可用时写入 META 的 source_ref + compositePinIndex，并清理模板残留的 flow field_7。
    - generic runtime（300000/300001/300002）：META pin 必须写入 `field_4=6(Str)`（避免 `type_id_int=null` 导致信号绑定/端口展开错位）。
    - signal-specific runtime（常见 0x6000xxxx/0x6080xxxx）：META pin 通常省略 source_ref 与 `field_4`，写回侧遵循该口径（不再强制写入 `field_4`）。
    - 对齐真源：signal-specific runtime 下，META pin 的“信号名字符串 VarBase”其 ItemType.type_server(field_100) 常为 empty bytes（而非显式 `{field_1=6(Str)}`），写回侧在该场景会主动归一化为 empty bytes，避免官方侧更严格校验失败。
    - 当 base 缺失 node_def/106 导致无法直接拿到“信号名端口 index”时，会按真源端口块布局基于“参数端口 index”反推（send/listen/server_send 使用不同 offset），避免退化为 `min(param)-1` 导致 compositePinIndex 错位。
- `stage_dynamic_ports.py`：动态端口节点（拼装字典/拼装列表）占位 pins 同步与特例补丁（端口类型读取兼容 `output_port_types/output_types` 与 `input_port_types/input_types`）；其中 `拼装列表` 会根据输出端口的“列表别名”（如 `字符串列表/实体列表/三维向量列表/...`）推导元素类型，并同步写回实际端口对应 pins 的 VarType + `ConcreteBase.indexOfConcrete`，避免模板默认类型导致端口类型收敛错误。
  - 对齐 after_game：不再无条件补齐 1..100；仅保证 GraphModel.inputs 中实际出现的端口对应 pin 存在，并裁剪超出范围的未连线占位 pins，减少“空槽位 pins”差异噪声。
  - `stage_outparams.py`： declared generic 输出端口的 OutParam 类型写回（含字典 KV 类型描述）；当 `output_port_types/output_types` 缺失或仍为泛型时，可从 `inferred_out_type_text` / Variant candidates / Plan(dict KV) 推断并写出 OUT_PARAM，避免保留模板默认值导致端口类型错误；并支持对【获取/设置节点图变量】的“变量值”端口按 `graph_variables(name→variable_type)` 反推具体类型写入 OUT_PARAM；**字典 OUT_PARAM 若仍无法解析出 K/V（别名字典缺失）会直接抛错**，禁止回退写入导致编辑器显示错误字典类型；OutParam 的 `indexOfConcrete` 优先使用 `stage_prepare_node` 的 Plan（覆盖 `S<T:D<K,V>>` 与 `S<T:...>` 的 TypeMappings），未命中时再回退 `pin_rules`。
  - 额外约束：当推断结果为字典(VarType=27)时，OutParam 必须写出 MapBase 的 K/V 类型信息，即便端口名不是“字典”（例如 `获取自定义变量.变量值`），否则编辑器可能忽略 record 并回退为默认类型。
  - 对齐 after_game：当 `数据类型转换.输出` 端口在本图中没有出边时，不强制写 OUT_PARAM 类型，保留模板默认值（避免 direct 导出与 after_game 在该类节点上出现 pin_field_mismatches）。
  - 对齐真源：监听信号**事件节点**（GraphModel: `node_def_ref.kind=event` 且 outputs 含 `信号来源实体`）禁止写入/保留 OutParam(kind=4) records；信号参数端口由信号规格动态展开，数据连线仅通过目标 InParam.connect 表达（避免端口解释错位）。
  - 对齐真源：list VarType（如 字符串列表=11）的 OUT_PARAM 若使用 ConcreteBase 包裹，其 inner VarBase 必须为 ArrayBase(10002)，空数组值通常以 `field_109=empty bytes` 表达；写回侧会在检测到模板残留为 EnumBaseValue 等错误 cls 时，强制按 schema 重建该 OutParam record，避免官方侧更严格校验失败。
  - `stage_runtime_id.py`：Variant/Generic 的 concrete runtime_id 推断与 NodeProperty 写回；concrete_id 的决策统一复用 `ugc_file_tools.node_graph_semantics.type_binding_plan.build_variant_concrete_plan`，避免与 `.gia` 导出侧分叉。
- 对齐真源：监听信号“事件节点”（GraphModel: `node_def_ref.kind=event` 且 outputs 含 `信号来源实体`）：
  - 若节点 runtime 仍为通用 300001（监听信号），则不写入 `concrete_id`（避免端口解释漂移）。
  - 若节点 runtime 已切换为 signal-specific（0x4000xxxx/0x6000xxxx...），则允许写入 `concrete_id`（与 genericId 对齐）。

## 注意事项

- 不使用 try/except：失败直接抛错，便于定位写回合约与口径问题。
- 依赖方向保持单向：`constants_writeback_parts/*` 可以依赖 `node_graph_writeback` 其它模块（如 `record_codec.py`），但避免反向 import 本子包，防止循环引用。
- 如需跨模块复用 helper，应在 `constants_writeback.py` 暴露公开 API（无下划线），避免上层直接 import 子包内部实现。

