## 目录用途
`ui/main_window/package_events/` 承载 `PackageEventsMixin` 的拆分实现：按职责把“切包/保存、库页选中联动、归属写回、右侧面板协作”等逻辑拆成多个小 mixin，并由聚合入口 `ui/main_window/package_events_mixin.py` 组合继承以保持对外导入路径稳定。

## 当前状态
- **切包与保存**：`package_load_save_mixin.py` 负责项目存档切换、未保存提示与回滚、切包后 NodeRegistry/node_library 刷新，以及 watcher 监听作用域更新（共享 + 当前项目存档）。
- **库页选中联动**：`library_selection_mixin.py` 统一处理库页选中/取消选中与右侧面板收起。
- **PACKAGES 预览页**：`packages_view_mixin.py` 提供存档库页右侧预览与跳转（优先 `PackageView`，回退 `GlobalResourceView`），并保持“只读预览、不自动切包”的语义。
- **管理模式右侧面板**：`management_panels_mixin.py` + `management_panels_coordinator.py` 负责管理 selection → 右侧面板刷新编排，并保证 selection 单次解析，避免协议漂移。
- **归属与落盘**：`membership_mixin.py` / `resource_membership_mixin.py` 将“所属存档切换”统一视为移动资源文件到目标根目录，并同步当前包的内存索引与缓存失效；`immediate_persist_mixin.py` 负责脏标记与去抖增量落盘请求（区分“资源本体变化 vs 索引引用变化”）。

## 注意事项
- Mixin 之间只通过主窗口公开属性与 `main_window.app_state` 协作；避免互相反向 import 实现细节导致循环依赖。
- 本目录的 mixin 不直接读写磁盘；落盘统一交给 `PackageController` / `PackageIndexManager`。
- 对外入口保持在 `ui/main_window/package_events_mixin.py`；外部模块不要直接依赖本目录具体文件名。
- 右侧标签页显隐/切换统一通过 `RightPanelController` 表达意图，避免在 mixin 内直接操作 `side_tab` 或分散依赖 registry/policy。

