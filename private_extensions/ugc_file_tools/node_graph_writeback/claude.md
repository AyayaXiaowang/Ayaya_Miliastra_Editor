# node_graph_writeback 目录说明

## 目录用途

- 核心能力：**GraphModel(JSON) → `.gil` 节点图段写回**（server/client）。
- 目标：入口稳定、实现模块化、可复用/可测试；并与导出侧共享同一套“端口类型/VarType/信号绑定”语义口径（单一真源）。

## 当前状态

- 统一工具入口：`python -X utf8 -m ugc_file_tools tool graph_model_json_to_gil_node_graph --help`（wrapper 位于 `ugc_file_tools/commands/`）。
- 导出中心/交付进游戏测的推荐入口：`python -X utf8 private_extensions\\run_ugc_file_tools.py project import ...`（走 `pipelines/project_writeback.py`，与导出中心 UI 同款口径；避免节点图列表/索引等 UI 依赖字段分叉）。
- 对外稳定导入路径：
  - `writer.py`：薄门面（re-export）。
  - `pipeline.py`：稳定导入路径（薄转发到 `pipeline_parts/`）。
  - `prechecks.py`：写回前模板覆盖预检、写回后合约校验（含 genshin-ts/NEP 画像校验）。
- 两条写回模式：
  - **模板克隆模式**：复用样本 `.gil` 的 node/record 模板（覆盖更广）。
  - **纯 JSON 模式**：从空存档自举节点图段，不依赖任何现有模板（更偏内部诊断/最小自举；不作为导出中心交付链路入口）。
- 写回前统一 enrich：使用引擎 `EffectivePortTypeResolver` 补齐 `*_port_types` 与 declared types（与预览/导出同口径），避免“预览正确但写回落盘退化”的分叉。
- 关键阶段模块：
  - `constants_writeback.py`：常量与端口类型/Concrete 写回（含字典 K/V、反射端口 `indexOfConcrete` 等）。
  - `edges_writeback*.py`：flow/data 连线写回（含类型传播与 record 落盘策略）。
  - `pipeline_parts/`：主流程与输入预处理（UIKey/占位符、GraphVariables、信号映射、payload group/entry 工具等；详见其 `claude.md`）。
- 反射/泛型端口写回口径（重要）：
  - 当端口在 NodeDef 中声明为 `R<T>`/反射/泛型家族（declared generic）时，**无论该端口是常量还是连线输入**，写回侧都会落盘 `ConcreteBase + indexOfConcrete`（作为类型载体），避免游戏运行态按错误类型解释 pin 而出现“值为空/不生效/端口错位”。
  - 信号 META 绑定节点的“参数端口”为例外：按真源/GIA 口径直接写基础 VarBase，不包 ConcreteBase。
- 共享语义层：写回侧禁止依赖 `ugc_file_tools.gia_export.*` 的实现模块；统一复用 `ugc_file_tools/contracts/` 与 `ugc_file_tools/node_graph_semantics/`。
- 复合节点（GIL）写回已支持：
  - 复合节点实例 `node_type_id_int` 由 `composite_id` 稳定映射到 `0x4000xxxx`（见 `composite_id_map.py`）。
    - low16 强制落在 `0x0001..0x7FFF`，避免被部分链路当作 int16 负数导致查表失败与节点退化。
  - 写回会在 payload `section10` 注入复合节点依赖：
    - `section10['2']`：NodeInterface(node_def) wrappers（含虚拟引脚列表 100~103，pin persistent uid=field_8）。
      - persistent uid（field_8）采用真源口径：按 kind 顺序（InFlow/OutFlow/InParam/OutParam）连续分配，常见从 `24` 起（InFlow=24, OutFlow=25, InParam=26...），并与节点图 pin record 的 `field_7(compositePinIndex)` 对齐。
    - `section10['4']`：CompositeGraph（子图 nodes=field_3，接口映射 port_mappings=field_4）。
    - NodeInterface 的 data pins（`102/103`）会写入 `type_info(field_4)`（对齐真源）：
      - 基础字段：widget_type(field_1) + var_type_shell(field_3) + var_type_kernel(field_4)
        - Vec3(三维向量, VarType=12) 的 widget_type 必须为 7（缺失会导致编辑器/游戏侧不生成可编辑输入控件）。
      - 列表：额外写入 field_102（包含元素类型的 type_info）
      - 字典：额外写入 field_105（包含 key/value VarType；缺失时直接 fail-fast）
      - Bool/Enum：额外写入 field_101（Bool 固定为 1；Enum 为 enum_id）
      - flow pins 保持空 message。
    - CompositeGraph.port_mappings 的内部端口索引区分 shell/kernel：mapping.field_3=internal_shell_sig、field_4=internal_kernel_sig；两者不保证相等（需通过 NEP `data.json` 解析端口对应的 ShellIndex/KernelIndex）。
    - CompositeGraph.inner_nodes 的每个 inner node 会写入 `field_4`（repeated NodePin message）：
      - 从写回侧 NodeGraph records 解码得到 NodePin（保留 connects/ConcreteBase/VarType 等），并额外补齐 declared generic pins 的“类型载体 pin”，避免复合子图内节点端口在编辑器中退化为“泛型”。
      - 对齐真源：当 inner node 的列表/字典端口缺少 `ConcreteBase.indexOfConcrete` 或字典 K/V 载体时，会基于端口的有效类型快照补齐（列表按真源 concrete 顺序写入 index；字典补齐 MapBase 的 K/V + `ConcreteBaseValue.field_5`），避免编辑器回退显示为“整数列表/泛型字典”。
      - 对齐真源：允许 NodePin 省略 `field_2(PinIndex2)`（signal-specific runtime 的 META pin 常见），解码时会归一化补齐为与 `field_1` 相同，避免复合子图内信号绑定信息丢失。
    - 对齐真源：当信号节点命中静态绑定且 base 映射可用时，复合子图 inner node 允许携带 `field_9(signal_index)`，用于 signal-specific runtime 的信号主键对齐。
    - 对齐真源：复合子图 inner node 若命中 signal-specific runtime_id，则 **shell/kernel runtime_id 必须一致**（都写为 send/listen/server 的 0x4000xxxx），避免编辑器按通用信号节点端口表解释导致“动态端口索引错位”。
    - 对齐真源：CompositeGraph.inner_nodes 的 `resource_locator.kind` 需与 runtime_id 前缀匹配：
      - builtin：`kind=22000`
      - 自定义/信号/复合等 `0x4000/0x4080/0x6000/0x6080` 前缀：`kind=22001`
  - 复合节点虚拟输入端口的 pin record `field_7` 会按 NodeInterface 的 persistent uid 补齐（通过 `record_id_by_node_type_id_and_inparam_index` 传递）。
  - 复合节点子图（sub_graph GraphModel）在写回前也会执行端口类型标准化与 EffectivePortTypeResolver enrich（补齐 `input/output_port_types` 与 declared types），避免子图内字典/动态端口等类型推断退化导致 pins/records/Concrete 错漏。
  - 复合节点实例（host graph 的 composite node）端口类型会强制对齐到复合节点接口 virtual pins 的 `pin_type`，并写入到 GraphModel 的 `input_port_types/output_port_types`，避免端口名退化为“列表/字典”时写回沿用模板默认值导致“列表全变整数列表、字典全变泛型”。
    - 当复合节点实例的 `inputs/outputs` ports 列表被上游标准化阶段清空时，会基于 virtual pins 的顺序与名称补齐 ports 列表；若 ports 非空但长度不匹配则直接 fail-fast。
