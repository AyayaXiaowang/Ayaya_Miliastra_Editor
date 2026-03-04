## 目录用途
`app/ui/graph/graph_view/` 是节点图画布的视图层（`GraphView`）及其子模块：将缩放/平移/聚焦、叠层（小地图/标尺/搜索/性能/加载遮罩）、右上角控件与上下文菜单等逻辑从主类中拆分出来，保持 `GraphView` 作为稳定门面。

## 当前状态
- **稳定导入**：外部统一 `from app.ui.graph.graph_view import GraphView`；实现位于 `graph_view_impl.py`。
- **共享画布租约**：`shared_graph_view_lease.py` 的 `SharedGraphViewLeaseManager` 管理全局唯一 `app_state.graph_view` 在编辑器与 TODO 预览之间的借还/能力切换，并在借还时恢复视图状态快照（缩放/镜头中心），带极小缩放保护。
- **交互与导航**：`controllers/` 处理键鼠事件与交互状态；`navigation/` 提供 `fit_all/focus_on_node/...` 等聚焦能力；`highlight/` 负责高亮/灰显。
- **叠层与弹窗**：`overlays/` 提供小地图、标尺、画布搜索、性能面板、加载遮罩与平移/缩放冻结等 overlay；`popups/` 提供“添加节点”菜单等非模态浮层。
- **装配与扩展点**：`assembly/` 负责场景附加与 resize 联动；`top_right/` 统一管理右上角按钮（自动排版/搜索/额外按钮）；`auto_layout/` 封装“校验→布局→差异合并→重建连线”流程。

## 注意事项
- 保持 `GraphView` 公开 API/信号签名稳定；子模块只做委托实现，不对外暴露私有钩子。
- overlay/控制器不直接写盘、不绕过 `GraphScene` 命令修改模型；需要改模型必须走场景命令/控制器。
- 为避免循环依赖，类型标注使用 `TYPE_CHECKING`，运行期导入尽量局部化；不使用 try/except 吞错，错误直接抛出。
