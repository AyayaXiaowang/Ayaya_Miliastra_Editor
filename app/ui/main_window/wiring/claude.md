## 目录用途
主窗口信号装配/连线（wiring）集中层：将各页面/面板对外信号绑定到主窗口回调或 `NavigationCoordinator.handle_request(UiNavigationRequest)`，避免连线散落在 `ui_setup_mixin.py`。

## 当前状态
- 控件实例化仍由 `ui_setup_mixin.py` 负责；本目录提供 binder 函数集中完成信号连接与导航请求构造/转发。
- 覆盖页面级 binder（Todo/验证/图库/存档库/管理页等）与右侧面板 binder（属性/战斗详情/管理编辑/验证详情等）。
- 右侧 tab 注册矩阵已收敛到 `ui/main_window/features/RightPanelAssemblyFeature`，wiring 只负责连线与转发。

## 注意事项
- 本目录只做“连线”，不承载业务编排；复杂流程下沉到 `app.models` 或专用 controller/service。
- 导航请求必须通过 `app.models.UiNavigationRequest` 的工厂方法构造，避免手写字符串组合造成语义漂移。
- Todo 预览的“跳转到图元素”来自全局 `app_state.graph_view.jump_to_graph_element`；binder 侧需按 `ViewMode.TODO` 做门禁，避免编辑器事件串入。

