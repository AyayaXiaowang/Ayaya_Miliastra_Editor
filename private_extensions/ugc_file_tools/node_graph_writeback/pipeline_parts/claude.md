# pipeline_parts 目录说明

## 目录用途

- 存放 `node_graph_writeback/pipeline_parts/pipeline.py` 的“分阶段/按职责” helper 实现，避免写回主流程继续膨胀。
- 对外稳定入口仍通过 `node_graph_writeback/pipeline.py`（薄转发）与 `writer.py` 暴露。

## 当前状态

- 本目录包含：UIKey/诊断、占位符收集与 registry 注入、GraphModel(JSON) 加载与归一化、template/base 载入、信号映射提取、payload group/entry 工具、scope 推断等模块。
- `pipeline.py`：薄转发入口（对外仍由 `node_graph_writeback/pipeline.py` 与 `writer.py` 暴露）。具体实现拆分到本目录的 mode/helper 模块，避免单文件继续膨胀。
- `pipeline_graph_model_loader.py`：统一“GraphModel(JSON) → 写回输入”的加载与约束（占位符扫描、scope 推断与一致性校验、GraphVariables 提取与类型映射），供模板克隆/纯 JSON 两条链路共用。
- 写回模式实现：
  - `pipeline_mode_template_clone.py`：模板克隆模式（复用样本 `.gil` 的节点/record 模板）。
  - `pipeline_mode_pure_json.py`：纯 JSON 模式（不依赖模板，按 schema 写入）。
- `pipeline_parts/pipeline.py` 在进入写回阶段前会对输入 GraphModel 做一次“有效端口类型补齐”：
  - 写回前会将 `graph_variables` 强制注入到 graph_model payload（某些输入 JSON 会把 graph_variables 放在外层），确保 EffectivePortTypeResolver 能按变量表推断端口有效类型；
  - 随后通过 `ugc_file_tools.graph.port_types.standardize_graph_model_payload_inplace(...)` 统一补齐 `edge.id` 并调用引擎 EffectivePortTypeResolver（与预览同口径）对 payload 就地 enrich，生成 `input_port_types/output_port_types` 与 `*_port_declared_types`；
  - 写盘前会生成端口类型缺口报告（gap_report）；若 `counts.total>0`（存在任意非流程端口 effective 仍为泛型家族）将 fail-fast 阻断写回，并在 `output_gil_path` 同目录写入 `reports/port_type_gaps/*.json` 作为可复现证据；
  - 并对【字典原地修改】节点（如“对字典设置或新增键值对”）执行 fail-closed：必须得到明确的别名字典(K/V)，否则直接抛错，禁止回退写入导致“字符串-字符串字典”这类必错结果。
  - 目的：把预览态的“有效类型”强制落盘到写回输入中，消除字段形态分叉与类型推断退化，并避免静默回退掩盖类型实例化缺失。
- 上述“端口类型补齐/字典 fail-closed”拆分在 `pipeline_port_types.py`；GraphVariables 表合并与最小归一化在 `pipeline_graph_variables_merge.py`。
- `pipeline_graph_variables_autofill.py`：GraphVariables 的辅助逻辑（name→type 映射；从 UI registry 自动补齐 default_value，可选排除名单；并支持在缺少外部 registry 时从 base `.gil` 的 UI records 反查 layout root GUID，回填 `LAYOUT_INDEX__HTML__*` 并补齐“布局索引_*”类变量默认值），避免写回主流程膨胀。
  - 模板克隆模式与 `--pure-json` 纯 JSON 写回模式都会执行该 auto-fill（保持“直写回”与 after_game 的布局索引口径更接近）。
  - 当 base `.gil` 缺少 UI records（空存档常见）时，写回会 best-effort 合并运行时缓存的 UI guid 证据（legacy）：
    - 优先选择 `ui_export_records.json` 里“覆盖当前 required_ui_keys 最多”的 `ui_guid_registry_snapshot`；
    - 再回退到当前 `ui_guid_registry.json`。
- `pipeline_parts/pipeline.py` 写回 GraphEntry['6']（GraphVariables）时遵循“真源优先 + 代码级修正”：
  - 若 base `.gil` 中同 graph_id 已存在 GraphVariables 表：
    - **仅对 `布局索引_*`** 这类“运行态回填型变量”优先保留 base 条目（避免覆盖真源已解析的 layout index GUID）；
    - 其余变量按代码级 `GRAPH_VARIABLES` 重新生成（确保字典类变量的默认值不会被旧产物的空字符串占位污染）。
  - 即使 GraphModel 未声明 `graph_variables`（为空），也可能从 template/base 继承变量表；写回侧会对继承表做最小归一化（例如 id-like 的 0 默认值用 empty bytes 表达），避免历史模板编码差异导致官方侧更严格校验失败。
- `pipeline_ui_registry_legacy.py`：遗留 UIKey→GUID registry 读取（仅用于诊断/旧工具链），主写回流程不依赖该文件。
- `pipeline_gil_payload.py`：NodeGraph payload 的低层工具：
  - 按 `graph_id_int` 删除旧 entry（用于 overwrite fallback / 去重修复）；
  - overwrite 优先“就地替换 entry”（保持 groups 顺序与 group 元数据不变，避免 `group_index` 漂移导致目录/分组错位）；
  - 空存档下自举 root4/10 节点图段。
