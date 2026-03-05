## 目录用途
`app/common/` 存放可被 `app.models` 与 `app.ui` 共享的轻量级纯 Python 工具模块（无 PyQt 依赖），用于封装跨层通用的数据结构、缓存与环境探测能力。

## 当前状态
- **缓存与策略工具**：`in_memory_graph_payload_cache.py`（进程内 graph_data 缓存，应用层通过 `GraphDataService` 统一桥接）、`pagination.py`（懒加载分页目标计算）、`selection_restore_policy.py`（列表刷新后选中恢复决策）。
- **资源级纯逻辑**：`decorations_merge.py` 提供“装饰物合并”纯逻辑（keep_world 以 TRS 矩阵计算保持世界位置不变，并尽力保持旋转/缩放；父级 scale 优先读取 `InstanceConfig.metadata["ugc_scale"]` 以兼容 `.gia` 导入/写回口径），供元件/实体摆放等页面复用；`trs_math.py` 提供轻量 TRS 矩阵数学（Unity ZXY 欧拉约定）供合并/变换类逻辑复用。
- **环境与更新检查**：`environment_checker.py` 输出可复制的运行环境检查报告；`github_update_checker.py` 提供 Release 版本对比与 assets 解析能力，供 UI 更新流程复用。
- **私有扩展机制**：`private_extension_loader.py` 按用户设置与约定路径加载私有扩展（支持环境变量 `GRAPH_GENERATER_PRIVATE_EXTENSION_DISABLED` 一键禁用，用于救援启动）；`private_extension_registry.py` 提供启动期/主窗口期钩子与 UI Web 工具/HTML bundle 转换等扩展点（无 PyQt 依赖）。
  - 配置示例使用占位符路径，不在源码中写死本机盘符绝对路径。

## 注意事项
- 保持纯 Python 与轻量依赖，不得引用 UI/引擎中的重型组件或引入顶层副作用。
- 缓存类模块需考虑线程安全与显式失效入口，避免内存泄漏与刷新后缓存失步。
- `app.ui` / `app.models` 如需节点图 payload 缓存读写，统一走 `app.runtime.services.graph_data_service.GraphDataService`，不要直接 import `in_memory_graph_payload_cache.py`。
