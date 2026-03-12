## 目录用途
- `analysis_center/`：ugc_file_tools 的**分析中心**（三步式 UI）：选择范围 → 搜索/结果 → 构建索引（进度/日志/失败清单）。
- 面向“静态引用/使用”分析：节点（builtin/event）、复合节点（composite_id）、信号名（静态绑定口径），输出“在哪些节点图中使用”。

## 当前状态
- 索引构建以**节点图源码文件**为入口：步骤1复用导出中心的 `resource_picker.py` 资源树（仅展示 `节点图/*.py`），支持“勾选扫描子集；留空=扫描该范围内全部节点图”，并提取 docstring 元数据拿到 `graph_id`。
- 索引数据优先复用磁盘 `graph_cache`：读取 `app/runtime/cache/graph_cache/<graph_id>.json` 的 `result_data["data"]`，并校验 `file_hash/node_defs_fp` 一致性；未命中或不兼容会尝试后台解析生成缓存，失败进入失败清单。
- 搜索 UI 支持按类型（自动/节点/复合节点/信号/占位符）过滤，并返回每图命中次数与相对路径/graph_id。
- 占位符搜索覆盖：`ui_key` / `entity_key` / `component_key`（扫描节点图源码的字符串字面量，口径与导出中心一致）。
- usage index 支持磁盘缓存：`app/runtime/cache/ugc_file_tools/analysis_center/`；构建时 UI 会明确显示“缓存命中/未命中”与缓存路径（不静默使用旧索引）。
- 对话框创建与基础 UI 样板复用 `ui_integration/center_dialog_scaffold.py`（单例唤起、尺寸自适配、标题栏、tabs 容器），分析中心仅关注范围/搜索/索引任务编排。
- 任务历史复用 `export_history.py`：索引构建完成/失败会写入历史，便于复盘。

## 注意事项
- 不切换全局 `active_package_id`：避免影响主程序的资源作用域与 schema 缓存。
- 不吞错：单图解析/缓存不兼容会明确记录到失败清单；UI 提供可复制的错误文本。
- 本目录只负责 UI 与索引构建编排；信号口径复用 `ugc_file_tools.node_graph_semantics.signal_usage` 的公开函数。

