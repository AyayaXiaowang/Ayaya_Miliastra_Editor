## 目录用途
`ui/panels/ui/` 存放“界面控件组（UI Control Groups）/UI 工作台”相关的右侧面板与支撑模块：包含控件组管理器、CRUD/Store、模板树、预览渲染与布局/模板配置面板等。

## 当前状态
- `ui_control_settings_panel.py` 为主入口面板，对接管理模式的“界面控件组” section，并向上游发出选择/变更事件。
- 预览与渲染逻辑集中在 `ui_control_group_preview*.py` 与 `ui_control_group_template_helpers.py`，避免在面板类中混入大量纯逻辑工具函数。
- 数据访问通过 `UIControlGroupStore/UIControlGroupManager` 收敛，尽量保持面板侧为“显示 + 触发操作请求”。

## 注意事项
- 面板仅负责 UI 与交互，不在此目录散落写盘细节；需要写回时通过上层统一入口或 service 层执行。
- 不使用 `try/except` 吞异常；异常直接抛出，便于在测试与运行期定位。

