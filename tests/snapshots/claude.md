## 目录用途
存放“可回归 / 可 diff”的测试快照产物（由工具生成，提交进仓库作为 baseline）。

## 当前状态
- `node_library_manifest.json`：节点库 NodeDef 的稳定序列化快照（manifest_version 随 schema 演进），由内部生成流程生成与更新，用于检测节点端口/类型/约束/端口别名（port_aliases）/语义标识（semantic_id）等变化。
- baseline 在运行期作用域 `active_package_id=None`（仅共享根）下生成；项目存档私有的复合节点不进入 baseline，以避免跨项目冲突导致 CI 漂移。

## 注意事项
- 快照文件禁止手工编辑；必须通过生成流程生成/更新，保证排序与格式稳定。
- 当节点库发生结构性变更（新增/删除节点、端口/类型/约束/别名/semantic_id 等）时，应同步更新 baseline 并提交，以保持 CI/本地护栏对齐。
- 本目录仅存放 baseline 快照；诊断报告请放 `docs/diagnostics/`。


