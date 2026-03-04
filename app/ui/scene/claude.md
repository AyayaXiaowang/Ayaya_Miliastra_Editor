## 目录用途
`app/ui/scene/`：`GraphScene` 的交互/管理职责拆分层。通过一组 mixin（交互、对象管理、Y 调试、视图右键菜单桥接等）把复杂 UI 逻辑从场景主类中拆出来，便于维护与复用。

## 当前状态
- **交互**：`interaction_mixin.py` 的 `SceneInteractionMixin` 处理端口拖拽连线、自动连线、端口高亮与节点拖拽；连线可连性同时考虑端口类型与 `NodeDef` 的泛型约束。
- **对象管理**：`model_ops_mixin.py` 的 `SceneModelOpsMixin` 管理 add/remove 图元、copy/paste/delete、高亮与验证刷新，并与 fast preview/批量边层兼容。
- **布局 Y 调试**：`ydebug_interaction_mixin.py` 的 `YDebugInteractionMixin` 负责装配与转发调试 tooltip/链路高亮等能力（展示与状态由对应 overlay/manager 承担）；`tooltip_overlay.py` 的调试卡片会展示节点的源码位置（`GraphModel.metadata["source_file"]` + `NodeModel.source_lineno/source_end_lineno`）用于快速定位到代码行。
- **右键菜单桥接**：`view_context_menu_mixin.py` 的 `SceneViewContextMenuMixin.handle_view_context_menu(...)` 作为 `GraphView` 显式委托入口，统一处理命中类型并为“空白处添加节点”等行为提供稳定协作接口。
- **薄主类**：`GraphScene` 主文件保持为薄层（初始化、NodeDef 解析入口、`add_node_item`、虚拟引脚清理等），复杂分支下沉到 mixin/服务。

## 注意事项
- mixin 只假设宿主提供必要属性（model/node_items/edge_items/...），避免互相强耦合；类型标注用 `TYPE_CHECKING`，运行期导入尽量局部化以防循环。
- 撤销/重做统一走 UI 命令与 `UndoRedoManager`；引擎层仅保留纯模型命令，不让 `GraphScene` 直接穿透到引擎内部。
- Qt 生命周期坑：`QGraphicsScene.clear()` 会删除底层 C++ 图元；清空/重载时必须先清理 Python 侧索引容器与高亮状态，避免后续回调触发 `wrapped C/C++ object ... has been deleted`。
