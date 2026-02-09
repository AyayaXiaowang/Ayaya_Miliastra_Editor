# App/Common

## 目录用途
存放可被 `app.models` 与 `app.ui` 共享的轻量级工具模块，确保无 PyQt 依赖，用于封装跨层通用的数据结构与缓存。

## 当前状态
- `in_memory_graph_payload_cache.py`：**进程内临时**的节点图 payload（`graph_data`）缓存，提供按图根 ID/图 ID 组合键存储、基于 `detail_info` 的解析入口（`graph_data`/`graph_data_key`），以及按图根/按图 ID/全量清空的失效函数；应用层统一通过 `app.runtime.services.graph_data_service.GraphDataService` 桥接，避免多入口读写/失效导致分叉。
- `github_update_checker.py`：纯 Python 的 GitHub Release 更新模块：仅保留 `latest_release_version`（本地版本号 vs 最新 Release tag）对比逻辑，并提供 Release assets 解析与更新检查所需的基础能力，供 UI 的“一键下载更新包”功能复用；不依赖 PyQt。
- `environment_checker.py`：运行环境检查（纯 Python）：用于 UI 的“检查环境”按钮，检测“千星沙箱”窗口是否存在、沙箱所在屏幕的分辨率/缩放是否在支持范围、以及本程序与沙箱进程的管理员权限是否匹配，并输出可复制的文本报告。
- `private_extension_loader.py`：私有扩展加载器（仅机制不含私有实现）：优先按用户设置（`settings.PRIVATE_EXTENSION_*`，落盘到 `app/runtime/cache/user_settings.json`，默认忽略不入库）。当前 `settings.PRIVATE_EXTENSION_ENABLED` 会在配置加载后被强制为 True（不再在设置页中展示开关）；当未提供 sys_path/modules 时，会自动扫描并加载工作区内的私有扩展目录：
  - 推荐：`<workspace_root>/private_extensions/<插件名>/plugin.py`
  - 兼容：`<workspace_root>/plugins/private_extensions/<插件名>/plugin.py`
  环境变量可临时覆盖；无插件/无配置时无副作用；导入失败直接抛出。
  - 注意：按文件路径加载时会先将模块写入 `sys.modules`（与标准 import 语义一致），避免 dataclasses/typing 等依赖模块注册表的逻辑失败。
- `private_extension_registry.py`：私有扩展钩子注册表（无 PyQt 依赖）：提供启动期/主窗口期钩子注册与触发点，供私有模块在导入/安装阶段注册。
- `private_extension_registry.py`：同时提供“UI HTML 自动转换”扩展点：私有扩展可注册 `register_ui_html_bundle_converter(...)`，由主程序在监听到项目存档 `管理配置/UI源码` 发生变化时触发转换，并将转换产物（bundle：UILayout + templates）写入管理配置的 UI 资源（UI布局/UI控件模板）。
- `private_extension_registry.py`：同时提供“私有 UI Web 工具插件启用标记”（与自动转换器注册解耦）：私有扩展可调用 `register_ui_tools_plugin_enabled()` 标记启用，用于 UI 侧门禁（展示 UI 相关分类/入口）；即使不注册 `register_ui_html_bundle_converter(...)`（禁用自动转换），仍可使用 Web 预览/手动导入导出工作流。
- `__init__.py`：占位以声明 Python 包。

## 注意事项
- 保持纯 Python 与轻量依赖，不得引用 UI/引擎中的重型组件。
- 模块需关注线程安全（缓存默认使用锁保护），并提供显式的清理/失效入口避免内存泄漏与布局更新后缓存失步。
- `app/ui` 与 `app/models` 不应直接 import `in_memory_graph_payload_cache.py`；如需读写/失效，请走 `GraphDataService`。
- 本目录描述仅聚焦“用途/状态/注意事项”，不记录操作历史。

