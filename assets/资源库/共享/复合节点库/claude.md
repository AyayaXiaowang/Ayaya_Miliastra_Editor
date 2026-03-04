## 目录用途
存放跨项目复用的复合节点（Composite）源码（类格式 `.py`），供普通节点图按 `composite_id` 引用。

## 当前状态
- 复合节点采用类格式（`@composite_class` + JSON payload），对外节点名以类名为准；引脚通过 `流程入/流程出/数据入/数据出` 声明。
- `scope` 与 prelude 导入对齐：server 使用 `graph_prelude_server`，client 使用 `graph_prelude_client`。
- 当前仅维护少量通用复合节点，用于覆盖 Graph Code 中高频但受限的 Python 语法/模式（不在此维护清单）。

## 注意事项
- 每个文件头 docstring 必须包含 `composite_id/node_name/node_description/scope`；`composite_id` 全库唯一且稳定，引用以 `composite_id` 为准。
- 调用需要 `game` 入参的节点函数时必须显式传入 `self.game`。
- 字典字面量需落到变量并使用别名字典类型注解，避免用裸 `"字典"` 承载字面量。
- 强类型列表（如 `实体列表/浮点数列表/配置ID列表`）的字面量/`拼装列表` 在校验阶段会逐元素检查类型；如需“先初始化再清空”以避免空列表，初始化占位元素也必须是正确的元素类型（例如用 `self.owner_entity` 作为 `实体列表` 占位元素）。
- 新增/修改后必须校验：`python -X utf8 -m app.cli.graph_tools validate-graphs \"assets/资源库/共享/复合节点库\"`。

