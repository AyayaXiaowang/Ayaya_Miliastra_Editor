## 目录用途
应用层的“模型与纯逻辑编排”：提供与界面流程相关的数据结构与算法（任务清单生成、导航请求、视图模式配置等），不依赖 PyQt，可在非 GUI 环境复用。

## 当前状态
- 任务清单：`TodoItem`、`TodoGenerator`、`todo_detail_info_schema`（detail_info 约束单一真源）、`todo_graph_tasks/`（节点图任务细分）。
- UI 协作模型：`view_modes.py`（视图模式/右侧面板配置）、`ui_navigation.py`（导航意图数据模型）、`edit_session_capabilities.py`（只读/可交互/可保存/可校验语义）。
- `NodeTypeHelper.get_node_def_for_model(...)` 以 `node_def_ref` 为真源；对 `kind="event"` 采用确定性的 `category/title -> builtin_key` 映射定位 NodeDef（用于端口类型推断/判定），不做 title 猜测式 fallback。

## 注意事项
- 依赖方向必须单向：`app.ui -> app.models`；禁止 `app.models` 引入任何 `PyQt6` 或 UI 组件。
- 保持 fail-fast：数据缺失/结构不符直接抛错，避免静默回退导致 UI 状态分叉。
- 面向大图的生成/遍历避免 O(n^2) 退化（例如队列遍历不要用 `list.pop(0)`）。

