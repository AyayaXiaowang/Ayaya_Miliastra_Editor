# 节点图画布搜索子模块（graph_view/search）

## 目录用途
为 `GraphView` 提供**画布内搜索**的纯逻辑支持：构建搜索索引、执行匹配、输出命中节点/连线集合。

## 当前状态
- `graph_search_index.py`：从 `GraphModel` 构建一次性索引，支持按查询词匹配：
  - 节点标题/类别/端口名
  - **GIA 导出序号（从 1 开始）**：按导出口径的稳定排序计算并纳入索引，可直接用数字搜索并在命中标签中标为 `GIA序号`
  - 输入常量（端口输入框内容）
  - 代码变量名（`NodeModel.custom_var_names`），并可扩展为“变量定义→下游使用节点”的关联命中
  - 图来源文件（`GraphModel.metadata["source_file"]`），用于匹配形如 `@xxx.py` 的引用字符串，并支持 `@xxx.py (75-80)` 这类“文件 + 行号范围”过滤定位
  - `match()` 输出 `GraphSearchMatch`（按视觉顺序排序的 `node_ids` + 需要保持高亮的 `edge_ids_to_keep` + `tokens_cf/source_spans` + 变量关联提示映射），用于导航与灰显。
  - UI 列表项 `GraphSearchResultItem` 采用**按需构建**：由 `GraphSearchIndex.build_result_item(...)` 在分页渲染时仅为当前页少量节点生成（含标题/类别/端口名/ID/坐标/源码行/代码变量名/变量名对/常量预览/命中标签/变量关联提示），避免命中很多节点时一次性创建大量结果对象。

## 注意事项
- 本目录模块**不依赖 PyQt**，仅依赖 `engine.graph.models` 的数据结构，便于单元测试与复用。
- 匹配语义默认不区分大小写（使用 `casefold()`）；性能敏感路径应避免在每次输入时重新构建索引。
- `GraphSearchIndex.match()` 仍保持“全字段包含所有 tokens”的默认语义，并在 `build_result_item()` 中为单条结果计算字段标签（例如：标题/常量/变量名/源文件/行号），用于帮助调试者快速分辨“为什么命中/命中的是什么”。
- 源码片段展示属于 UI 责任：`GraphSearchResultItem` 仅携带行号范围，具体从 `GraphModel.metadata["source_file"]` 读取代码并裁剪预览由 `GraphSearchOverlay` 负责（避免本目录引入文件系统依赖与 Qt 依赖）。
- `GraphSearchIndex.build(..., source_code=...)` 支持由 UI 侧注入源码全文，用于提取“赋值左值变量名”（例如 `目标踏板GUID列表 = 获取节点图变量(...)`）并纳入搜索索引；这样开发者可以直接用源码里的局部变量名定位对应节点。
- 行号范围过滤为**显式语法**：使用 `行:75-80` / `行:75` 或 `(75-80)` / `(75)`；纯数字（如 `12`）默认按文本搜索，用于匹配 `GIA序号` 等数字字段。


