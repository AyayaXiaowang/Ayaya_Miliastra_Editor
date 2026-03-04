## 目录用途
`ui/controllers/graph_editor_flow/` 承载“节点图编辑器”的流程服务（load/save/validate/auto_layout_prepare）与会话状态机，把跨域链路从 `GraphEditorController` 中拆出去，降低耦合与单文件体积。

## 当前状态
- **会话状态机**：`session_state_machine.py` 作为单一真源，统一派生 `save_status` 与 `EditSessionCapabilities`，避免 controller/view/scene 之间语义分叉。
- **加载服务**：`load_service.py` 负责反序列化、复合节点端口同步、`GraphSemanticPass` 语义对齐、场景创建/替换与收尾；支持 `clear_current_scene=False` 以配合 controller 的 GraphScene LRU 复用。
- **后台准备**：`graph_prepare_thread.py`（`GraphPrepareThread`）负责 CPU 密集的模型准备（deserialize/semantic 等），产出可在主线程装配 scene 的结果，避免大图打开卡 UI。
- **保存/校验**：`save_service.py`（序列化 → `ResourceManager.save_resource` → 回读确认）、`validate_service.py`（`ComprehensiveValidator.validate_graph_for_ui` 产出 UI 可用 issues）。
- **排版前准备**：`auto_layout_prepare_service.py` 按需清缓存并从 `.py` 重新解析生成 `graph_data`。
- **新建节点端口策略**：`new_node_ports_policy.py` 维护节点创建时的默认端口/预置值规则（纯逻辑、可单测）。
- **复合节点子图端口刷新**：复合节点子图（`load_graph_for_composite`）装配完成后，会对端口执行一次 refresh（`GraphScene._refresh_all_ports`），用于更新“虚拟引脚暴露角标/tooltip”依赖的缓存，保证复合节点库预览画布可见。

## 注意事项
- 本目录服务不直接发射 Qt 信号；与 UI 的交互/提示由 `GraphEditorController` 统一处理。
- 不在 service 内做 `try/except` 吞错；遇错直接抛出，由上层统一处理。
- 会话能力与保存状态必须走 `session_state_machine`；禁止在 controller/view/scene 复制 bool 字段造成分叉。
- 节点创建的默认端口/预置值等业务规则必须集中在本目录策略中；不要在 controller/scene/view 按节点名硬编码 if/else。

