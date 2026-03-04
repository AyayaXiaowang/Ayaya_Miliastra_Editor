## 目录用途
最小复现节点图目录：只放“一个复合节点 + 一个布尔虚拟引脚”的最小图，用于缩小 `.gil` 写回（section10 / CompositeGraph inner_nodes / Bool VarBase）问题范围并做稳定回归。

## 当前状态
- `TS_最小复现_布尔复合调用.py`：宿主图仅实例化一次 `TS_最小布尔复合_v1` 并传入布尔常量，便于导出后对照 `section10` 的布尔 NodePin 编码。

## 注意事项
- 该目录用于写回链路诊断：修改后建议跑 `python -X utf8 -m app.cli.graph_tools validate-file <节点图路径>`。
- 遵循 fail-fast：校验失败直接抛错，不做兜底。

