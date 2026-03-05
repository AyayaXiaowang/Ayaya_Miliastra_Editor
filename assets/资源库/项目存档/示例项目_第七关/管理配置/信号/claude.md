## 目录用途
存放项目存档 `示例项目_第七关` 的自定义信号定义（Python 代码资源，`.py`）。
节点图中的【发送信号/监听信号】以这里的 `signal_name` 作为可用信号白名单，并据此补全参数端口与类型。

## 当前状态
- 目录内信号覆盖关卡大厅与第七关流程。
- 同目录也包含少量“参数类型覆盖”的回归用信号（标量/列表/多点发送/无参），便于校验信号参数类型支持情况。
- 信号定义按“共享根 + 当前项目存档根”聚合为只读 Schema 视图，供校验/编辑器/导出链路读取。

## 注意事项
- 每个信号一个 `.py` 文件，导出 `SIGNAL_ID` 与 `SIGNAL_PAYLOAD`（至少包含 `signal_id/signal_name/parameters/description`）。
- `signal_name` 在作用域内必须唯一；不允许出现“同名不同 ID”的重复定义。
- `parameters[].name/parameter_type` 必须与节点图端口名与中文类型一致；复杂聚合优先用结构体，不用字典参数。
- 修改后跑一次：`python -X utf8 -m app.cli.graph_tools validate-project --package-id <package_id>`。
