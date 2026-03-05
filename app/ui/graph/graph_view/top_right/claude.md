## 目录用途
管理 `GraphView` 右上角的浮动控件，包括自动排版按钮以及可注入的额外操作按钮（如预览页的“编辑”）。

## 当前状态
- `controls_manager.py` 提供 `ensure_auto_layout_button/ensure_search_button/update_position/set_extra_button/raise_all` 等静态方法，负责按钮创建、定位与层级维护。
- 右上角控件现在支持两层：
  - Host 级主按钮：通过 `set_extra_button()` 设置（例如 TODO 预览的“编辑”、编辑器的“前往执行”）。
  - 插件扩展按钮：通过 `add_extension_widget()` 追加（位于主按钮与“自动排版”之间），并支持 `set_extension_widgets_visible()` 统一切换可见性（用于共享画布在预览场景隐藏扩展入口）。
- 按钮样式与交互在此集中定义，`GraphView` 仅在初始化和 resize 时调用接口，复用同一套体验。
- 默认常驻一个“🔍 搜索”按钮，用于在不记快捷键时也能手动打开画布内搜索栏（等价于 Ctrl+F）。

## 注意事项
- 额外按钮必须以 `GraphView` 为父控件，避免层级错乱；管理器会自动调用 `raise_()` 保证置顶。
- 当视图尺寸发生变化或 `extra_top_right_button` 可见性改变时，请再次调用 `update_position`，否则按钮可能漂移。
- 按钮的点击逻辑应在外部连接（GraphView、控制器或面板），本目录不绑定业务行为，保持可复用性。
- 浮动按钮配色使用 `GraphPalette`（节点图画布固定深色调色板），保证在画布背景上始终有足够对比度。
 - 插件扩展控件属于可选能力：当共享画布被 TODO 预览借用时，应整体隐藏扩展控件以避免“预览页出现不相关入口”。

