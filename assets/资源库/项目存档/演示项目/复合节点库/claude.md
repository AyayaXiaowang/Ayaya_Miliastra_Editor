## 目录用途
- `演示项目/复合节点库/`：存放演示项目的复合节点（Graph Code DSL）示例与模板，供复制改造/教学与自检使用。

## 当前状态
- `composite_多引脚模板_示例.py`：多流程入/出与多数据入/出骨架示例，包含最小可读逻辑与 `__main__` 自检入口（调用 `validate_file`）。

## 注意事项
- 复合节点文件必须可通过引擎校验（`engine.validate_files` / `app.runtime.engine.node_graph_validator.validate_file`）。
- 已知节点调用需遵循项目约定的调用口径（例如需要 `game` 上下文的节点必须显式传入 `self.game`），避免触发静态校验错误。
- 节点图 DSL 的类型注解应使用中文类型字符串（例如 `"浮点数"`/`"整数"`）；避免在 DSL 代码里混用 Python `typing` 类型提示导致规则误判或解析不一致。
- 不在节点图 DSL 中写“判空/数据是否存在”的业务防御逻辑；这类逻辑对离线建模没有意义。

