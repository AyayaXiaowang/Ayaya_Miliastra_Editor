## 目录用途
拆分后的 `PackageIndexManager` 实现模块集合，用于管理“目录即项目存档”模式下的存档索引派生、创建/复制、运行期状态与资源归属移动等能力。

对外入口仍为 `engine.resources.package_index_manager.PackageIndexManager`（该模块仅做重导出，保持兼容）。

## 当前状态
- `manager.py`：组合各 mixin，定义最终的 `PackageIndexManager` 类与构造逻辑；启动时会拦截旧式索引文件 `pkg_*.json` / `packages.json`（仅检查资源库根目录），避免误扫外部工具产物目录。
- `naming_listing_mixin.py`：存档列表、路径判定、显示名与 `resource_names` 派生；实体摆放目录名以 `ResourceType.INSTANCE.value` 为唯一真源（不再兼容旧目录名 `实例`）；并提供公开命名清洗 API `sanitize_package_id(name)`（供 UI/扩展调用，避免依赖下划线私有方法）。
- `package_clone_mixin.py`：新建/复制项目存档、目录骨架/文档、克隆 ID 改写与清理；并提供 `ensure_package_directory_structure(package_id)` 用于“导入/解析型流程”在落盘后补齐目录骨架（以 `示例项目模板/` 的目录层级为真源镜像创建缺失目录，跳过 `__pycache__` 与 `文档/共享文档`）。UI 工作流目录骨架仅保留 `管理配置/UI源码`（HTML 为真源；UI 派生物统一写入运行时缓存，不落资源库）。
- `index_cache_mixin.py`：目录派生 `PackageIndex`、进程内缓存、Todo 状态落盘与基础包操作。
- `runtime_and_movement_mixin.py`：运行期 package_state（最近打开）与资源“归属根目录”移动（共享/项目存档）。

## 注意事项
- 不要在这里引入 UI 层依赖，保持引擎层纯净。
- 默认不吞错；异常应直接抛出，由上层统一处理与提示。
- 对外 API/语义变更需同步更新相关测试（尤其是 `tests/resources`、`tests/ui`）与 `engine/resources/claude.md` 的“当前状态”描述。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。


