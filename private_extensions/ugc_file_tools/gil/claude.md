# ugc_file_tools/gil 目录说明

## 目录用途

- `ugc_file_tools.gil`：GIL 领域的公共能力收敛目录（`.gil` 解析、扫描、列表、以及与 UI/导出中心共享的轻量工具函数）。

## 当前状态

- `builtin_empty_base.py`：提供“程序内置空存档 base `.gil`”的定位函数 `get_builtin_empty_base_gil_path()`，供导出中心的“导出为空存档”选项复用（当前指向 `builtin_resources/empty_base_samples/empty_base_with_infra.gil`）。
- `infrastructure_bootstrap.py`：补齐“空壳/极简 base `.gil`”缺失的基础设施段（当前覆盖：`root4/11` 初始阵营互斥字段 key=13、`root4/35` 默认分组列表、以及常见缺口的 `root4/6` 与 `root4/22`），用于降低“编辑器可渲染但官方侧严格校验失败”的风险。
  - `root4/11` 的 key=13 补齐优先按条目内稳定键（常见为 key=3）匹配 bootstrap 样本；当 base 条目的匹配键漂移/缺失导致无法命中时，会退化为“按 index 对齐补齐”（entries 长度一致时）并提供保守兜底，避免单条缺失导致官方侧解析失败。
  - `root4/35` 默认分组列表仅补齐“已观测的最小可用口径”（16 项 canonical 分组），**不会**整段克隆 bootstrap 存档里可能携带的业务噪音分组。
  - `root4/6` 与 `root4/22` 不再从 `save/test.gil` 拷贝（其口径可能与校验成功样本不一致），而是从“内置空存档 base”（`builtin_resources/empty_base_samples/empty_base_with_infra.gil`）提取 canonical 口径做最小补齐。
  - 兼容输入形态：允许调用侧以 `int` 或 `str` 数值键传入 numeric_message（内部统一归一化为 `str(key)`），避免桥接层/不同 dump 路径导致的键类型漂移。
- `id_listing.py`：只读列出 `.gil` 内的元件/实体 ID（诊断/对照用）。
- `name_unwrap.py`：名字字段归一化：将 dump-json 中形如 `"<binary_data> 0A .."` 的“嵌套 message(field_1=string) bytes”解包为可读文本名，避免回填识别/候选列表出现 `<binary_data>` 噪音项（例如 `飞机头`）。
- `template_scanner.py`：只读扫描 `.gil` 内已有元件模板（`template_name -> template_id_int`），供导出中心做“同名模板冲突检查”与策略编排；会对 `<binary_data> 0A ..` 形态的名称做解包（默认 `decode_max_depth=16`，降低大/复杂样本在主进程预扫时卡死/崩溃的风险）。
- `instance_scanner.py`：只读扫描 `.gil` 内已有实体实例（`instance_name -> instance_id_int`），供导出中心做“同名实体冲突检查”与策略编排；会对 `<binary_data> 0A ..` 形态的名称做解包（默认 `decode_max_depth=16`，降低大/复杂样本在主进程预扫时卡死/崩溃的风险）。
- `motioner_group.py`：运动器(Motioner) 组项的识别与补丁（实例段 `root4/5/1[*].7` 追加/修补 `{1:4,2:1,14:{505:1}}`），供 CLI/写回链路复用。
- `ui_layout_scanner.py`：只读扫描 `.gil` 内已有 UI 布局 root（按 `layout_name -> layout_root_guid` 映射），供导出中心/写回链路做“同名布局冲突检查”与策略编排（默认 `decode_max_depth=16`，降低大/复杂样本在主进程预扫时卡死/崩溃的风险）。
- `graph_variable_scanner.py`：扫描 `.gil` 的图变量/布局相关信息（用于写回与诊断）。
- `signal_scanner.py`：只读扫描 `.gil` 的 signal entries（`root4/10/5/3`）与 NodeGraph 内信号节点使用摘要（用于对照/差异定位与格式反推）。
  - 支持构建 `signal_name -> role -> id_int` 的映射（用于对照同名信号在不同 `.gil` 中的 id 是否一致）。
  - 也会输出信号节点 pins(records) 的原始顺序与“是否按 `(kind,index)` 稳定排序”的标记（用于定位 pins 顺序漂移导致的运行时严格校验失败）。
  - signal entries 摘要已包含：`signal_index_int`、以及 send/listen/server 的 `signal_name_port_index_int` 与参数端口索引列表（用于快速对照 `compositePinIndex` 口径与端口号段是否漂移）。
  - 兼容 dump-json 形态：当 `entry['3'](signal_name)` 被保留为 `"<binary_data> ..."`（例如 `prefer_raw_hex_for_utf8=True`）时，会解码回 UTF-8 文本，保证诊断输出/对照逻辑稳定。
- `pipeline.py`：GIL 域内的编排/管线工具（保持薄编排，不承载 UI 逻辑；`--dtype` 默认指向 `ugc_file_tools/builtin_resources/dtype/dtype.json`）。

## 注意事项

- 本目录仅提供 **纯逻辑** 能力：不要在顶层引入 PyQt6。
- fail-fast：结构或资源缺失直接抛错，不使用 try/except 吞错。
- 本文件不记录修改历史，仅保持“目录用途 / 当前状态 / 注意事项”的实时描述。
