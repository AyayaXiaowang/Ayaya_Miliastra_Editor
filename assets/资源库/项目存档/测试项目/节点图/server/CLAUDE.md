## 目录用途
存放 `测试项目` 的 server 侧节点图脚本（Graph Code / 类结构 Python），用于 `.gil` 写回与进游戏回归验收。

## 当前状态
- 节点图集中放在 `实体节点图/回归/` 下，覆盖复合节点全类型 pins、信号、嵌套复合与多图复用，以及写回/导出口径回归。

## 注意事项
- 节点图脚本统一使用 workspace bootstrap：注入 `PROJECT_ROOT` 与 `assets/` 到 `sys.path`，并 `from app.runtime.engine.graph_prelude_server import *`。
- 单文件自检：在 `__main__` 中调用 `validate_file_cli(__file__)`。

