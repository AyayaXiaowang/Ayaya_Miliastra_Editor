# 节点图视图子模块

## 目录用途
围绕 `GraphView` 将节点图视图相关的动画、叠层、小地图、导航、高亮、上下文菜单等逻辑拆分为独立子模块，提升可维护性与复用性。

## 当前状态
- 外部统一通过 `from app.ui.graph.graph_view import GraphView` 获取 `GraphView`，所有公开方法签名保持不变。
- `GraphView` 的实现位于 `app/ui/graph/graph_view_impl.py`；本目录下的 `animation/`、`overlays/`、`controllers/` 等子模块承载具体行为实现。
- 共享画布租约：`shared_graph_view_lease.py` 提供 `SharedGraphViewLeaseManager`，集中管理全局唯一 `app_state.graph_view` 在 TODO 预览与编辑器之间的借还、只读/可编辑能力切换与右上角按钮/联动开关同步；并维护“视图状态快照”（缩放/镜头中心）在借还时恢复，避免预览侧 `fit_all` 等聚焦操作把编辑器画布带入“压缩状态”。
  - 共享画布在缺失编辑器视图快照时会进行“极小缩放保护”：当缩放小于 10%（0.10）会重置变换，避免回到编辑器后仍处于过度压缩导致难以操作的状态。

## 子模块结构

### animation/ - 视图动画模块
- `view_transform_animation.py`：平滑过渡视图缩放与位置的动画辅助类
  - 使用定时器驱动 60fps 动画
  - 支持三次缓动函数（ease-in-out cubic）
  - 可配置持续时间、最大缩放、边距系数

### overlays/ - 视图叠层模块
- `minimap_widget.py`：小地图组件，显示整个节点图的缩略视图
  - 支持拖拽跳转、场景边界动态更新
  - 渲染缓存与节流（100ms 合并），避免频繁重绘
  - 实时叠加当前视口矩形指示
- `ruler_overlay_painter.py`：标尺叠层绘制器（静态方法）
  - 绘制顶部 X 轴与左侧 Y 轴坐标刻度
  - 根据缩放动态合并刻度间隔，避免标签重叠
  - 在视图坐标系绘制，不受场景缩放影响

### popups/ - 弹出窗口模块
- `add_node_popup.py`：添加节点的浮动菜单（非模态）
  - 支持搜索过滤、作用域过滤（server/client/通用节点）、端口类型兼容性过滤
  - 按类别分组展示（事件/执行/查询/运算/流程控制/复合节点），默认折叠分组，搜索时自动展开包含匹配项的分组
  - 回车快速添加、Esc 关闭、失焦自动关闭

### controllers/ - 交互控制器模块（步骤2完成）
- `interaction_controller.py`：图视图交互控制器
  - 管理所有键盘鼠标事件（滚轮/按键/点击/拖拽/双击）
  - 交互状态管理（拖拽平移/空格手抓/框选）
  - 帧设置优化（交互期间临时提升更新模式避免残影）
  - 背景失效与缓存管理（确保网格与标尺对齐）
  - 布局Y调试图标点击拦截

### navigation/ - 视口导航模块（步骤2完成）
- `viewport_navigator.py`：视口导航器
  - 居中到节点（center_on_node）
  - 适应全部内容（fit_all）
  - 聚焦单个节点（focus_on_node）
  - 聚焦两个节点与连线（focus_on_nodes_and_edge）
  - 执行矩形聚焦（execute_focus_on_rect，支持动画与无动画模式）

### highlight/ - 高亮服务模块（步骤2完成）
- `highlight_service.py`：高亮服务
  - 高亮节点/连线/端口（单个或批量）
  - 清除所有高亮
  - 灰显非焦点元素（dim_unrelated_items）
  - 恢复所有元素透明度（restore_all_opacity）

### context/ - 上下文菜单桥接模块（步骤2完成）
- `add_node_menu_bridge.py`：添加节点菜单桥接
  - 封装右键空白处添加节点菜单的显示逻辑
  - 管理菜单实例生命周期与自动连接回调

### top_right/ - 右上角控件管理模块（步骤3完成）
- `controls_manager.py`：右上角控件管理器
  - 确保并配置自动排版按钮
  - 确保并配置“🔍 搜索”按钮（打开画布内搜索栏）
  - 管理额外自定义按钮（如预览页的"编辑"按钮）
  - 支持插件扩展控件列表（位于主按钮与“自动排版”之间），并提供统一隐藏/显示入口，配合共享画布在 TODO 预览场景隐藏扩展入口
  - 统一更新按钮位置（右对齐，间距管理）
  - 提升所有控件到最上层
  - 按钮配色与禁用态使用 `GraphPalette`（画布固定深色调色板），保证在画布上有稳定对比度

### auto_layout/ - 自动排版控制器模块（步骤3完成）
- `auto_layout_controller.py`：自动排版控制器
  - 排版前回调（可选重载模型）
  - 节点图验证（含虚拟引脚映射）
  - 克隆模型并执行就地布局
  - 差异合并（新增/删除节点与连线）
  - 同步坐标与基本块、布局 Y 调试信息
  - 基于最新模型重建所有连线图形项，保证 UI 与模型状态一致
  - 更新图形项与场景
  - 排版完成回调

