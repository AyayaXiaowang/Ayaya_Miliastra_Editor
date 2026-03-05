## 目录用途
节点图资源根：存放节点图的 Graph Code 源码（类结构 Python，`.py`），供引擎静态解析、校验与布局。

## 当前状态
- 当前仅包含 server 侧实体节点图的一小段示例子集（见 `server/实体节点图/第七关/`）。

## 注意事项
- 仅使用 `.py` 保存；文件头 docstring 必须声明 `graph_id/graph_name/graph_type/folder_path` 等元信息。
- 修改后跑校验闭环：`python -X utf8 -m app.cli.graph_tools validate-file <节点图路径>` 或 `python -X utf8 -m app.cli.graph_tools validate-project --package-id 示例项目_第七关`。