- 诊断/二分：环境变量 `UGC_WB_DISABLE="flag1,flag2"`（含 `all`）用于禁用部分补丁点以做二分定位。
- after_game 对齐补丁：可选裁剪少量“真源 after_game 导出会消失”的冗余 data edges（例如 `数据类型转换.输出 -> 对字典设置或新增键值对.值`），但仅在目标端口仍有其它数据供给时才会执行，避免改变语义与导致端口类型回退。
- 落盘归一化：最终会将每个节点的 pins(records) 按 `(kind,index)` 稳定排序，减少阶段 append 导致的顺序漂移。
  - 节点坐标写回对齐真源：当坐标分量为 `0.0` 时省略对应字段（NodeInstance.field_5/field_6），避免无意义的 0 值字段造成 dump diff 噪声，并更贴近官方导出编码。

## 注意事项

- fail-fast：不使用 `try/except` 吞错。
- 依赖方向单向：上层只依赖 `writer.py/pipeline.py`；禁止跨模块导入 `pipeline_parts/*` 私有实现。需要复用的 helper 必须暴露为公开 API（无下划线）。
- data-link 编码护栏：`pin_index.index=0` 时省略 `field_2`；字典端口必须写入 K/V；模板 record 若显式存在 `field_2=0` 需规范化为“省略 field_2”，避免编辑器忽略连线。
- 信号节点：静态绑定判定以 `__signal_id` 或“信号名为字符串常量且无 data 入边”为准；监听信号事件节点（GraphModel: `node_def_ref.kind=event` 且 outputs 含 `信号来源实体`）允许仅依赖 `node_def_ref.key/title` 做信号名绑定；当 base `.gil` 信号表可提供映射时会提升为 signal-specific runtime_id，并补齐 `node.field_9(signal_index)` 与 META/flow 的 compositePinIndex，避免端口错位/信号名串号。
  - 补充：信号节点的 type_id 提升（generic 300000/300001/300002 → signal-specific node_def_id）同样不应依赖 `__signal_id`；只要满足“信号名为字符串常量且无 data 入边”并且 base 映射可用，即可提升，以保证编辑器能展开动态端口。
- 复合节点依赖注入使用引擎 `composite_node_manager` 按需加载子图；缺失/解析失败会直接抛错（fail-fast）。
- section10 merge 口径：
  - 默认仍优先保留 base 中已存在的 NodeInterface/CompositeGraph（避免覆盖真源中存在但写回侧尚未建模的字段）。
  - NodeInterface：当 base 条目缺少关键引用/内容（例如 signature.graph_ref 缺失/编码异常）时会覆盖，避免复合节点在编辑器中表现为“空壳”。
  - CompositeGraph：只要本次生成的 incoming 包含 inner_nodes，就会覆盖 base（可编辑性优先，避免 base 里残留的“泛型/错误子图”被永久保留）。
  - `section10['2']`（NodeInterface 表）与 `section10['4']`（CompositeGraph 表）真源形态均为 **repeated wrapper list**：`[{'1': <obj>}, ...]`（每条 entry 用 field_1 包一层），而不是 `{'1': [<obj>, ...]}` 这种“再包一层 message(field_1=repeated)”的形态。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。
