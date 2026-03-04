## 目录用途
项目存档 `示例项目_第七关` 的实体摆放资源：存放关卡/场景实例（InstanceConfig）JSON，用于描述实体模板引用、初始位置与装饰物等。

## 当前状态
- 目录用于示例与回归；实例引用以业务 ID/GUID 等为准（不在本文档维护清单）。

## 注意事项
- 通过 ResourceManager/编辑器维护，避免手工改字段导致引用悬空。
- 修改后跑一次：`python -X utf8 -m app.cli.graph_tools validate-project --package-id <package_id>`。
