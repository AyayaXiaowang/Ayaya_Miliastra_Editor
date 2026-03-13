## 目录用途
最小复现节点图目录：用于回归“节点图挂载（mount metadata）写回 base `.gil` 的实体摆放段（root5，slot=3）”链路。

## 当前状态
- `回归_节点图挂载_实体.py`：声明 `mount: entity_key:...`，用于验证导出/写回时能把写回后的 `graph_id_int` 绑定到目标实体实例。

## 注意事项
- 修改后建议跑：`python -X utf8 -m app.cli.graph_tools validate-file <节点图路径>`。
- 本目录仅用于回归与诊断；不作为业务项目维护。

