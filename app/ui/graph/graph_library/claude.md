## 目录用途
节点图库子模块，将 `ui/graph_library_widget.py` 中的领域逻辑抽取为职责明确的 mixin，使主组件专注于 UI 装配与状态管理：

- `folder_tree_mixin.py`：文件夹树展示与基础交互（右键菜单挂载、展开状态缓存、目标文件夹选择等）；在非只读模式下支持新建/重命名/删除文件夹，以及拖拽移动节点图到目标文件夹。
- `graph_list_mixin.py`：节点图卡片列表（轻量元数据、排序/筛选、选中/双击/跳转）与图级资源操作（新建/复制/重命名/删除/移动到文件夹）。内建 `_graph_metadata_cache` 与卡片快照，避免重复调用 `load_graph_metadata()` 并在内容未变更时跳过 UI 更新；对会改写磁盘的操作会主动失效 UI 刷新签名，避免因资源库指纹基线延迟刷新导致“点击后无变化”的错觉。
- 图卡片列表支持增量刷新：`GraphListMixin` 复用现有 `GraphCardWidget` 并记录排列顺序，仅在资源增删或卡片信息发生差异时创建/销毁/移动 QWidget，避免大规模的重建与布局抖动。

主组件 `GraphLibraryWidget` 只负责：UI 装配、样式应用、信号绑定与基础状态（`current_graph_type/current_folder/current_sort_by/current_package`），并确保整页遵守“除了设置所属存档之外不允许落盘修改节点图”的约束。

## 当前状态
- 图库页支持统一快捷键与右键菜单：默认 `Ctrl+N/Ctrl+D/F2/Delete/Ctrl+M`，快捷键来源于 `KeymapStore`，可在“快捷键设置”中自定义并保存；若启用只读模式，则写入类动作会被禁用并提示仅可浏览。
- 只读模式下若触发“新建节点图”入口，会明确提示用户到 `assets/资源库/项目存档/<项目存档名>/节点图/` 或 `assets/资源库/共享/节点图/` 用 Python 文件维护图源码。
- `FolderTreeMixin` 的文件夹树为**扁平展示**：共享与当前存档目录同级，且始终 **当前存档优先、共享靠后**；共享目录及其子目录在每一层名称前显示 **`🌐`** 标记，避免用户把共享子目录误当成普通分类目录。
  - 条目数据键为 `(graph_type, folder_scope, folder_path)`，展开快照 key 使用 `graph_type:folder_scope:folder_path`，避免共享/存档同名目录造成展开状态串扰。
- `FolderTreeMixin` 会确保文件夹树始终存在一个“当前选中项”（优先匹配 `current_graph_type/current_folder`，否则回退到根目录），避免出现“左侧未选中目录但中间列表已经被目录过滤”的错觉。
- `GraphListMixin` 依赖 `_graph_metadata_cache` 与卡片快照做增量刷新，避免大图量下的重建抖动。
- **切目录无卡顿（两阶段刷新）**：`GraphListMixin._refresh_graph_list()` 先基于资源索引的 `graph_id -> file_path` 做“路径推断”（graph_type/folder_path/mtime），快速生成占位卡片并完成筛选/排序；随后启动后台线程 `GraphMetadataLoadThread` 逐个补全 docstring 元信息（可能触发 AST 解析），避免大图/多图在 UI 线程卡住。
  - 元信息补全完成后，若当前按 `name/nodes` 排序，会自动再排序一次，确保结果准确。
  - 刷新会维护 generation 并在切目录时 `requestInterruption()` 取消上一轮加载，避免旧目录的补全结果“串”到新目录。
- `GraphListMixin` 在刷新列表时会基于“资源库指纹 + 当前视图上下文 + (类型/目录/scope/排序)”生成刷新签名；签名未变时跳过全量枚举与排序，复用现有卡片与选中状态，降低跨页面切换时的卡顿。
- 打开节点图：`GraphListMixin` 在双击卡片时会启动后台线程 `GraphResourceLoadThread`（`graph_resource_load_thread.py`）加载 `ResourceManager.load_resource(ResourceType.GRAPH, graph_id)`，避免节点图解析/缓存命中/布局链路在 UI 线程阻塞；线程内会向“全局性能监控”记录 `graph.load_resource:<graph_id>` 耗时段，便于定位“缓存命中但仍然慢”的真实瓶颈；当 `selection_mode=True`（如图选择对话框）时，双击仅视为“选中 graph_id”，不会触发重度加载。
  - 若加载失败，提示信息会同时覆盖“文件缺失/损坏”与“节点图未通过校验（逻辑不合法）”两类常见原因，并引导用户查看控制台错误与运行 `validate-graphs/validate-file` 做自检。
