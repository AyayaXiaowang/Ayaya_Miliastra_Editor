## 目录用途
节点系统核心：节点定义（`NodeDef`）、节点解析管线、节点注册表（`NodeRegistry`）、复合节点编辑能力（`CompositeNodeManager`）等。

## 当前状态
- **节点库构建**：`NodeRegistry` 负责构建并缓存“节点定义库（NodeDef）”，实现侧节点来自 V2 管线（只解析不导入），复合节点通过 `pipeline/composite_runner.py` 解析追加，构建期不依赖 `CompositeNodeManager`。
- **节点定义稳定键（canonical key）**：`NodeDef.canonical_key` 作为节点定义在节点库中的稳定主键；引擎提供统一入口 `get_canonical_node_def_key(node_def)` / `resolve_node_def_by_key(key, node_library=...)`，调用侧禁止自行拼接 `category/title/#scope` 作为定位键。`NodeDef` dataclass 字段顺序保持“非默认字段在前”，确保导入期不触发 dataclasses 参数顺序错误。
- **复合节点作用域**：复合节点加载遵循运行期 `active_package_id`（共享根 / 共享+当前项目存档根），避免跨项目存档全量聚合导致复合节点同名/同 ID 覆盖或串包；`NodeRegistry` 在请求节点库时会检测 `active_package_id` 变化并自动刷新，保证复合节点集合与当前作用域对齐。
- **复合节点管理**：`CompositeNodeManager` 仅用于复合节点的增删改查、落盘与懒加载子图，属于“编辑/运行期管理器”，不应参与节点库构建；默认写入落点为 `assets/资源库/项目存档/测试项目/复合节点库/`（仅在需要落盘时创建目录），不在 legacy 根 `assets/资源库/复合节点库/` 下自动创建目录或写入内容；当外部工具直接修改 `复合节点库/**/*.py` 时，可通过 `CompositeNodeManager.reload_library_from_disk()` 重新扫描并更新内存索引。
- **复合节点文件筛选**：统一由 `engine.nodes.composite_file_policy` 提供；复合节点定义文件位于资源库的任意“资源根目录”（`共享/`、`项目存档/<package_id>/`）下的 `复合节点库/**/*.py`（仅跳过 `__init__.py`），并默认按 `active_package_id` 作用域发现（共享根 + 当前项目存档根），manager/pipeline/校验入口共用同一规则避免漂移。复合节点文件名不再要求特定前缀，是否为复合节点由“处于复合节点库目录”这一位置语义决定。
- **复合节点子图解析**：需要显式注入 `base_node_library`；禁止在解析过程中隐式触发节点库构建或重新扫描实现库，避免缓存不一致与潜在循环依赖。全局工厂在未注入时会使用实现侧管线产物构建基础库（不触发 `NodeRegistry`）。

## 注意事项
- 严禁让复合节点编辑/解析路径在节点库构建过程中反向调用 `get_node_registry().get_library()`。
- 复合节点库的文件夹/文件操作必须进行安全路径归一化：只允许相对路径（统一使用 `/` 分隔，字符串级分隔符归一化统一复用 `engine.utils.path_utils.normalize_slash`），禁止绝对路径/UNC/盘符注入与任何 `.`/`..` 片段；并且在 `resolve(strict=False)` 后必须仍位于复合节点库根目录之下。
- 不使用 `try/except` 吞错；错误直接抛出，由上层处理。
- 不在节点图逻辑里书写任何“判空/数据是否存在”类防御代码；缺数据应直接报错暴露问题。
- 文档字符串与注释中的“工作区根目录”统一称为 `workspace_root`（不绑定具体仓库目录名）。

## 日志约定
- 节点库持久化缓存命中/失效/写入等细节默认降为 `log_debug`（由 `settings.DEBUG_LOG_VERBOSE` 控制），避免 UI 启动期刷屏；上层如需对用户展示节点库加载耗时/数量，应输出摘要级别日志（如 `log_info` 或更高层的汇总）。

## 目录用途
- 抽象节点规格与相关类型（端口、属性、校验约束）
- 提供节点定义加载与聚合能力（`node_definition_loader.py`, `impl_definition_loader.py`）
- 提供集中式节点注册与查询（`node_registry.py`）
- 管理端口名称/类型规则（`port_name_rules.py`, `port_type_system.py`, `port_index_mapper.py`）
- 提供复合节点管线与管理能力（`pipeline/*`, `composite_node_manager.py` 等）

