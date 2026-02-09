## 目录用途
`app/ui/graph/library_pages/` 存放各类“资源库/列表类页面”（节点图库、元件库、实体摆放、战斗预设、管理配置库、项目存档页等）的 PyQt6 实现。
这些页面通常复用 `DualPaneLibraryScaffold` 与通用 Mixin（搜索、工具栏、确认弹窗、选中恢复等），并与主窗口右侧属性/详情面板联动。

## 当前状态
- **统一布局范式**：搜索框挂在标题行 actions 区；主操作按钮行位于标题下方；主体多为“左侧分类树/列表 + 右侧列表/详情/堆栈”。
- **统一选中协议**：库页实现 `LibraryPageMixin`（`set_context/reload/get_selection/set_selection`），并通过 `notify_selection_state(...)` 让主窗口集中控制右侧容器显隐。
- **资源视图约定**：库页上下文只区分 `PackageView`（具体项目存档）与 `GlobalResourceView`（共享资源视图，`global_view`）；不再提供“未分类视图”入口，避免跨项目资源混看。
- **复制（派生）能力**：元件库 / 实体摆放 / 战斗预设页面均提供“复制”入口，用于基于现有资源快速派生变体；复制会生成新的业务 ID，名称追加“ - 副本”，并默认清空 GUID（若存在）以避免重复 GUID 导致校验失败或引用歧义。
- **项目存档页（预览 vs 切包解耦）**（`package_library_widget.py`）：左侧项目存档列表的**选中仅用于预览**，不再自动触发主窗口切包；仅当用户点击“切换为当前”或双击条目时，才会发出 `package_load_requested(package_id)` 由主窗口在 `ViewMode.PACKAGES` 下执行切包保护入口。
  - 右侧详情树默认折叠，仅展示“分类 + 计数”；展开分类节点时再懒加载前 N 条（末尾提供“加载更多”占位）。
  - 预览内容来源于**磁盘扫描（共享根 / 目标项目存档根）**，不依赖 `ResourceManager` 当前作用域，避免“预览其他存档时资源列表为空”的串包错觉。
  - 右侧详情树双击节点图条目时，图资源加载改为后台线程（避免 `load_resource(ResourceType.GRAPH, ...)` 阻塞 UI），加载完成后再发出 `graph_double_clicked(graph_id, graph_data)` 交由主窗口打开编辑器。
- **管理配置在存档预览中按“共享 + 项目”合并展示**：当预览某个具体项目存档时，`管理配置/*`（含结构体定义/信号/关卡设置等）会将共享根与项目根下的条目合并后计数与列出，避免“项目目录未放定义文件但实际可用共享定义”的误解；UI 工作流不再以“管理配置资源”形式维护（HTML 为真源，派生物入运行时缓存），因此预览树不再展示 `UI页面/UI布局/UI控件模板` 等资源桶。
  - 管理配置条目在树节点中会同时携带：
    - **binding_key**（PackageIndex.resources.management 的资源桶 key，用于右侧摘要与所属存档）
    - **jump_section_key**（管理页面 section_key，用于双击跳转）
    从而避免“桶 key / section_key 不一致”导致跳转失败或标题覆盖的问题（例如 `timers → timer`、结构体定义按类型拆分等）。
  - 结构体定义在项目存档页中按 payload 的 `struct_ype/struct_type` 拆分为“基础结构体定义/局内存档结构体定义”，与管理配置库页面保持一致。
  - 项目存档页提供“复制”入口：将当前选中的项目存档目录复制为新的项目存档目录，并默认切换到新项目存档继续编辑。
  - 项目存档页提供工具栏扩展入口（用于私有扩展注入工具按钮/状态控件而不触碰内部 layout）：
    - `PackageLibraryWidget.ensure_extension_toolbar_button(...)`
    - `PackageLibraryWidget.ensure_extension_toolbar_widget(...)`（例如注入进度条/状态指示器）
- **管理配置库**（`management_library_widget.py`）：左侧扁平管理类型列表，右侧 `QListWidget` 展示条目；条目变更通过 `data_changed(LibraryChangeEvent)` 上报主窗口持久化。
  - **代码级只读类型**：`signals` / `struct_definitions` / `ingame_struct_definitions` / `save_points` 在库页禁用“新建/删除”，UI 仅用于浏览与维护所属项目存档关系。
  - **作用域一致性**：信号/结构体等代码级资源的列表展示遵循当前 `ResourceManager` 的索引作用域（共享根 + 当前项目存档根）；在 `<共享资源>` 视图中不会混入其它项目存档目录下的定义。
  - **结构体列表读取入口**：`StructDefinitionSection` 提供 `_load_struct_records(resource_manager)` 统一读取当前视图可见的结构体记录；资源库刷新流程可调用 `_invalidate_struct_records_cache(resource_manager)` 触发失效（当前为空实现，用于兼容与预留扩展）。
  - **重名消歧**：结构体列表默认仅展示 `struct_name`（或 `name`）；仅当当前视图内出现“同名结构体”时，才在显示名中附带 **短后缀**（从 `struct_id` 去掉重复前缀后提取），避免 `名字（完整ID）` 过长且重复；完整 `struct_id` 会在 tooltip 中以 `ID: ...` 展示，便于复制与排查。
- **局内存档结构体列表行构建**：`InGameSaveStructDefinitionSection._build_row_data` 与基础结构体行构建保持一致的签名（支持 `base_name/needs_disambiguation`），并在此基础上额外展示“列表字段数量/长度摘要”，同时保留 `ID` 字段用于排查与复制。
  - 右侧列表条目会按物理资源根目录标注归属：当条目位于共享根目录时显示 **“共享”徽章**（与节点图库一致），并在 tooltip 中补充“归属: 共享（所有项目存档可见）”。
  - **关卡变量模板**（`management_section_variable.py`）：按 `VARIABLE_FILE_ID`（变量文件 ID）作为条目主键分组展示，避免以源路径作为不稳定键；右侧详情表格展示该文件内的 variable_id/默认值/描述等，只读。
