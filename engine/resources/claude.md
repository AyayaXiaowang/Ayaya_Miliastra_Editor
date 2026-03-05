# 目录用途

资源层（纯逻辑）：以 `ResourceManager` 为唯一入口，管理资源库（JSON 资源、Graph Code `.py`、管理配置代码资源等）的索引、读写、缓存、作用域（共享/项目存档）、引用追踪与只读视图。

## 当前状态

- **门面 + 分服务**：`ResourceManager` 负责对外 API 与跨服务编排；索引/图/缓存/文件操作分别由 `ResourceIndexService` / `GraphResourceService` / `ResourceCacheService` / `ResourceFileOps` 等实现类承担。
- **作用域（共享 + 当前存档）**：索引与代码级 Schema（结构体/信号/关卡变量/局内存档模板等）统一按 `active_package_id` 聚合【共享根】或【共享根 + 当前项目存档根】；同 ID 以项目存档覆盖共享，重复 ID 由校验工具定位修复。
- **代码级 Schema 载入**：结构体/信号/关卡变量/局内存档模板等“声明型” `.py` 定义文件使用 AST 静态提取（不执行顶层代码；关卡变量保留子进程 `compile` 语法预检用于热重载容错）；其余确需运行期语义的代码资源通过 `engine.utils.module_loader` 或专用 loader 动态加载，并按各子服务的规则选择“跳过非法文件”或 fail-fast。
- **关卡变量载入校验**：局内存档变量（`自定义变量-局内存档变量`）的 `variable_name` 必须符合 `玩家槽位_chip_序号` 且同槽位序号从 1 开始连续；字典/typed dict 变量的 `default_value` 禁止出现嵌套 dict（需要复杂结构请改用结构体/结构体列表）。
- **代码级资源加载**：`ResourceManager.load_resource` 对 `SIGNAL/STRUCT_DEFINITION` 直接从 `.py` 文件静态提取 `*_PAYLOAD`（不 import 执行），并仍按 `(type,id,mtime)` 做缓存。
- **自定义变量注册表（单一真源）**：`管理配置/关卡变量/自定义变量注册表.py` 通过 AST 静态提取声明与 data store 绑定（`load_auto_custom_variable_registry_from_code`），并默认接入关卡变量 Schema：当注册表存在时，Schema 会派生虚拟变量文件（稳定 `file_id`，`absolute_path` 指向注册表）；同时跳过磁盘上的派生变量文件（`自动分配_*`、`UI_*_自动生成`）以避免与虚拟变量文件产生 ID 冲突与多处真源。变量类型支持 typed dict alias（如 `字符串-整数字典`），并在 schema 载入阶段校验 key/value 类型名合法性。
- **注册表 contract 严格化（字段白名单）**：注册表声明条目必须为 `AutoCustomVariableDeclaration(...)` 常量写法，禁止 dict/运行期拼装；并对 `metadata` 执行严格白名单校验（仅允许明确约定的 keys，例如 `sources`），不允许随意增删字段导致真源漂移。
- **owner 直接引用实体/元件**：registry 的 `owner` 直接填 `instance_id`/`template_id` 或广播关键字 `player`/`level`；支持 `str | list[str]`（多 owner）。已废弃 `data:<store_key>` 间接语法与 `CUSTOM_VARIABLE_DATA_STORES` 绑定表；虚拟变量文件按 owner ref 分组，sync-custom-vars 按 owner 查找实体/模板并追加变量文件引用。
- **owner 合约（强语义字段）**：关卡变量 payload 强制携带顶层 `owner(level|player|data)`；Schema 载入阶段通过 `level_variable_owner_contract.validate_and_fill_level_variable_payload_owner(...)` 做值域校验与 fail-fast，并支持从历史 `metadata.auto_owner` 显式迁移填充 `owner`（两者冲突会报错）。注册表派生的虚拟变量 payload 直接写入 `owner`，不再写入 `metadata.auto_owner`。
- **节点图读写拆分**：节点图加载/保存/缓存/元数据分别由 `GraphLoader` / `GraphSaver` / `GraphCacheFacade` / `GraphMetadataReader` 负责；`GraphResultDataBuilder` 是 `GraphModel -> result_data` 的单一真源（补齐 `node_defs_fp`、`layout_settings`、`folder_path` 等关键字段）。
- **轻量展示路径**：列表/文件夹树等“只展示”场景走 `GraphResourceService.load_graph_metadata()`（tokenize 读取模块首个 docstring，默认 `utf-8-sig`）；避免触发严格解析与自动排版。节点/连线数量仅来自持久化 `graph_cache`，未命中则保持为空。
- **folder_path 推断与标准化**：节点图 docstring 可不声明 `folder_path`，资源层会从 `.py` 文件路径推断并用 `engine.utils.path_utils.normalize_slash` 归一化；必要时会对旧缓存补齐，保证 UI 展示稳定。
- **缓存与指纹**：进程内缓存由 `ResourceCacheService`；磁盘持久化缓存由 `PersistentGraphCacheManager` 管理（位于 `settings.RUNTIME_CACHE_ROOT`）。兼容性以 `NodeModel.node_def_ref` 与 `node_defs_fp/resource_library_fingerprint` 等数据契约为基线，不兼容即失效重建。
- **后台快照提交**：后台完成的 `ResourceIndexData + resource_library_fingerprint` 可通过 `apply_index_snapshot(...)` 一次性提交替换，避免 UI 线程执行全量扫描。
- **外部修改保护**：保存支持可选 `expected_mtime`（`save_resource(..., expected_mtime=..., allow_overwrite_external=...)`），用于阻止静默覆盖外部工具改动。
- **写盘健壮性**：JSON 类文件统一原子写（`atomic_json.atomic_write_json`）；持久化缓存读取可修复“尾部残留/多段 JSON”并重写为单段，避免启动期 `JSONDecodeError`。
- **代码生成解耦**：节点图 `.py` 源码生成不在 `engine` 内硬编码，`GraphResourceService.save_graph` 通过依赖注入接收 `graph_code_generator.generate_code(...)`（由应用层决定策略）。
- **统一解析门面**：`ref_resolver.py` / `package_guid_index.py` 将 GUID/变量/结构体等多跳解引用收敛到资源层；自定义变量文件引用（`str/list`）统一由 `custom_variable_file_refs.py` 解析与写回。

## 注意事项

- 禁止手拼资源路径；统一通过 `ResourceFileOps` / `ResourceManager`，并保持路径使用 `pathlib.Path`。
- 资源索引扫描只认“稳定 ID 字段”（不回退文件名）；顶层 JSON 必须为 object（dict）才会入索引。字段/命名约定以 `management_naming_rules.py` 与 `resource_filename_policy.py` 为单一真源。
- 新建资源场景必须显式传入 `resource_root_dir`（全局视图→共享根；包视图→当前包根），否则会落到默认归档项目并在当前视图不可见。
- 节点图仅支持资源根目录下的类结构 `.py`；展示列表不要调用 `load_resource(ResourceType.GRAPH, ...)`，否则会触发解析与自动布局。
- 不使用 try/except 吞错；需要容错的路径以“显式兼容/失效策略”实现（例如缓存不自洽→删除并重建）。

---
注意：本文件不记录变更历史，仅描述目录用途、当前状态与注意事项。