## 公共 API（通过 `engine.nodes` 顶层导出）
- 定义与注册：`NodeSpec`, `node_spec`, `NodeDef`, `load_all_nodes`
- 节点库实例管理：`NodeRegistry`, `get_node_registry(workspace_path, include_composite=True)` 使用按 `(workspace_path.resolve(), include_composite)` 键控的缓存字典，为不同工作区和复合节点视图提供独立的节点库实例；**磁盘持久化缓存**（`app/runtime/cache/node_cache/node_library.json`）写入当前作用域下的节点库（含复合节点；复合节点集合由运行期 `active_package_id` 决定并纳入指纹）；`include_composite=False` 仅在实例内存中做过滤视图，避免覆盖缓存导致共享复合节点解析失败；测试环境可通过 `clear_all_registries_for_tests()` 显式清空实例缓存。
- 端口规则与类型：`get_dynamic_port_type`, `FLOW_PORT_TYPE`, `ANY_PORT_TYPE`, `GENERIC_PORT_TYPE`, `can_connect_ports`, `get_port_type_color`；其中 `can_connect_ports` 额外支持结构体家族类型 `结构体<struct_name>` / `结构体列表<struct_name>`：仅允许 **同名互连**（`结构体`↔`结构体` 或 `结构体<A>`↔`结构体<A>`），避免未绑定结构体名时把“泛型结构体”误连到任意具体结构体。
- 枚举与常量：`NodeCategory`, `NODE_CATEGORY_VALUES`, `ALLOWED_SCOPES`
- 复合节点：`CompositeNodeManager`（延迟导入以避免循环依赖）、`get_composite_node_manager(workspace_path, ...)`（首次创建必须显式传入 workspace；若全局缓存中仅存在单一工作区实例，可省略 workspace_path 直接复用；多工作区场景必须显式传入避免歧义）、`clear_global_composite_node_manager_for_tests()`（测试清理口）、虚拟引脚与映射配置类型，以及基于 `CompositeVirtualPinSnapshot` 的虚拟引脚撤销助手（`composite_virtual_pin_undo_helper.py`），为 UI 撤销命令提供纯模型级快照/恢复能力

## 依赖边界与节点实现来源
- 允许依赖：`engine/utils`、`engine/graph`、`engine/validate`
- 禁止依赖：`plugins/*`、`app/*`、`assets/*`、`core/*`
- 节点实现代码的实际来源为工作区根目录下的实现库管线：
  - 现用实现库：`plugins/nodes/`
- 节点库持久化缓存的“变更指纹”与图缓存共用统一实现：同时覆盖历史目录、新目录以及节点定义/图解析核心和复合节点库，任一部分变更都会触发缓存失效与重建。

