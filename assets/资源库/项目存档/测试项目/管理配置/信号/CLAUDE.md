## 目录用途
存放项目存档 `测试项目` 的自定义信号定义（Python 代码资源，`.py`）。
节点图中的【发送信号/监听信号】以这里的 `signal_name` 作为可用信号白名单，并据此补全参数端口与类型。

## 当前状态
- 目前包含 1 个测试集专用信号：`TS_Signal_AllTypes_001`（覆盖多类型参数）。

## 注意事项
- 每个信号一个 `.py` 文件，导出 `SIGNAL_ID` 与 `SIGNAL_PAYLOAD`（至少包含 `signal_id/signal_name/parameters/description`）。
- `signal_name` 在作用域内必须唯一；不允许出现“同名不同 ID”的重复定义。
- 参数端口名必须与 Graph Code 中 `发送信号(..., 参数名=...)` 保持一致。

