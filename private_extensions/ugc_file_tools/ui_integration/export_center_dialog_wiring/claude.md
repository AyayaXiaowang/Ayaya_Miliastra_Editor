# export_center_dialog_wiring 目录说明

## 目录用途

- 承载“导出中心”对话框的 **UI wiring/联动实现**（信号连接、状态同步、预览刷新、步骤导航、回填识别交互、执行页进度与结果展示）。
- 对外入口仍由 `ui_integration/export_center_dialog_controller.py` 提供，本目录仅用于拆分实现以降低单文件体积与耦合度。

## 当前状态

- **统一实现入口**：`wire.py` 提供 `wire_export_center_dialog(...)`，签名与外部入口保持一致。
- **环境与依赖注入**：通过 `env.py` 收口对话框控件引用与运行态 `rt`，避免在模块顶层导入 PyQt6。
- **模块拆分**：
  - `basic_sync.py`：基础开关联动（打包/写回 UI 等）与通用同步函数
  - `format_ui.py`：格式切换（GIA/GIL/修复/合并）对 UI 页面的裁剪、文案与联动触发
  - `ui_export_record.py`：UI 导出记录选项与详情刷新
  - `analysis_tab.py`：回填分析页（依赖清单、识别目标、表格渲染、双击缺失项覆盖）
  - `preview.py`：步骤3“执行计划预览”与左侧“已选资源”摘要（含 UI/资源→自定义变量联动）
  - `execute_tab.py`：执行页进度、日志、结果文本与启动导出 action（失败时写入可复制的复现信息文本）
  - `failure_repro.py`：导出失败复现信息快照构建与格式化（可选项/已选项/plan/CLI 模板）
  - `repair_sync.py`：修复/合并信号模式下输出路径默认值同步
  - `step_nav.py`：步骤 tabs + footer 导航逻辑

## 注意事项

- 避免在模块顶层导入重型依赖（尤其 PyQt6）；Qt 相关对象通过参数注入。
- 保持 fail-fast：不吞异常；UI 联动中的“程序化勾选”需保持原有的 re-entrancy 规避策略。
- 不要改变对外行为与交互口径；拆分以等价重构为主。

