## 目录用途
`app/ui/panels/`：主窗口右侧属性/详情面板集合（元件/实体摆放、战斗预设、管理配置、界面控件组、Widget 配置等）。面板负责 UI 表单装配与字段读写，通过控制器/`ResourceManager` 写回资源。

## 当前状态
- 面板按领域拆分并复用 `PanelScaffold`、通用对话框与主题 token；复杂面板进一步拆成子包（如 `template_instance/`、`widget_configs/`、`combat/`、`peripheral_system/`）。
- 元件/实体面板的通用操作集中在 `template_instance_service.py`（组件/挂载图/变量覆写/GUID 等），并包含装饰物打散为元件模板的写盘辅助（通过 `ResourceManager.save_resource(..., resource_root_dir=...)` 直接落到当前项目存档目录）。
- 图相关面板与“图语义引用查看”等能力统一依赖 runtime 的 `GraphDataService` + 异步加载器，避免 UI 层各自维护 `GraphModel` 缓存。
- 支持只读预览场景（节点图库/项目存档预览等）：优先读取轻量元数据与缓存统计，不在单击阶段触发完整解析/自动布局。
- “所属项目存档/归属位置”收敛为单选根目录（共享/某 package_root），切换等价于移动资源文件；只读场景禁用移动。

## 注意事项
- 业务流与写盘不要散落在面板：涉及索引/移动/删除统一走 `PackageController`/`PackageIndexManager`/`ResourceManager`。
- 主题/字体/弹窗统一走 `ThemeManager` 与 `app.ui.foundation` 工具；不使用 try/except 吞错。
- 若需要运行期缓存/记忆状态，统一用 `app.runtime.services.*`（如 `JsonCacheService`），不要手写路径与 JSON 读写。
