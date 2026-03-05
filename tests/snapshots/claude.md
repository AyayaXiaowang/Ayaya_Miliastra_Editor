## 目录用途
存放“可回归 / 可 diff”的测试快照产物（由工具生成，提交进仓库作为 baseline）。

## 当前状态
- `node_library_manifest.json`：节点库 NodeDef 的稳定序列化快照（manifest_version 随 schema 演进），由内部生成流程生成与更新，用于检测节点端口/类型/约束/端口别名（port_aliases）/语义标识（semantic_id）等变化。
- `node_library_manifest.json` 的 baseline 在运行期作用域 `active_package_id=None`（仅共享根）下生成；项目存档私有的复合节点不进入该 baseline，以避免跨项目冲突导致 CI 漂移。
- `gia_export_asset_bundle_golden__*.json`：节点图 `.gia` 导出金样快照（AssetBundle message 结构 + sha256），用于在重构导出链路时锁定行为。
  - golden 用例会按 case 推断并注入 `active_package_id`，并通过 `ResourceManager.rebuild_index()` + 清理导出侧全局缓存确保复合节点依赖与序列化顺序稳定。
  - 生成/更新：`$env:UPDATE_GIA_EXPORT_GOLDEN_SNAPSHOTS='1'; pytest -q tests\\tooling\\test_gia_export_asset_bundle_golden_snapshot.py::test_gia_export_asset_bundle_golden_snapshots`
- `gil_writeback_roundtrip_golden__*.json`：节点图 `.gil` 写回 roundtrip 金样快照（GraphModel(JSON) → `.gil` pure-json 写回 → payload 直读 Graph IR）。
  - 用例会同时覆盖 `prefer_signal_specific_type_id={False,True}` 两种策略差异，避免行为靠“样本碰巧”稳定。
  - 信号节点 type_id 口径对齐 after_game：当命中 signal-specific 时使用 0x4000xxxx/0x4080xxxx（不再 OR 成 0x6000xxxx）。
  - Graph IR 的 pins(records) 顺序作为结构快照的一部分：写回侧会统一按 `(kind,index)` 稳定排序，避免顺序漂移；golden 会锁住该约束。
  - 生成/更新：`$env:UPDATE_GIL_WRITEBACK_GOLDEN_SNAPSHOTS='1'; pytest -q tests\\ugc_file_tools\\test_gil_writeback_roundtrip_golden_snapshot.py::test_gil_writeback_roundtrip_golden_snapshots`

## 注意事项
- 快照文件禁止手工编辑；必须通过生成流程生成/更新，保证排序与格式稳定。
- 当节点库发生结构性变更（新增/删除节点、端口/类型/约束/别名/semantic_id 等）时，应同步更新 baseline 并提交，以保持 CI/本地护栏对齐。
- `gia_export_asset_bundle_golden__*.json` 会锁定共享语义层（`node_graph_semantics.type_binding_plan` / `contracts.node_graph_type_mappings`）对 concrete/indexOfConcrete 的决策（含字典 K/V 查询节点的输出端口 indexOfConcrete）；当这些规则演进时，需要按生成流程更新快照。
- 本目录仅存放 baseline 快照；诊断报告请放 `docs/diagnostics/`。


