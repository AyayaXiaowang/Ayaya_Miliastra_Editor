## 目录用途
- 关卡变量（Level Variables）代码资源根：以 `自定义变量注册表.py` 作为自定义变量的单一声明入口，供 UI/节点图/导出链路读取与校验。

## 当前状态
- `自定义变量注册表.py`：收敛 `lv.*`（owner=level）与玩家侧 `ps/p1~p8.*`（owner=player）变量声明；UI `validate-ui` 会按注册表派生的 Schema 校验占位符存在性与字典键路径。

## 注意事项
- 本目录资源为测试/回归夹具：内容以“能覆盖 UI 校验与写回链路”为目标，不作为业务项目维护入口。
- 修改后建议跑：
  - `python -X utf8 -m app.cli.graph_tools validate-ui --package-id 测试项目`
  - `python -X utf8 -m app.cli.graph_tools validate-project --package-id 测试项目`

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

