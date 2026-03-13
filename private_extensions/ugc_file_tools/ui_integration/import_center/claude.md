## 目录用途
- `ugc_file_tools` 的“导入中心”实现：将 `.gil/.gia` 导入能力收敛到统一的三步式对话框（选择与配置 / 预览分析 / 执行+进度+日志）。
- 本目录仅负责 UI 编排与执行进度展示；底层导入逻辑复用 `ugc_file_tools/pipelines/*`。

## 当前状态
- 支持三类导入任务（均在同一对话框内完成配置与执行）：
  - `.gil` 整包导入为项目存档（可选生成 Graph Code 与导入后校验）
  - `.gil` 选择性导入（步骤2内分析节点图清单并勾选导入范围）
  - `.gia` 导入到项目存档（bundle/player_template/node_graphs）
- 对话框创建与基础 UI 样板复用 `ui_integration/center_dialog_scaffold.py`（单例唤起、尺寸自适配、标题栏、tabs 容器），导入中心仅关注三步页内容与执行编排。
- 执行页固定展示：进度条 + 当前步骤标签 + 日志尾部 + 结果摘要；失败时在执行页直接展示错误（不要求用户去看控制台）。
- 任务历史复用 `ui_integration/export_history.py`（同一份“最近任务”列表包含导入/导出条目）。
- 兼容入口：`ui_integration/read_gil.py` / `read_gil_selected.py` / `read_gia.py` 默认跳转到本导入中心并预选任务类型。

## 注意事项
- 避免在模块顶层导入 PyQt6；尽量在入口函数内延迟导入以降低插件加载开销。
- 保持 fail-fast：不吞异常；但需要把异常内容以可复制文本展示在执行页，保证失败可见且可追溯。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

