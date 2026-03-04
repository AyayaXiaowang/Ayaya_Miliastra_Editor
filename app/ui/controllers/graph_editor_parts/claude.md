## 目录用途
将 `app/ui/controllers/graph_editor_controller.py` 的实现按职责拆分为若干 mixin 子模块，避免单文件过大；对外 API 仍以 `GraphEditorController` 为唯一入口。

## 当前状态
- **能力同步**：`capabilities_mixin.py` 负责 `EditSessionCapabilities` 在 controller/view/scene 之间的同步与兼容字段维护。
- **场景缓存**：`scene_cache_mixin.py` 提供 `GraphScene` 运行期 LRU 缓存，加速同进程会话来回切换。
- **自动排版**：`auto_layout_mixin.py` 负责排版前重解析、设置变更重建场景、排版后刷新缓存等编排。
- **加载管线**：`load_pipeline_mixin.py` 负责同步/非阻塞/复合节点子图加载与收尾（状态/镜头/自动排版触发）。
- **保存与校验**：`save_validate_mixin.py` 负责保存/校验/新增节点/自动保存防抖与 dirty 状态派生。
- **会话开关**：`open_session_mixin.py` 负责打开图（编辑/独立）与会话关闭、`scene_extra_options` 等。
- **调试输出**：编辑器会话（打开/加载/保存/排版）相关高频调试输出默认关闭，需通过 `settings.GRAPH_UI_VERBOSE` 显式开启以避免控制台刷屏。

## 注意事项
- mixin 不定义 `__init__`，只提供方法实现；实际依赖由 `GraphEditorController.__init__` 注入/初始化。
- 跨域流程的单一真源仍在 `app/ui/controllers/graph_editor_flow/` 的 service（load/save/validate/auto_layout_prepare 等），本目录只承载 controller 的拆分实现。
- UI 层不写 `try/except` 兜底；错误直接抛出，由上层入口统一处理。

