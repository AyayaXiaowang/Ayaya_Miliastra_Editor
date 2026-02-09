## 目录用途
引擎核心层：图模型、节点规格、布局、验证、执行器、无状态工具与资源访问等纯逻辑模块。禁止依赖应用层与插件层。

## 公共 API
统一从 `engine/__init__.py` 暴露稳定接口；子模块默认视为内部。

当前导出的公共 API（按功能域组织）：
- **图模型**：`GraphModel`, `NodeModel`, `EdgeModel`, `PortModel`, `BasicBlock`
- **序列化与哈希**：`serialize_graph`, `deserialize_graph`, `get_content_hash`
- **配置模型**：`GraphConfig`, `LevelVariableDefinition`, `LevelVariableOverride`, `SignalConfig`, `ComponentConfig` 等（包级索引与视图由 `PackageIndex` + `PackageView` 表达）
- **节点系统**：`NodeRegistry`, `get_node_registry`, `NodeSpec`, `node_spec`, `NodeDef`
- **端口系统**：`port_type_system`, `port_name_rules`, `port_index_mapper`
- **复合节点**：`CompositeNodeManager`, `CompositeNodeConfig`, `VirtualPinConfig`
- **图代码解析**：`GraphCodeParser`, `CompositeCodeParser`, `GraphParseError`, `validate_graph_model`（代码生成能力迁移到应用层）
- **验证引擎**：`validate_files`, `ComprehensiveValidator`
- **布局算法**：`layout_service`（纯数据输出，与 UI 解耦），负责跨块数据副本处理、BasicBlock 构建与布局 Y 轴调试信息生成
- **资源视图与访问**：`ResourceManager`, `PackageIndexManager`, `PackageView`, `GlobalResourceView` 等，用于统一访问 `assets/资源库` 中的模板、实例、关卡实体与管理配置。
- **工具函数**：`is_flow_port_name`, `log_info`, `log_error`, `log_warning`（分别由 `engine.utils.graph` 与 `engine.utils.logging` 提供）

## 依赖边界
- 允许依赖：标准库、`engine/*` 内部模块
- 禁止依赖：`app/*`、`plugins/*`、`assets/*`、`core/*`（以及任何未纳入仓库的内部工具链/本地脚本）
- 不依赖任何 `core.*` 模块；所有图模型、布局、验证、资源与工具能力均以 `engine.*` 作为唯一入口。

## 当前状态
- 引擎层仅保留 `graph`、`configs`、`layout`、`nodes`、`resources`、`utils`、`validate` 等活跃子模块；执行/IO/聚合服务放在应用层或工具层实现，避免在 `engine` 下留下空壳目录。
- 资源视图层通过 `PackageView`/`GlobalResourceView` 等对象提供对模板、实例与关卡实体的只读/可写访问：每个存档的关卡实体通过 `PackageIndex.level_entity_id` 引用，若索引缺失但实例中已存在带 `metadata.is_level_entity=True` 的实体，则视图层会自动识别并补写索引，保证验证规则与 UI 视图能够一致地发现关卡实体。
- 图代码解析层统一负责从节点图代码与 docstring 中提取图元数据、信号绑定与结构体绑定信息，为验证规则与图编辑 UI 提供一致的 `GraphModel.metadata` 视图；信号与结构体节点的标题、静态端口名（包括用于选择资源的“信号名”“结构体名”端口）在 `engine.graph.common` 中集中维护，供 UI、代码生成与校验共享。
- 类型体系已收敛为单一事实来源：规范中文类型名（基础/列表/结构体/字典/流程/泛型/枚举）、别名字典解析、结构体字段与图变量允许集合等均集中在 `engine/type_registry.py`；配置层、验证层与端口系统均通过导入该模块或其兼容转发模块消费类型信息，避免多份清单漂移。
- `validate` 子模块提供基于 AST 与节点图结构的双层校验能力：既包含 Graph Code 的语法/布尔条件/图变量/类型名/信号参数名等规则，也包含针对复合节点与局部变量（如【获取局部变量→设置局部变量】模式）的结构化检查，统一通过 `validate_files` 与 `ComprehensiveValidator` 对外暴露。
- `plugins`、`app`、`tests` 统一通过 `engine` 公共 API 使用图模型、验证与布局能力，不再通过历史兼容路径导入。
- 结构体校验已收紧：拆分/拼装/修改结构体节点必须填写“结构体名”输入端口，缺失会直接报错，避免因未绑定结构体名导致的运行期风险。

## 注意事项
- 仅存放无 UI/无外设 I/O 的纯逻辑代码。
- 严禁循环依赖；跨子模块协作通过明确的边界函数实现。
- 不使用 `try/except` 吞错；错误直接抛出，由上层处理。
- 外部代码（`app`/`plugins`/`tests`）应统一通过 `engine` 顶层导入，不再使用 `core.*`。
- 新代码必须遵循依赖边界，禁止反向依赖 core/app/plugins。
- 资源库根目录统一为 `assets/资源库`（由 `engine.resources.ResourceManager` 管理与扫描）；请勿在引擎层硬编码其他资源路径。
- 引擎产生的运行期缓存应统一落在“工作区根目录/app/runtime/cache”；`engine/` 下不应出现 `app/runtime/cache` 等运行期产物目录。
