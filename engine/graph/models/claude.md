## 目录用途
`engine/graph/models/` 存放节点图与资源视图相关的核心数据模型与序列化逻辑（纯数据/纯逻辑），不包含 UI 或磁盘 I/O。

## 当前状态
- **图模型**：`graph_model.py` / `graph_serialization.py` / `graph_hash.py` / `graph_config.py` 提供图结构、序列化与内容哈希。
  - `NodeModel` 额外携带 `effective_input_types/effective_output_types` 端口类型快照，用于 `graph_cache` 与工具链快速读取（不作为连线判定的单一真源）。
  - `NodeModel.node_def_ref`（`NodeDefRef(kind+key)`）作为节点定义定位的唯一真源：builtin/composite 用于精确解析节点库 NodeDef；event 用于表达“自定义事件入口”等不在节点库中的事件节点（不依赖 title fallback）。后续校验/UI/自动化/导出应通过该引用解析 NodeDef，禁止使用 `title` 作为定位键；缺失该字段视为旧数据，由上层缓存门禁触发重建（不做 title fallback）。
    - `NodeDefRef.from_dict` 明确接受 `kind="event"`，保证包含事件稳定标识的图数据可被反序列化/加载（UI 会话恢复等场景不应因该 kind 崩溃）。
- **语义元数据单一写入**：`signal_bindings` / `struct_bindings` 仅允许 `engine.graph.semantic.GraphSemanticPass` 写入，其他模块不得直接写入 metadata。
  - 禁止写入的统一报错入口收敛到 `deprecated_metadata_writes.py`，用于在 `GraphModel/SignalBindingService` 等处保持一致的错误信息与行为。
- **存档模型**：`package_model.py` 提供模板/实体摆放/战斗预设/管理配置等存档侧数据类型，供 `engine.resources` 与上层应用复用；管理配置中包含 UI 相关聚合字段（`ui_layouts/ui_widget_templates/ui_pages`），用于承载 UI 工作流的运行时资源与入口对象。
  - 关卡变量定义：`LevelVariableDefinition`（管理配置/关卡变量的代码级定义单一真源）。
  - 节点图变量：`GraphVariableConfig` 支持可选 `struct_name`（结构体/结构体列表图变量用于绑定既有结构体定义；常见 default_value=None 仍可省略）。
  - 实体摆放覆写：`LevelVariableOverride`（实例 JSON 以 `variable_id + value` 覆写变量值；**严格要求字段名为 `variable_id/variable_name/variable_type/value`，不再兼容用 `name` 充当别名或用 `default_value` 代替 `value`**）。
  - 实体摆放变换：`InstanceConfig` 维护 `position/rotation/scale` 三个 Vector3 字段（`scale` 默认 `1,1,1`），用于属性面板与序列化一致展示。
  - 模板/实例扩展配置：`TemplateConfig.entity_config` 与 `InstanceConfig.entity_config` 对齐，用于承载实例级与模板级的扩展配置段落（例如战斗标签页字段）。
- **实体类型视图**：`entity_templates.py` 聚合规则层实体类型信息与 UI 展示信息（图标/分类/说明）；变量类型清单以 `engine/type_registry.py` 为单一真源。

## 注意事项
- 本目录禁止引入 PyQt、文件读写或网络请求。
- 新增/调整模型字段需同步更新 serialize/deserialize（以及必要的兼容逻辑）。
- 不在本目录复制规则清单；规则来源应从 `engine.configs.rules` / 组件注册表读取。

---

注意：本文件不记录修改历史，仅维护“目录用途 / 当前状态 / 注意事项”的实时描述。

