## 目录用途
`app/ui/graph/`：节点图编辑器 UI 子包（PyQt6）。包含 `GraphScene/GraphView`、图形项、撤销栈、节点图库与通用库页脚手架等；只负责呈现与交互，资源持久化委托 `engine/resources` 与上层控制器。

## 当前状态
- **画布核心**：`GraphView`（`app.ui.graph.graph_view` 门面）+ `GraphScene` 负责缩放/平移/搜索/自动排版与只读预览；画布可在不同页面之间复用（如 TODO 预览）。
- **图元与样式**：节点/端口/连线图元位于 `items/`；画布调色板与内联控件样式集中管理，保证画布外观稳定。
- **只读能力**：通过 `EditSessionCapabilities` 收敛“可编辑/可校验/可落盘”能力；只读场景允许校验/自动排版但不写盘。
- **性能策略**：超大图加载采用增量装配（time-budget）；渲染侧支持 LOD、常量控件虚拟化、批量边层等策略，组合判定下沉到 `app.runtime.services.graph_scene_policy`。
- **调试叠加**：布局 YDebug 等调试叠加依赖的 `_layout_y_debug_info` 缓存在场景加载/重建阶段准备，叠加层只读消费，避免在绘制路径做重计算；布局层流程语义以端口类型真源驱动，不再依赖“临时端口改名”补丁。
- **NodeDef 真源**：UI 侧解析 NodeDef 以 `NodeModel.node_def_ref` 为唯一真源；除 `kind="event"` 的确定性 `category/title -> builtin_key` 映射兼容规则外，禁止 `title/category/#scope` 猜测式 fallback；语义绑定由 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成。

## 注意事项
- UI 不直接 `open()` 读写资源；图/资源加载通过 `ResourceManager`、runtime services 与控制器。
- 不使用 try/except 吞错；错误直接抛出，由上层统一处理/展示。
- 新增交互/性能策略优先下沉到 service/policy，避免在 Qt 事件回调里堆业务分支。
