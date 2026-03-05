## 目录用途
为 `GraphView` 提供画布内搜索的纯逻辑支持：从 `GraphModel` 构建索引、执行匹配，输出命中节点/连线集合供 overlay 展示与导航。

## 当前状态
- `graph_search_index.py` 构建一次性 `GraphSearchIndex`，支持匹配节点标题/类别/端口、输入常量、代码变量名（`NodeModel.custom_var_names`）、来源文件与行号范围等。
- 支持 **GIA 导出序号**（从 1 开始）的稳定排序索引，可直接输入数字搜索并标注 `GIA序号`。
- `match()` 输出 `GraphSearchMatch`（按视觉顺序的 `node_ids`、需要保留高亮的 `edge_ids_to_keep`、token 与 source span），供灰显/聚焦/导航使用。
- 结果项按需构建：`build_result_item(...)` 在分页渲染时只为当前页生成少量 `GraphSearchResultItem`，避免命中很多节点时一次性分配大量对象。
- 行号过滤为显式语法（例如 `行:75-80` 或 `@xxx.py (75-80)`）；纯数字默认仍按文本匹配（用于 `GIA序号` 等字段）。

## 注意事项
- 本目录不依赖 PyQt，仅依赖 `engine.graph.models`；避免引入文件系统访问。
- 性能敏感路径不要在每次输入时重建索引；源码片段读取与裁剪由 UI（`GraphSearchOverlay`）负责。
- 匹配默认使用 `casefold()` 做大小写无关比较，语义变更需同步更新 UI 的命中标签说明。

