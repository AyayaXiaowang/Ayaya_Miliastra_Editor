## 目录用途
存放服务器端共享节点图脚本（Graph Code，类结构 Python）。

## 当前状态
- 目录按类型分层（实体节点图/状态节点图/职业节点图/道具节点图），并在 `模板示例/` 中维护少量可复制的教学样例。

## 注意事项
- 节点图脚本使用统一 workspace bootstrap，并统一 `from app.runtime.engine.graph_prelude_server import *`（不要注入 `<repo>/app`）。
- 建议在 `__main__` 中调用 `validate_file_cli(__file__)`，并在 `__init__` 中调用 `validate_node_graph(self.__class__)` 对齐编辑器/校验口径。
- 未归类内容默认归入“实体节点图”。

