## 目录用途
存放资源库/索引/扫描策略相关测试：覆盖资源目录扫描的健壮性、索引条目生成、命名与文件名同步策略等，确保资源层规则稳定且不会在扫描阶段产生意外回写。

## 当前状态
- `test_resource_index_items_scan.py`：回归资源索引扫描生成的条目结构与关键字段（以 `tmp_path` 最小工作区构造输入）。
- `test_graph_folder_tree_scan_is_resilient.py`：回归节点图文件夹树扫描的健壮性（异常文件/边界情况不应导致扫描崩溃）。
- `test_graph_folder_path_inference.py`：回归节点图 `folder_path` 的推断与缓存自愈：当 docstring 未声明 folder_path 或旧缓存缺失 folder_path 时，资源层应能基于文件路径补齐，保证 UI 展示一致（样例图位于 `节点图/server/实体节点图/模板示例/`）。
- `test_graph_cache_update_from_model.py`：回归 UI 自动排版后“从 GraphModel 刷新持久化缓存”的口径：result_data.metadata 必须补齐 `node_defs_fp` 并能命中进程内缓存；同时 folder_path 仍应可从文件路径推断（样例图位于 `节点图/server/实体节点图/模板示例/`）。
- `test_effective_port_type_cache.py`：回归 graph_cache 的“有效端口类型缓存”生成：覆盖【获取局部变量】值端口透传、【拼装字典】键/值类型按别名字典收敛、以及“下游常量确定类型→上游泛型输出沿连线推断”的传播。
- `test_package_directory_structure_ensure.py`：回归项目存档“目录骨架补齐”接口：以 `示例项目模板/` 目录结构为真源镜像创建缺失目录，并跳过 `__pycache__`/`文档/共享文档`；模板缺失时走最小 fallback。
- `test_package_index_manager_public_naming_api.py`：回归 `PackageIndexManager` 的公开命名清洗 API：`sanitize_package_id(name)` 必须存在且与 `engine.utils.name_utils.sanitize_package_filename` 口径一致（供 UI/扩展调用，避免依赖下划线私有方法）。
- `test_resource_name_filename_sync_policy.py`：回归“扫描阶段是否允许将文件名回写到 JSON.name”的策略边界，避免 UI 改名被索引扫描回滚。
- `test_resource_index_code_py_resources_scan.py`：回归代码级资源（`管理配置/信号`、`管理配置/结构体定义`）的 `.py` 扫描与索引条目生成，避免存档视图漏掉信号/结构体定义导致 UI 混看或空列表。
- `test_resource_preview_scan_service.py`：回归“预览磁盘扫描”服务的扫描口径与缓存失效：覆盖 JSON 资源 ID 字段读取、节点图 docstring graph_id 回退、信号/结构体模块常量提取、结构体定义按 `basic/ingame_save` 分类扫描（目录即分类 + `STRUCT_TYPE/STRUCT_PAYLOAD` 回退），以及 `invalidate()` 后重新触盘生效。
- `test_level_variable_schema_view_ast_loading.py`：回归关卡变量代码资源加载契约：从示例包中加载 `LEVEL_VARIABLES`（`LevelVariableDefinition(...)`）并断言浮点/向量默认值可被正确静态提取，避免动态 import 执行顶层代码回流。
- `test_ingame_save_template_schema_view_ast_loading.py`：回归局内存档模板代码资源加载契约：从示例包中加载 `SAVE_POINT_ID/SAVE_POINT_PAYLOAD` 并断言 entries/struct_id 等关键字段可被正确静态提取。
- `test_resource_manager_load_code_py_resources_static_extract.py`：回归 `ResourceManager.load_resource` 读取 `SIGNAL/STRUCT_DEFINITION` 的 `.py` 资源时不执行顶层代码（文件内刻意放置 `raise` 作为护栏），并断言 payload 静态提取结果正确。
- `test_auto_custom_variable_registry_ast_extract.py`：回归“自定义变量注册表”静态加载：从 `.py` 中提取 `CUSTOM_VARIABLE_DECLARATIONS/DATA_STORES` 并保证文件内顶层 `raise` 不会被执行（禁止动态 import）。
- 自定义变量注册表声明 contract 约束：声明条目必须为 `AutoCustomVariableDeclaration(...)` 常量写法；`owner` 使用实体级语法 `player|level|data:<store_key>`；禁止旧字段 `per_player/ui_visible/frontend_read/data_store_key` 与非白名单 metadata keys。
- `test_package_view_shared_visibility.py`：回归 `PackageView` 在具体存档视图下的“可见资源集合”语义：应同时包含共享根目录与当前存档根目录下的模板资源，并支持通过 `get_template()` 直接访问共享模板。
- `test_index_disk_consistency.py`：回归“索引（PackageIndex 视图）vs 磁盘（项目存档目录扫描）”一致性报告：覆盖孤儿/缺失/磁盘重复 ID 的统计口径与可复现最小输入。

## 注意事项
- 需要文件系统时优先在 `tmp_path` 下构造最小资源目录与样例文件，避免污染仓库工作区。
- 资源目录构造需遵循资源库“多 root”布局：优先写入 `assets/资源库/共享/...` 或 `assets/资源库/项目存档/<package_id>/...`，避免使用 legacy 的 `assets/资源库/<资源类型>/...` 平铺路径导致扫描不到。
- 资源索引默认仅扫描共享根目录；若测试需要访问“具体项目存档目录”下的资源，应在用例中显式调用 `ResourceManager.rebuild_index(active_package_id=...)` 切换作用域。
- `TemplateConfig` 不再在模板 JSON 内声明默认变量字段；如测试需要覆盖变量行为，应通过【管理配置/关卡变量】与 `metadata.custom_variable_file` 走关卡变量体系。