- 图列表排序在任意排序方式下都会保持 **当前存档优先、共享靠后**（先按 `is_shared` 分组，再按选定的排序字段排序），避免共享条目“插队”造成误判。
- 当刷新后“原选中图已不在当前列表中”（外部删除源文件、切换视图范围过滤掉该图等），`GraphListMixin` 会清空选中并 `emit graph_selected("")`，确保右侧图属性面板回到空状态，避免继续加载已不存在的源文件。
- `GraphListMixin.select_graph_by_id(...)` 支持按需控制是否同步目录筛选：默认会切换 `current_folder` 聚焦到目标图所在文件夹；在启动会话恢复等场景可关闭该行为，仅恢复类型切换与卡片选中。
- 当前项目存档视图下，文件夹树与图列表会按资源根目录过滤：仅展示“共享 + 当前项目存档”下的节点图与目录结构，不会把其他项目的目录混进来；共享资源视图（`global_view`）下仅展示共享根目录。
- 当前包视图下若列表混入共享节点图，`GraphListMixin` 会在卡片数据中标记 `is_shared=True`，由 `GraphCardWidget` 显示“共享”徽章，确保用户能一眼区分共享资源与本项目资源。
- 支持 server/client 类型切换与全局/按包过滤，筛选结果与 `PackageIndex` 的索引保持一致。
- 路径与 folder_path 的文本归一化统一复用 `engine.utils.path_utils.normalize_slash`，避免 UI 内部散落 `replace("\\", "/")` 口径漂移。

## 注意事项
- 事件过滤器：`FolderTreeMixin.eventFilter` 负责文件夹树拖拽，主组件需在 `_setup_ui` 中 `self.folder_tree.viewport().installEventFilter(self)`；若基类顺序因继承结构无法使 mixin 先于 `QWidget`，mix-in 内已回退调用 `QtWidgets.QWidget.eventFilter`，确保拖拽逻辑与默认处理兼容。
- Folder tree 会保存“已展开的 `(graph_type, folder_scope, folder_path)` 集合”并对比快照，仅当文件夹结构发生变化时才真正重建；普通刷新会尽量恢复原有展开状态，而在切换节点图类型（`force=True`）时会忽略旧展开快照并自动展开整棵树，确保从 server 切到 client 时也能直接看到各级子文件夹。
- 展开状态恢复时需确保“服务器/客户端”根节点保持展开：根节点不参与 key 快照（folder_path 为空），若根节点折叠会造成“只有根目录、子文件夹都不见了”的错觉。
- 异常处理：遵循 UI 目录约定，不使用 try/except；异常直接抛出。确认/警告等需要用户决策的提示统一通过标准对话框或 `ConfirmDialogMixin` 处理，而文件夹删除成功等非关键状态反馈则使用 `ToastNotification.show_message()` 在窗口右上角短暂展示，不打断后续操作。
- 上下文菜单：统一使用 `app.ui.foundation.context_menu_builder.ContextMenuBuilder`，不要内联 QSS。
- 资源读写：仅通过 `ResourceManager` 读写图与文件夹信息；图列表加载使用 `load_graph_metadata()` 的轻量路径，避免执行节点图代码；对节点图包归属的修改统一委托右侧图属性面板中的 `PackageMembershipSelector` 和 `PackageIndexManager`，不在本子包中直接改写索引文件。
- 依赖：不引入主窗口或编辑器控制器引用；与外部交互统一通过 `GraphLibraryWidget` 的信号（`graph_selected/graph_double_clicked/jump_to_entity_requested`）。
- 资源访问：统一使用 `engine.resources.*`（`PackageView/GlobalResourceView/GraphReferenceTracker`）。
- UI 卡片：图卡片渲染统一来自 `app.ui.graph.library_pages.graph_card_widget.GraphCardWidget`，不要在 mixin 中定义平行实现；卡片上的“变量/编辑”等按钮在图库视图中为只读展示或禁用状态。
- 固定提示控件：图列表 layout 顶部可能插入“加载中提示”等固定 widget；`_reorder_graph_cards(...)` 需要跳过这些固定项，避免 reorder 把卡片插到提示之上。
- 提示与确认：`GraphListMixin` 通过 `ConfirmDialogMixin` 的 `confirm/show_warning/show_error` 暴露统一入口，不再直接散落 `QMessageBox` 调用；`FolderTreeMixin` 中的“删除文件夹成功”等操作采用右上角的 Toast 通知替代阻塞信息框，保持删除流程轻量、可连续操作。