## 当前状态与注意事项
- 节点实现发现与索引已迁移至 `plugins/nodes` 管线；不再在运行期解析旧 `node_implementations/` 目录。
- 节点函数类型桩生成：`engine.nodes.stubgen.generate_nodes_pyi_stub(workspace_root, scope=...)` 可从 `NodeRegistry/NodeDef` 导出 `plugins/nodes/{server,client}/__init__.pyi`（`.pyi` 仅用于类型检查/补全），用于在写 Graph Code 时获得“节点入参端口名 + 端口类型 + 返回值形态”的 IDE 提示并降低拼写风险。
- 实现侧 NodeDef 构建支持可控的“别名键注入”：`impl_definition_loader.load_all_nodes_from_impl(..., inject_alias_keys=...)` 可关闭别名直达键，便于导出/回归场景稳定以 `by_key` 为唯一节点集合，并单独通过 `alias_to_key` 表达兼容改名。
- 端口类型推断统一通过 `port_name_rules.get_dynamic_port_type()`；流程口判断统一使用 `engine.utils.graph.graph_utils.is_flow_port_name()`。
- 端口类型语义（流程/泛型/泛型列表/泛型字典、字典别名判定、列表判定等）统一以 `engine/type_registry.py` 的规范类型名与工具函数为唯一事实来源，`port_type_system.py` 仅负责“连线判定与 UI 颜色”的端口侧逻辑，避免类型语义在多处实现发生漂移。
- 节点作用域以 `NodeDef.scopes` 为唯一语义来源：`scopes` 非空则只在对应作用域可用；`scopes` 为空则视为通用节点（在所有受支持作用域中均可用）。不再依赖 `doc_reference` 推断作用域，避免“文档目录结构变更=功能变更”的高耦合风险。
- 为避免循环依赖，复合节点管理器采用延迟导入与模块级转发。
- 复合节点库加载阶段直接依赖 AST / IR 解析构建内存索引，语法或结构错误会在解析时抛出异常，由调用方或 UI 层显式暴露问题，而不在管理器内部静默跳过。
- 不使用异常吞没；节点与图解析相关错误在进入引擎层后仍直接抛出，由调用方按需处理。
- `NodeRegistry` 节点库加载采用阻断式策略：禁止“加载中静默返回空库”。同线程重入会抛出 `NodeRegistryRecursiveLoadError`；跨线程并发访问会等待加载完成，确保上层不会拿到半成品节点库。
- 复合节点解析阶段会在应用布局时显式注入“基于基础节点库派生的布局上下文”，避免解析期反向调用 `NodeRegistry` 引发递归加载。
- 复合节点装饰器 `flow_entry` / `event_handler` / `data_method` 支持省略 `inputs`/`outputs`，依赖 `auto_inputs/auto_outputs` 标记与 `engine.graph.composite.pin_api` 提供的辅助函数填充虚拟引脚。
- `CompositeNodeManager` 的影响分析复用了 `engine.resources.graph_reference_tracker` 并缓存复合节点引用，避免每次分析都全量扫描节点图。
- 附录/节点图高级特性中的 `advanced_node_features.py` 集中定义结构体、信号、泛型引脚等高级概念，并以 `VirtualPinConfig/CompositeNodeConfig` 为核心描述复合节点的虚拟引脚配置，提供从 `PackageModel.signals` 到运行时 `SignalDefinition` 的桥接函数，供校验、代码生成和 Todo 管线复用。
- `NodeSpec` 支持 `input_generic_constraints`/`output_generic_constraints` 以及 `input_enum_options`/`output_enum_options` 字段，分别用于约束泛型端口允许的具体类型与声明枚举端口可选值集合；管线与 `NodeDef` 将原样保留这些元数据，验证器/编辑器可以据此阻止非法类型连接或枚举取值。
- `NodeSpec`/`NodeDef` 支持 `semantic_id`（稳定语义标识符），由 V2 管线透传到索引与 NodeDef，供校验/工具链稳定识别语义节点，避免依赖显示名字符串。
- `NodeSpec`/`NodeDef` 支持 `input_port_aliases`/`output_port_aliases`（端口别名/历史端口名集合），用于兼容“端口改名”；V2 管线与 manifest 导出会透传该字段，diff 与 Graph Code 迁移工具可据此自动改写端口名。
- `NodeSpec`/`NodeDef` 支持 `input_defaults`（输入端口默认值）：用于声明“可选输入端口”的缺省值；解析 Graph Code 与导出可执行代码时会据此补齐/省略等价的默认入参，避免把“缺参/缺线”变成运行期隐式错误。
- `engine.nodes.migrations` 提供迁移规则模型（纯数据/纯函数）：用于表达节点改名、端口改名等 breaking 变更的显式迁移计划；Graph Code 自动迁移工具属于内部工具链，不随仓库公开分发。
- 复合节点加载器在仅提取元数据与虚拟引脚时不会构建完整节点库，而是在需要加载子图或生成函数代码时才依赖基础节点库与实现管线；`CompositeNodeManager` 构造时优先复用 `NodeRegistry` 提供的节点库，避免在复合节点加载路径上重复跑节点实现管线，从而降低 UI 启动与模式切换的卡顿感。
- 复合节点的“源码生成/落盘”（`save_composite_to_file`）不再由引擎层内置生成器实现：需要由上层注入 `composite_code_generator.generate_code(CompositeNodeConfig)`；引擎层仅负责复合节点配置/子图的解析、校验与持久化编排，避免绑定运行时/插件导入策略。
- 复合节点落盘格式以**类格式（@composite_class）+ JSON payload**为闭环契约：加载器在懒加载阶段可从 `COMPOSITE_PAYLOAD_JSON` 直接提取虚拟引脚与元信息但不加载子图；保存则写回 payload，避免生成“解析不了的新文件”。新建复合节点默认创建“流程入/流程出”两个流程虚拟引脚，避免落盘空壳导致后续加载/校验失败。**旧函数式复合节点格式已移除且禁止使用**，确保“校验=解析=懒加载展示”口径一致。
- `CompositeVirtualPinManager` 统一负责虚拟引脚映射的增删查与显示编号计算，并提供按内部节点 ID 批量清理映射的辅助函数，供 UI 撤销命令和批处理工具在不关心持久化细节的前提下复用。
- 虚拟引脚类型遵循 `port_type_system.ANY_PORT_TYPE/GENERIC_PORT_TYPE`（即“泛型”）；禁止使用旧别名 `"any"/"Any"/"ANY"`，遇到会直接抛错，需手工迁移为“泛型”。
