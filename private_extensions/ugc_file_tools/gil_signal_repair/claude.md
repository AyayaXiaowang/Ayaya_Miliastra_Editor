# ugc_file_tools/gil_signal_repair 目录说明

## 目录用途
- 收口“`.gil` 信号损坏修复”的可复用实现模块（wire-level 最小补丁），供 `commands/repair_gil_signals_from_*` 等入口脚本与测试复用。

## 当前状态
- `from_imported_gia.py`：核心实现（按 `.gia` 选中节点图提取到的信号名作为 scope），对目标 `.gil` 执行：
  - 去重 signal entries（优先按 `signal_index` 合并，必要时按 `signal_name` 合并；遇到冲突保守跳过）
  - 生成 node_def id remap 并修补节点图内引用
  - 同步修补 node_def 内信号名与“运行时 META pin(kind=5)”上的信号名（不触碰参数 pin(kind=3) 常量）
  - 修补缺失的 param definition `field_6(send_to_server_port_index)`（按 `field_5 + 1` 推断）
  - 可选清理 placeholder 信号的 orphan node_defs（仅在本次 scope 覆盖所有非占位符信号名时允许）
  - 对外提供公开 API（无下划线）：`repair_gil_signals_from_imported_gia` / `plan_dedupe_by_signal_index` / `SignalEntryInfo`，供 `commands/` wrapper 稳定导入，避免跨模块私有依赖。
- `merge_signal_entries.py`：显式指定 keep/remove 信号名的 wire-level 合并工具：
  - 删除 remove entry + 其 node_defs（send/listen/server）
  - keep entry 可选重命名为新名字（常用于“占位符 → 正式名”）
  - remap 节点图内信号节点的 node_def ids，并按 keep entry 的端口索引修补 `compositePinIndex`（避免端口解释错位）
  - 对外提供公开 API（无下划线）：`merge_gil_signal_entries`（CLI：`ugc_file_tools tool --dangerous merge_gil_signal_entries ...`）。

## 注意事项
- fail-fast：不使用 try/except；结构不符合预期直接抛错，避免静默写坏存档。
- scoped处理：只处理“所选 `.gia` 中出现且目标 `.gil` 内存在/可唯一映射”的信号名；无法唯一确定时拒绝猜测。
- 字节保真：修复以 wire chunk 为单位进行，尽量减少无关字段重编码带来的漂移风险。
- 对外 public symbol（例如 `SignalEntryInfo`）的声明必须避免 import-time 依赖未定义的私有实现名（按“先定义，再 alias”）。

