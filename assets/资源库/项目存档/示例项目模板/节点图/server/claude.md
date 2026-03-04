## 目录用途
存放本项目存档的服务器侧节点图脚本（Graph Code / 类结构 Python）。

## 当前状态
- 目录包含模板示例与测试脚本，用于教学与回归。

## 注意事项
- 节点图脚本使用统一 workspace bootstrap：文件头部注入 `PROJECT_ROOT` 与 `assets/` 到 `sys.path`，并统一 `from app.runtime.engine.graph_prelude_server import *`。
- 单文件自检：在 `__main__` 中调用 `validate_file_cli(__file__)`。
- 节点图类建议在 `__init__` 中调用 `validate_node_graph(self.__class__)`，确保校验口径与编辑器一致。
- 目录建议按业务域组织：实体节点图/状态节点图/职业节点图/道具节点图（未归类默认放入实体节点图）。
