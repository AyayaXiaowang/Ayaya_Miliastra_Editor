## 目录用途
存放 UI 相关测试（含 PyQt6 最小构造/冒烟回归）。目标是覆盖 UI 高频改动的关键链路，同时保持不启动主窗口、不依赖真实外设输入。

## 当前状态
- `test_ui_library_pages_smoke.py`：资源库关键页面（元件库/实体摆放/节点图库/存档库）构造与刷新冒烟测试，复用 `tools.smoke_test_ui_libraries` 的同源逻辑。
- `test_two_row_field_table_widget_smoke.py`：`TwoRowFieldTableWidget` 的最小冒烟回归（加载/读回、集合类型展开、只读结构体“查看”按钮信号、metadata raw 值保留）。
- `test_execution_thread_step_event_semantics.py`：执行线程事件语义回归（`step_completed` 仅在最终结果时发射一次，重试/跳过不会导致步骤计数与任务树联动错位）。
- `test_resource_library_auto_refresh_state_machine.py`：资源库文件监控的自动刷新状态机纯逻辑回归（去抖/最大等待、指纹复核触发、刷新互斥、内部写盘抑制（含目录粒度抑制）、周期性指纹复核兜底），不依赖 PyQt6。
- `test_window_close_save_policy.py`：窗口关闭保存策略回归：关闭阶段必须走“flush 去抖缓冲 → 按脏块保存”，禁止无条件全量保存导致外部更新被覆盖。
- `test_save_conflict_policy.py`：保存冲突策略回归：当磁盘文件已被外部修改且提供 expected_mtime 时，保存必须默认拒绝静默覆盖；允许显式开启覆盖策略以对齐 VSCode 的“Overwrite”决策。
- `test_graph_editor_new_node_ports_policy.py`：节点图编辑器“新建节点初始端口策略”的纯逻辑回归，确保“拼装字典”默认生成 `键0/值0`，避免业务特例回流到控制器。
- `test_management_special_panel_selection_single_read.py`：管理模式“专用右侧面板刷新”selection 单次解析回归：确保 coordinator 解析当前选中后不会被专用面板二次反查库页选中，避免协议漂移导致右侧面板静默空白。
- `test_execution_monitor_panel_ui_splitter_no_out_of_range_warning.py`：执行监控面板 UI 组装回归：构造 `log_splitter` 时不应触发 `QSplitter::setCollapsible: Index ... out of range` Qt 警告。
- `test_execution_monitor_log_view_scroll_debounce_smoke.py`：日志视图高频追加冒烟：连续 append 多行并 `processEvents()`，验证 debounce 滚动逻辑可用且不崩溃。

## 注意事项
- 需要创建 `QApplication` 的测试应复用 `QApplication.instance()`，避免多实例导致崩溃。
- 如需 OCR 预热，必须在导入 PyQt6 之前完成（参照 tools 冒烟脚本的顺序），避免 DLL 冲突。
- 不使用 `try/except` 吞错，失败直接抛出由 pytest 记录。