- `pipeline_entry_ops.py`：对 groups/entry 的查找、overwrite/append 策略封装（复用 `pipeline_gil_payload.py` 的低层操作）。
- `pipeline_wire_write.py`：wire-level 写盘（只替换必要段）与缺失枚举常量报告输出。
- 复合节点依赖注入：`pipeline_parts/pipeline.py` 会在写回 GraphEntry 前基于 GraphModel 收集 `composite_id`，生成并注入：
  - `payload_root['10']['2']` 的 NodeInterface wrappers；
  - `payload_root['10']['4']` 的 CompositeGraph（含子图与 port_mappings）；
  - 并将复合节点虚拟输入端口的 pin persistent uid 合并进 `record_id_by_node_type_id_and_inparam_index`，供常量/连线写回补齐 pin record `field_7`。
- 信号映射提取（`pipeline_signals.py`）除端口索引外，还会提取：
  - `signal_name -> 参数 VarType 列表`（按参数顺序），用于写回侧对齐 GIA 口径：发送信号的参数端口类型由信号规格为真源覆写，并确保 META/source_ref/compositePinIndex 绑定稳定。
  - `signal_name -> signal_index`（来自 signal entry 的 `field_6`），用于写回侧对齐真源：信号节点实例需要写入 `node.field_9`（尤其是监听信号事件节点）。
  - 信号名端口索引优先从 node_def 的 `106[*].8(port_index)` 提取；当 base 缺失 node_def/106 时，允许仅基于“参数端口索引”按真源端口块布局反推（send/listen/server_send 使用不同 offset），避免退化为 `min(param)-1` 导致 compositePinIndex 错位。
- `pipeline_parts/pipeline.py` 支持 `prefer_signal_specific_type_id` 策略开关（默认 False）：用于控制信号节点是否在“静态绑定 + base 映射可用”时将通用 runtime type_id（300000/300001/300002）替换为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx；由 base `.gil` 的 node_def_id 0x4000xxxx/0x4080xxxx 推导）。
  - 该策略为 best-effort：仅当 base `.gil` 能解析到信号名→node_def_id 映射时才会切换；切换不再依赖模板库覆盖（模板缺失时会走最小合成节点）。信号事件节点（GraphModel: kind=event, title=信号名）在无样本合成时会按【监听信号】NodeDef 兜底，避免因 title=信号名 而无法定位 NodeDef。
- `pipeline_parts/pipeline.py` 负责“主流程编排”（实现层）；`node_graph_writeback/pipeline.py` 负责对外稳定导入路径（re-export）。
  - 对外可复用的 helper 若需跨模块调用，应优先在 `node_graph_writeback/pipeline.py` 暴露为 **公开 API（无下划线）**，避免上层 `from ... import _xxx` 导入私有符号。
  - 写盘策略：写回完成后不再对整份 payload 做 decode→encode 全量重编码；改为读取 base `.gil` 的 payload raw bytes，并在 wire-level 仅替换 `payload_root.field_10`（NodeGraphs section；必要时附带 `field_5`），其余段 bytes 原样保留（用于规避 UI base 下 templates 等段发生 payload drift 导致官方侧拒识）。
- UIKey 预检（`pipeline_ui_keys.py`）：
  - 缺失 UIKey 不再阻断写回：会在写回阶段回填为 0（包含 `UI_STATE_GROUP__*__*__group` 与普通 UIKey）。
  - 仍会输出缺失 keys 的增强诊断（出现位置/相似 key/对 state-group 的期望 record 名称提示），便于后续补齐 UI 导出或修正 HTML 标注。
- IDRef 占位符（`pipeline_placeholders.py`）：
  - `entity_key:` / `component_key:`：缺失映射不再阻断写回，缺失项回填为 0（与 `.gia` 导出侧策略一致）；写回报告会输出缺失清单。

## 注意事项

- 依赖方向保持单向：本子包可以依赖 `node_graph_writeback` 其它模块（如 `gil_dump.py`/`var_base.py` 等），但避免反向 import 本子包，防止循环引用。
- 不使用 try/except：失败直接抛错，便于定位写回合约与口径问题。
- after_game 对齐补丁（`pipeline_parts/pipeline.py`）：
  - 在常量/OutParam 写回后，会对 `拼装列表` 节点裁剪“未使用的高 index 未连线占位 InParam pins”，仅保留实际被使用（有入边或有常量）的端口范围，避免 direct 写回产物出现大量空槽位 pins diff 噪声。
  - 在 edges 写回完成后，会将每个节点的 pins(records) 按 `(kind,index)` 做稳定排序（flow→inparam→outparam→meta），避免多阶段 patch/append 造成顺序漂移；该归一化对信号节点尤为关键（参数 pin 后补时编辑器可渲染但运行时可能更严格）。
  - 裁剪逻辑拆分在 `pipeline_after_game_alignment.py`（触发仍由 feature flag 控制，fail-fast 不吞错）。