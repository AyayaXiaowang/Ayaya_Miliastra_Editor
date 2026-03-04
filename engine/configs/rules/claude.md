## 目录用途
引擎规则系统的只读配置与轻量规则函数：实体能力限制、组件兼容性、节点挂载约束、数据类型规则等，供校验器与运行时逻辑统一引用。

## 当前状态
- 规则以字典/枚举/纯函数为主，避免副作用与运行态依赖。
- 对外入口经 `engine.configs.rules.__init__` 统一导出。
- 关键模块：
  - `entity_rules.py`：实体类型与能力限制、类型规范化与变换校验
  - `component_rules.py`：组件使用与兼容性规则
  - `node_mount_rules.py`：节点图挂载规则与限制
  - `datatype_rules.py`：数据类型规则（与 `engine.type_registry` 保持单一真源）
  - `datatypes_typing.py`：节点图侧中文类型名占位声明（仅用于静态检查/补全）

## 注意事项
- 本目录仅依赖 `engine.*`，禁止反向依赖 `app/*`、`plugins/*`、`assets/*`。
- 规则说明可引用概念/字段名，但不要写外部知识库/文档系统的具体路径或 URL。
- 不使用 `try/except` 吞错；不一致应直接抛错让问题暴露。
