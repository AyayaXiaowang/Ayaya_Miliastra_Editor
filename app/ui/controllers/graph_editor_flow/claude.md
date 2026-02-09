## 目录用途
`ui/controllers/graph_editor_flow/` 承载“节点图编辑器”的纯流程服务（load/save/validate/auto_layout_prepare）与会话状态机，把跨域链路从 `GraphEditorController` 中拆出去，降低 God Object 体积与多人协作冲突面。

## 当前结构
- `session_state_machine.py`：编辑会话状态机（单一真源），统一派生 `save_status` 与 `EditSessionCapabilities`，避免 controller/view/scene 之间语义分叉
- `load_service.py`：加载管线服务（反序列化 → 复合节点端口同步 → **GraphSemanticPass 对齐语义元数据** → 场景创建/替换 → 批量装配 → 信号端口按需同步 → 小地图修复）；为支持“后台准备 + 主线程增量装配”，load_service 提供 `create_scene_for_load/attach_scene_to_view_for_load/sync_signals_after_load_if_needed` 将“纯场景装配/视图绑定/信号同步”拆分为可复用步骤，便于 controller 在不同加载策略（同步/异步）下复用同一逻辑；同时 `load(..., clear_current_scene=False)` 支持在切图时跳过 `current_scene.clear()`，用于 controller 运行期 GraphScene LRU 缓存复用旧画布。
- `graph_prepare_thread.py`：后台准备线程（GraphPrepareThread），负责节点图加载的“纯模型准备阶段”（GraphModel.deserialize/GraphSemanticPass 等 CPU 密集步骤），产出 `GraphPrepareResult(model, baseline_content_hash)` 供 controller 在主线程创建/装配 scene，避免大图打开时卡死 UI；并向“全局性能监控”记录 `graph.prepare.*` 系列耗时段（含 `graph.prepare.total:<graph_id>`），用于定位模型准备阶段的瓶颈。
- `save_service.py`：保存流程服务（序列化 → ResourceManager.save_resource → 回读确认）
- `validate_service.py`：验证流程服务（ComprehensiveValidator.validate_graph_for_ui，生成 UI 可用 issues 列表）
- `auto_layout_prepare_service.py`：自动排版前准备服务（按需强制重解析：清缓存→从 `.py` 解析→返回 graph_data；缓存写入由资源层统一提供 from_model API）
- `new_node_ports_policy.py`：新建节点“初始端口策略”（纯逻辑、可单测），集中维护节点创建时的业务特例（如“拼装字典”默认键值对端口）

## 注意事项
- 本目录服务不直接发射 Qt 信号；与 UI 的交互/提示由 `GraphEditorController` 统一处理。
- 不在 service 内做 try/except；遇错直接抛出，由上层统一处理。
- 会话能力与保存状态必须走 `session_state_machine`，禁止在 controller/view/scene 复制 bool 字段造成分叉。
- 节点创建的“默认端口/预置值”等业务规则必须集中在本目录的纯逻辑策略中；禁止在 controller/scene/view 内按节点名硬编码 if/else。
- 负责“体验级性能调优”的装配细节也应集中在 load_service：例如在 `fast_preview_mode` 下统一关闭小地图并降低渲染提示成本，避免把这些判断散落到 controller/view/scene 的多处入口。


