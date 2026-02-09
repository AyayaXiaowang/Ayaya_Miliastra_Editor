# cache 子包

## 目录用途
负责与缓存相关的通用工具，包括运行时缓存路径定义与内容/结构指纹工具，为引擎和应用层提供统一的缓存约定。

## 当前状态
- `cache_paths.py`：集中定义运行时缓存路径（如图缓存、节点库缓存、资源缓存、验证结果缓存等），以及 UI 派生物缓存（`ui_artifacts/<package_id>/...`：ui_key→guid 注册表、UI 交互映射、UI 多状态映射、HTML bundle 等）；统一基于 `engine.configs.settings.settings.RUNTIME_CACHE_ROOT` 派生子路径（默认仍为 `app/runtime/cache`）。当 settings 已通过 `settings.set_config_path(workspace_root)` 初始化时，路径派生会优先使用注入的 `workspace_root`，避免误传 `workspace_path` 导致缓存跑偏到 `engine/app/runtime/cache` 等目录。
- `fingerprint.py`：通用指纹计算与图布局指纹工具，基于稳定 MD5 与邻域距离特征，为图缓存、节点匹配等场景提供可复用指纹算法。

## 注意事项
- 本目录只提供路径与算法工具，不负责具体文件读写；实际 I/O 由调用方模块实现。
- 如需调整缓存根目录，统一修改 `settings.RUNTIME_CACHE_ROOT`，不要在业务模块中另起一套路径常量。
- 指纹与路径工具应保持幂等和可预期，避免因实现细节微调导致频繁缓存失效或命中异常。

---
注意：本文件不记录修改历史，仅描述“目录用途、当前状态、注意事项”。请在结构调整后保持描述同步。