- UI Web 工作台入口（如有）应以 **HTML 源码目录** 为入口：PyQt 页面只负责跳转/打开，不维护任何 UI 派生资源文件。
- **战斗预设库**（`combat_presets_widget.py`）：分类树切换到“职业/技能/投射物/单位状态/道具”等视图时，列表刷新不会再因为“当前列表不包含玩家模板条目”而清空有效选中；仅在“全部/玩家模板”视图下以玩家模板作为默认选中锚点，保证右侧战斗详情面板联动稳定。
  - 删除语义与元件/实体一致：在 `PackageView` 下“删除”表示**从当前项目存档移出**（移动到默认归档项目，不物理删除资源文件）；在 `GlobalResourceView` 下为**全局物理删除**（删除共享资源文件）。删除前会给出“可能被哪些战斗预设条目引用”的提示，降低误删成本。
- **节点图库**（`graph_library_widget.py`）：支持按类型/文件夹/排序浏览；主窗口只读挂载时禁用会改写节点图结构或文件夹的按钮。
  - 节点图库页同样提供工具栏扩展入口（用于私有扩展注入“导出/分析”类按钮或进度控件）：
    - `GraphLibraryWidget.ensure_extension_toolbar_button(...)`
    - `GraphLibraryWidget.ensure_extension_toolbar_widget(...)`
  - 切换项目存档/共享视图时会重置目录筛选并强制刷新文件夹树，避免沿用旧 `current_folder` 造成“左侧看似在根目录但列表仍被旧目录过滤”的错觉。
  - 模式切页轻量刷新：提供 `GraphLibraryWidget.refresh_for_mode_enter()`（不强制失效 UI 快照缓存），供主窗口在进入 `GRAPH_LIBRARY` 时做“按需增量刷新”，避免每次切回节点图库都全量重建目录/卡片导致卡顿；需要强制全量刷新仍使用 `reload()`。
  - 列表卡片（`graph_card_widget.py`）仅展示名称/类型/修改时间/描述/引用等概览信息；当节点图位于共享根目录时会额外显示 **“共享”徽章**，避免在“当前项目视图”下混入共享资源后产生误解；**节点数量/连接数量**统一在右侧属性面板的“基本信息”中展示。
  - 启动会话恢复仅恢复“选中图”的卡片焦点，不会隐式切换目录筛选；文件夹树会默认选中根目录，避免出现“列表被收窄但左侧无选中目录”的误解。
- **元件库/实体摆放共享标记**：具体项目存档视图下列表会混入共享根目录资源，`template_library_widget.py` 与 `entity_placement_widget.py` 的列表项会与节点图库一致显示 **“共享”徽章**（由统一的 list delegate 绘制），并在 tooltip 中标注“归属: 共享（所有项目存档可见）”，降低“以为是当前项目存档私有资源”的误解风险；实体摆放列表允许实例未绑定/找不到元件（TemplateConfig）时仍可展示，类型回退读取 `InstanceConfig.metadata["entity_type"]`，并在 tooltip 中补充未绑定的 `template_id`。
- **变量体系收敛后的 UI**：元件库列表 tooltip 不再统计模板侧“默认变量”，改为展示模板 `metadata.custom_variable_file`（变量文件引用，支持单文件/多文件列表）；实体摆放“新建实体”对话框不再基于模板变量定义生成“初始变量值”输入区（变量定义与默认值以管理配置/关卡变量为准）。
- **统一快捷键与右键菜单**：元件库/实体摆放/战斗预设/节点图库四页统一提供快捷键与右键菜单项；快捷键来源于 `KeymapStore`（默认值如下，可在“快捷键设置”中自定义并保存）：
  - `Ctrl+N` 新建
  - `Ctrl+D` 复制
  - `F2` 重命名
  - `Delete` 删除
  - `Ctrl+M` 移动（元件/实体/战斗预设：移动“所属项目存档/归属位置”；节点图：移动到文件夹）
  - 元件删除前会提示“当前项目存档内哪些实体引用了该元件”，共享资源的全局删除还会额外提示跨项目存档的实体引用，减少“删完才发现一片悬空”的情况。
  - 快捷键作用域约定：库页快捷键均使用 `WidgetWithChildrenShortcut`，仅当焦点位于当前页面/列表范围内才会触发，避免 Qt 默认 `WindowShortcut` 造成跨页面“全局抢按键”。

## 注意事项
- 库页以“展示 + 发出操作请求”为主；原则上不在页面内散落写盘逻辑。
  - 例外：**归属位置变更/从项目存档移除/全局删除**属于资源管理操作，页面会通过 `PackageIndexManager`（移动文件）或 `ResourceManager`（物理删除）执行，并发出 `data_changed(LibraryChangeEvent)` 让主窗口触发去抖保存与联动刷新。
- 左侧树/列表不要使用 `setFixedWidth(...)` 锁死宽度：库页主体通常在 `QSplitter` 内，需要允许用户拖拽分隔线调整宽度；默认宽度请使用 `setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)` + `splitter.setSizes([...])` 设定初始值。
- 列表/树在删除、刷新或重建后不要继续使用旧的 Qt Item；应先缓存业务键/显示文本再重建。
- 颜色与样式优先使用 `ThemeManager` token，避免硬编码颜色值与平台字体名。

## 日志约定
- 列表选中变化属于高频 UI 事件，默认不向控制台 `print` 刷屏；需要排查时使用 `log_debug` 并通过 `settings.DEBUG_LOG_VERBOSE` 开关显式打开。

