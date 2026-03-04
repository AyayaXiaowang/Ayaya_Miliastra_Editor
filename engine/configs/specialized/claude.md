## 目录用途
编辑器特化/高级概念相关的配置数据模型集合（以 `dataclass` 为主）：覆盖 UI 控件、节点图高级配置、战斗/仇恨扩展、资源系统扩展等，供编辑器 UI、校验器与工具链读取。

## 当前状态
- 模块按主题拆分，入口为 `engine.configs.specialized`。
- `ui_widget_configs.py` 为 UI 控件配置的权威定义；其它模块应导入复用，避免重复枚举/字段漂移。
- `node_graph_configs.py` 描述节点图相关的特化配置；`struct_definitions_data.py` / `signal_definitions_data.py` 提供结构体/信号定义的只读访问封装（面向当前资源作用域）。
- 其它常用模块：`specialized_configs.py`、`ability_units_configs.py`、`combat_effect_configs.py`、`resource_system_extended_configs.py`、`additional_advanced_configs.py`、`overview_configs.py`。

## 注意事项
- 保持“纯数据 + 轻量序列化/规范化工具函数”，不要在此引入运行时业务流程或 UI 依赖。
- 导入建议按需导入具体模块，避免 `from engine.configs.specialized import *` 造成命名冲突。
- 注释/文档中不要硬编码外部文档/知识库的物理路径或 URL，仅保留概念性说明。