### assembly/ - 视图装配模块（步骤3完成）
- `view_assembly.py`：视图装配器
  - 场景附加（attach_scene：设置场景矩形、创建 overlay 管理器与小地图）
  - 窗口调整响应（on_resize：联动小地图/overlay/按钮定位）
  - 小地图位置更新（update_mini_map_position）

## 保留在原文件的内容
`ui/graph_view.py` 保留 `GraphView` 类薄层（约 290 行）：
- 构造器（初始化基础属性与子模块控制器）
- 事件方法委托（wheelEvent/mousePressEvent/keyPressEvent 等）
- 公开 API 方法委托（聚焦/高亮/导航/装配）
- 绘制事件与显示事件（委托标尺绘制器与装配器）
- 右键菜单入口（只做只读/拖动判定，并将事件委托给场景的 `handle_view_context_menu` 接口；端口自身的菜单仍由 Qt 标准分发触发）
- “添加节点”菜单入口对场景侧暴露为 `GraphView.show_add_node_menu(...)`（公开方法），场景/交互逻辑不再通过 `hasattr(view, "_show_add_node_menu")` 这类私有钩子探测协作。

## 迁移与集成方式
- **委托模式**：`GraphView` 事件方法保留 PyQt 重载签名，内部委托给控制器
- **静态方法调用**：导航器、高亮服务、装配器等使用静态方法，传入 `view` 实例
- **组合关系**：`GraphView` 持有 `InteractionController` 实例，直接调用其方法
- **导入路径**：所有子模块从 `app.ui.graph.graph_view.xxx` 导入，保持模块化

## 委托关系总结
| GraphView 方法 | 委托目标 | 说明 |
|---|---|---|
| wheelEvent | InteractionController.handle_wheel | 滚轮缩放与 Tooltip 避让 |
| mousePressEvent | InteractionController.handle_mouse_press | 拖拽/框选/Y调试点击 |
| mouseReleaseEvent | InteractionController.handle_mouse_release | 拖拽结束/帧设置恢复 |
| mouseDoubleClickEvent | InteractionController.handle_mouse_double_click | 双击跳转 |
| keyPressEvent | InteractionController.handle_key_press | 快捷键（删除/撤销/复制等） |
| keyReleaseEvent | InteractionController.handle_key_release | 空格释放 |
| scrollContentsBy | InteractionController.handle_scroll_contents | 滚动联动 |
| contextMenuEvent | Scene.handle_view_context_menu（若实现）/Qt 默认分发 | 右键菜单入口（场景决定节点/连线/空白处行为，端口仍走自身 contextMenuEvent） |
| center_on_node | ViewportNavigator.center_on_node | 居中到节点 |
| fit_all | ViewportNavigator.fit_all | 适应全部 |
| focus_on_node | ViewportNavigator.focus_on_node | 聚焦节点 |
| focus_on_nodes_and_edge | ViewportNavigator.focus_on_nodes_and_edge | 聚焦两节点与边 |
| highlight_* | HighlightService.* | 高亮节点/边/端口 |
| dim_unrelated_items | HighlightService.dim_unrelated_items | 灰显 |
| restore_all_opacity | HighlightService.restore_all_opacity | 恢复透明度 |
| setScene | ViewAssembly.attach_scene | 场景附加 |
| resizeEvent | ViewAssembly.on_resize | 窗口调整 |
| set_extra_top_right_button | TopRightControlsManager.set_extra_button | 设置额外按钮 |
| _on_auto_layout_clicked | AutoLayoutController.run | 自动排版 |

## 注意事项
- 保持信号与回调接口不变，确保与控制器、主窗口的耦合点稳定
- 子模块使用 `TYPE_CHECKING` 避免循环导入（标注类型而不实际导入）
- 事件方法保留 PyQt 重载签名，仅内部委托，避免事件分发失效
- 小地图与动画组件保持对 `GraphView` 的弱引用（传入视图实例，调用公开方法）
- 拆分前后视觉表现与交互行为完全一致（已验证：启动/缩放/拖拽/菜单/小地图/自动排版）
- **拖拽模式（动态切换）**：
  * 默认 `NoDrag` 模式
  * 左键点击节点/端口时 → 保持 `NoDrag`，允许拖拽节点或创建连线
  * 左键点击空白处时 → 切换为 `RubberBandDrag`，允许框选多个节点
  * 右键/中键/空格+左键时 → 切换为 `ScrollHandDrag`，实现画布平移
  * 释放后恢复为 `NoDrag`
- **调试语句清理**：已移除 View 和交互控制器中的布局 Y 调试 print 语句，保持日志输出简洁
 - 共享画布在 TODO 预览与编辑器之间借还时，除切换主按钮外，还应统一隐藏/恢复插件扩展控件，避免预览页出现“导出/写盘”等不相关入口。

## 性能与维护优势
- **职责分离**：每个子模块专注单一职责，便于测试与维护
- **代码复用**：导航器/高亮服务可供其他视图复用
- **降低耦合**：控制器与服务层不依赖 `GraphView` 实现细节
- **易于扩展**：新增交互/导航逻辑只需修改对应子模块
