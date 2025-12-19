## 目录用途
`ui/graph/library_pages/` 存放节点图库、元件库、实体摆放、战斗预设、存档库等“资源库/列表类页面”的具体 PyQt6 实现，这些页面通常以左右分栏或卡片列表形式呈现资源，并复用 `PanelScaffold` 及一组通用库页面 Mixin（如搜索过滤、工具栏、滚动与选中管理等）。

## 当前状态
- 已提供 `GraphLibraryWidget` 等节点图库页面，用于按类型、文件夹与存档视图浏览节点图，并通过只读模式限制节点图结构修改在代码侧完成。
- 各资源库页面依赖 `engine/resources` 提供的资源视图（如 `PackageView`、`GlobalResourceView`、`UnclassifiedResourceView`），只负责 UI 层筛选、展示与跳转，不直接持久化资源数据。
- 库页面通过 `LibraryPageMixin.notify_selection_state` 统一上报“是否有有效选中”，由主窗口通过 `right_panel.update_visibility()` 集中控制右侧容器的显示/收起，避免在各页面重复维护空选中处理或依赖主窗口私有方法名。
- 管理配置库（`management_library_widget.py`）的“选中摘要”通过 `selection_summary_changed` 信号上报给主窗口，避免依赖 `window()` + 反射调用主窗口钩子方法名。
- 元件库与实体摆放等“左树右列表”页面应优先复用 `standard_dual_pane_list_page.StandardDualPaneListPage` 构建 UI 骨架（搜索框 + 工具栏按钮行 + 左侧分类树 + 右侧列表），页面只保留业务差异逻辑以降低漂移风险。
- 节点图库卡片（`graph_card_widget.GraphCardWidget`）的“修改时间”优先使用轻量元数据提供的时间戳字段，避免在卡片渲染时对目录做重复的文件名 `glob` 扫描。
- 战斗预设页面在后台绑定包时不会强制选中玩家模板，仅在当前处于战斗预设模式或显式进入玩家编辑入口时才选中首个模板以驱动右侧详情。
- 局内存档管理在全局/未分类视图下以“代码级模板聚合视图”展示与维护默认模板状态；具体存档视图仅按 `resources.management["save_points"]` 过滤展示所属关系。

## 注意事项
- 新增资源库相关页面时优先放入本目录，并通过统一的脚手架与 Mixin 组装 UI，而不是在其他面板中重复造轮子。
- 页面内部若需要根据资源类型、文件夹或视图模式切换（例如节点图库的服务器/客户端节点图切换），应通过清晰的状态字段驱动列表与树形结构刷新，避免缓存快照与 UI 状态不一致。
- 字体：卡片/按钮如需显式设置字号或字体族名，统一使用应用级默认字体或 `app.ui.foundation.fonts`（emoji 图标字体同样按平台选择），避免硬编码 Windows 字体名导致 macOS 缺字体提示。
- 管理配置库的删除操作在发射 LibraryChangeEvent 时应携带当前列表项的 section_key 与 scope，保持主窗口持久化上下文完整。
- 战斗预设列表在发出选中信号前先清理其他战斗上下文，避免空选中回调将刚选中的右侧战斗详情面板收起，顺序应保持“先清理后选中”。

## 目录用途
`ui/graph/library_pages/` 存放所有“库/资源浏览”类页面组件，包括：
- `template_library_widget.py`：元件库页面（按分类浏览模板，支持搜索与只读预览）。
- `entity_placement_widget.py`：实体摆放页面（按存档与分类浏览实例与关卡实体）。
- `combat_presets_widget.py`：战斗预设库页面（玩家模板/职业/技能等分组列表）。
- `management_library_widget.py`：管理配置库页面（按管理类型聚合各类配置，并与主窗口右侧管理属性面板联动）。
- `management_section_*.py`：管理配置库中各具体 Section 的右侧列表语义与增删改逻辑实现，例如外围系统管理、计时器管理、变量管理等，仅负责列表枚举与基础操作，具体编辑表单与专用右侧面板由 `ManagementPropertyPanel` 或专用 Panel 模块承载。
- `graph_library_widget.py`：节点图库页面（按文件夹与类型浏览节点图，支持详情与跳转）。
- `package_library_widget.py`：存档库页面（按存档查看包含的模板/实例/节点图/战斗预设/管理配置等汇总信息）。

## 当前状态
- 主要库页面基于统一的脚手架与 Mixin（`DualPaneLibraryScaffold` / `SearchFilterMixin` / `ToolbarMixin` 等）实现“左侧分类/列表 + 顶部工具栏 + 右侧明细/堆栈”的布局范式；若出现仍手写 `QSplitter + SectionCard` 的页面，优先迁移到 `DualPaneLibraryScaffold.build_dual_pane()` 以降低布局漂移风险。
- 资源列表的刷新会尽量保留用户之前的选中状态，并在结果集为空时通过回调通知主窗口收起右侧属性或详情面板，避免展示失效上下文；无论是程序化选中还是用户点击列表条目，都会按约定驱动主窗口右侧的属性或专用详情面板同步当前上下文。
- 存档库页面右侧的“存档内容详情”树按视图模式展示：
  - 具体存档：列出关卡实体、模板、实例、节点图、战斗预设与管理配置等，并在叶子节点上附加资源 ID 与挂载节点图等元信息。
  - 全部存档/未分类视图：基于 `GlobalResourceView` / `UnclassifiedResourceView` 聚合展示所有或未纳入任何存档的资源。
- 管理配置库页面通过 `ManagementSectionSpec` 与 `BaseManagementSection` 体系，将原有的管理页面拆解成按类型划分的 Section，并统一以列表形式呈现，同时保留对尚未迁移页面的占位跳转能力。装备数据已按“词条/标签/类型”三个 Section 接入列表与专用右侧面板，依旧共享同一个 `equipment_data` 资源域。

## 注意事项
- 库页面仅负责 UI 与交互，不直接写回磁盘；资源持久化统一由上层控制器（`PackageController` 等）与 `ResourceManager` 负责。
- 新增库页面时，应尽量复用现有脚手架与搜索/过滤/确认对话框工具，保持交互风格与布局一致。
- 需要跨页面跳转（例如从存档库点击或双击某个条目跳转到具体编辑页面）时，优先通过主窗口或 `NavigationCoordinator` 提供的信号与槽完成，避免在库页面中直接操作其他模式页面的内部实现细节。
- 卡片、列表项以及管理 Section 内展示的颜色/徽标等 UI 颜色应优先使用 `ThemeManager.Colors` 提供的 token（如 `PRIMARY`/`SECONDARY`/`TEXT_SECONDARY`/`WARNING` 等），而不是在 QSS 或 `QColor` 中硬编码 `#RRGGBB`，以保证节点图库与管理库在暗色/浅色主题下的视觉一致性。

## 目录用途
`ui/graph/library_pages/` 存放以“资源库/列表视图”形式呈现的页面组件，例如节点图库、元件库、战斗预设列表、实体摆放列表和功能包库等。

- 这些页面通常具有如下特征：
  - 左侧为树或列表，右侧为详情或预览区域
  - 顶部带有统一样式的工具栏（新建/删除/筛选/搜索）
  - 支持筛选、排序与双击打开等交互

## 当前状态
- 节点图相关：提供节点图库与卡片视图，支持按功能包、文件夹和图类型筛选；在主窗口中以**只读库页面**挂载：禁止通过节点图库 UI 新建/删除/重命名/移动节点图或文件夹，也不允许从卡片按钮或变量对话框对节点图逻辑或变量进行落盘修改，唯一允许修改并写回的字段是各资源的“所属存档”，由右侧图属性面板顶部的 `PackageMembershipSelector` 统一承载并写入 `PackageIndex`。
- 元件与实体：提供元件库、实体摆放与战斗预设的浏览、筛选与跳转入口；`category_tree_mixin.EntityCategoryTreeMixin` 统一生成"全部实体/关卡实体/实体类型"树节点，其中“全部实体”始终位于根节点最上方，其次为“关卡实体”入口；元件库与实体摆放共用相同的分组与图标规则；实体摆放页的“全部实体”列表在基础实体实例之外，还会追加当前视图下的关卡实体条目（如存在），并在任意分类下都通过专用的 `level_entity_selected` 信号驱动右侧属性面板，以防被当作普通实体实例处理；元件库与实体摆放在完成增删改操作后会通过信号通知主窗口，由 `PackageController.save_package()` 立即将变更写入资源库与功能包索引；对外暴露的刷新入口为 `TemplateLibraryWidget.refresh_templates()` 与 `EntityPlacementWidget.refresh_instances()`，由 `PackageEventsMixin._on_data_updated()` 在属性面板数据变更后统一调用，保持右侧属性与列表视图一致；库页面在刷新列表时统一通过 `app.ui.graph.library_mixins.rebuild_list_with_preserved_selection` 实现“恢复原选中 / 列表为空时发出空选中信号 / 首条记录默认选中”的策略，当刷新后当前分类/存档中不再包含原选中对象但仍有其他条目时，会默认选中新的第一条记录并发出选中信号，让右侧属性面板自动切换到新的上下文；当刷新后当前分类/存档中完全没有任何可见条目时，则发出“空选中”信号，由右侧属性面板自行清空与隐藏，避免在新上下文下继续展示已失效的元件或实体属性。
- 元件库：`template_library_widget.TemplateLibraryWidget` 使用左右分栏结构展示"元件分类 + 元件列表"，左侧分类包括物件、造物以及扩展概念（元件组、掉落物）；顶部"新建元件"按钮会根据当前选中的分类动态调整文案（例如"+ 新建造物元件"），并在新建对话框中预选对应的实体类型；当实体类型为"造物"时，对话框会追加"模型"下拉框，模型选项统一来自实体配置子系统的造物模型枚举，模型选择为可选，不选择时视作尚未绑定具体模型；当实体类型为"物件"（包含从"掉落物"分类派生的物件）时，模型下拉框仅提供"空模型"一个选项且默认选中，用于显式标记"无具体模型"的情况；新建元件对话框内部将实体类型选择、模型枚举、掉落物特有字段与基础校验拆分为若干私有辅助方法，避免单个方法承载过多职责；元件列表的 tooltip 在显示类型、变量与组件统计信息的同时，会在"掉落物"分类下省略节点图计数，避免误导为可挂接节点图；元件列表项会根据 metadata.template_category 优先显示扩展分类的图标（掉落物 💎、元件组 🧩），扩展分类的图标与说明统一通过 `engine.graph.models.entity_templates.get_entity_type_info` 获取；在具体存档视图下，“删除”按钮仅移除当前存档索引中的模板引用而不会删除底层资源文件；在 `<全部资源>` 与 `<未分类资源>` 视图下，“删除”会委托资源层执行模板 JSON 的硬删除并从所有功能包索引中移除对该模板的包级引用，删除前会展示引用该模板的存档 ID 列表用于风险确认。
- 掉落物：元件库的新建对话框与元件详情页都提供“模型ID”数字输入框，仅接受非负整数，用于标记掉落物在资源与战斗系统中的模型编号，并在列表与属性面板中统一强调“不支持挂节点图”的约束；通过“掉落物”分类新建的元件会自动携带“特效播放”和“战利品”两个默认组件，便于后续直接配置掉落表现与掉落内容。
- 实体摆放：右侧使用 `QListWidget` 列表展示实体条目，按当前左侧实体分类树与搜索文本实时重建列表，布局与交互风格与元件库保持一致；每个列表项的主行仅展示“图标 + 实体名称”，实体类型、元件名、GUID、位置与旋转等信息统一下沉到 tooltip 与搜索聚合字段中，保证文件列表本身足够简洁；列表项会根据元件的 metadata.template_category 优先显示扩展分类的图标和类型名（掉落物 💎、元件组 🧩），扩展分类定义与元件库共享统一的 `get_entity_type_info` 数据源；左侧分类树始终包含“📍 关卡实体”入口，在具体功能包视图以及 `<全部资源>` / `<未分类资源>` 视图下均可点击，点击该分类时右侧列表仅展示单一的“关卡实体”条目，列表中的关卡实体条目使用与左侧分类相同的图标以保持视觉语义统一；“添加实体”按钮会在该分类下直接创建或聚焦关卡实体本体而不弹出元件选择对话框，右侧属性面板则以“关卡实体”上下文展示基础信息与组件/变量标签页，其中“所属存档”下拉通过 `PackageIndexManager` 统一约束“每个存档最多绑定一个关卡实体”，并隐藏已被其他关卡实体占用的存档选项；实体的名称、位置与旋转等可编辑字段统一在右侧 `TemplateInstancePanel` 属性面板中就地修改，实体列表不提供位置编辑弹窗按钮，双击条目仅用于改变选中状态。
- 功能包：功能包库页面以树形式展示功能包包含的资源，右侧详情的表头为“类别 / 标识/名称 / GUID / 挂载节点图”；对于元件和实例等资源，会通过 `ResourceManager.get_resource_metadata()` 提取 GUID 以及 `default_graphs` / `additional_graphs` 中声明的节点图ID，并在“GUID”列展示实体的 GUID，在“挂载节点图”列按“图名 (graph_id)”汇总展示所有挂载的节点图；根节点与各分类标题会附带数量统计（例如“元件 (3)”、“战斗预设 (5)”），并在标题栏展示当前视图的资源总数，方便快速评估存档规模。功能包库仍使用 `app.ui.management.section_registry` 中的管理配置映射构建整棵资源视图，与管理面板共用同一份元数据：
- 实体摆放：右侧使用 `QListWidget` 列表展示实体条目，按当前左侧实体分类树与搜索文本实时重建列表，布局与交互风格与元件库保持一致；每个列表项的主行仅展示“图标 + 实体名称”，实体类型、元件名、GUID、位置与旋转等信息统一下沉到 tooltip 与搜索聚合字段中，保证文件列表本身足够简洁；列表项会根据元件的 metadata.template_category 优先显示扩展分类的图标和类型名（掉落物 💎、元件组 🧩），扩展分类定义与元件库共享统一的 `get_entity_type_info` 数据源；左侧分类树始终包含“📍 关卡实体”入口，在具体功能包视图以及 `<全部资源>` / `<未分类资源>` 视图下均可点击，点击该分类时右侧列表仅展示单一的“关卡实体”条目，“添加实体”按钮会在该分类下直接创建或聚焦关卡实体本体而不弹出元件选择对话框，右侧属性面板则以“关卡实体”上下文展示基础信息与组件/变量标签页，其中“所属存档”下拉通过 `PackageIndexManager` 统一约束“每个存档最多绑定一个关卡实体”，并隐藏已被其他关卡实体占用的存档选项。
- 存档库：`package_library_widget.PackageLibraryWidget` 以左侧存档列表 + 右侧资源详情树的结构展示全部存档及其包含内容；右侧详情树按“类别 / 标识/名称 / GUID / 挂载节点图”四列呈现资源概览，其中“类别”列使用略宽的固定列宽以保证中文类别标题与计数完整可见；单击元件/实例/关卡实体/节点图条目会在主窗口右侧属性或图属性面板中以只读方式预览详情，单击“战斗预设”分组下的玩家模板/职业/技能条目会在当前模式下临时拉起右侧战斗详情面板（玩家模板详情 / 职业详情 / 技能详情）以方便联动浏览，单击“管理配置”分组下的条目会通过通用 `ManagementPropertyPanel` 在右侧展示只读摘要与“所属存档”多选行；双击元件/实例/关卡实体条目仍通过 `NavigationCoordinator` 或图事件处理器跳转到对应的编辑上下文：元件、实例与关卡实体会根据当前存档切换到元件库或实体摆放页面并选中目标条目，节点图则在节点图编辑器中以独立方式打开；“全部存档”“未分类存档”等聚合视图基于资源管理器的全局视图与“未归档视图”构建资源树，只聚合展示模板/实例/节点图与管理配置等资源，不再单独插入固定的“关卡实体：(无)”占位行，仍仅提供只读浏览和预览能力，不执行跨页面跳转。
- 功能包：功能包库页面以树形式展示功能包包含的资源，右侧详情的表头为“类别 / 标识/名称 / GUID / 挂载节点图”；对于元件和实例等资源，会通过 `ResourceManager.get_resource_metadata()` 提取 GUID 以及 `default_graphs` / `additional_graphs` 中声明的节点图ID，并在“GUID”列展示实体的 GUID，在“挂载节点图”列按“图名 (graph_id)”汇总展示所有挂载的节点图；根节点与各分类标题会附带数量统计（例如“元件 (3)”、“战斗预设 (5)”），并在标题栏展示当前视图的资源总数，方便快速评估存档规模。功能包库仍使用 `app.ui.management.section_registry` 中的管理配置映射构建整棵资源视图，与管理面板共用同一份元数据：
  - 分类标题与管理面板左侧树保持一致（通过 `MANAGEMENT_RESOURCE_TITLES` 复用中文标题），避免出现仅有英文 key 的文件夹；
  - 对于没有任何资源的管理分类，不在树中显示空文件夹；
  - 对于外围系统、货币背包、局内存档、关卡设置等按存档聚合的管理配置，在树中折叠为单条汇总视图：外围系统以所有成就/排行榜/段位条目的总数作为计数，不逐条展示 `pkg_*_peripheral_systems` 聚合资源；货币背包、局内存档、关卡设置等字段仅在存在非空配置体时显示，并以“已配置配置体数”作为计数；信号管理则基于 `PackageIndex.signals` 与代码级信号定义在“📡 信号管理”分类下逐条展示当前存档引用的各个信号，并允许通过双击跳转到管理模式下的信号 Section；底层聚合资源 ID 统一收敛到对应树节点的 tooltip 中（如有），上述聚合与计数与树节点构造逻辑集中收敛到 `management_tree_helpers.build_management_category_items_for_tree` 与 `PackageLibraryWidget` 内部的辅助方法，使 PackageLibrary 与管理面板在管理配置语义上共享同一份配置来源。
- 战斗预设：界面主文件依赖 `combat_presets/` 子模块提供分类与数据访问逻辑，接入 `DualPaneLibraryScaffold`，与元件/实例页使用同一套 SectionCard + 工具栏布局；`CombatPresetsWidget` 左侧使用“📁 全部 + 各预设类型”的分类树，右侧统一采用 `QListWidget` 列表视图浏览玩家模板、职业、技能、本地投射物、单位状态与道具等所有战斗预设类型；列表项通过 `TableRowData.user_data` 记录所属 Section 与条目 ID，新增与删除统一委托给对应 `BaseCombatPresetSection` 子类实现；点击“+ 新建”时，各 Section 会基于数据模型在当前存档下创建一条带默认值的战斗预设记录并直接落入列表中，不再弹出新建表单对话框，后续修改一律通过页面内的详情/编辑面板完成；为方便排查战斗预设增删落盘路径中的问题，`CombatPresetsWidget._add_item` 与各 Section 的 `create_item`、以及控制器写回索引的逻辑会在关键步骤打印带有 `[COMBAT-PRESETS]` 前缀的调试日志；当选中玩家模板条目时会发出 `player_template_selected` 信号，与右侧 `CombatPlayerEditorPanel`“玩家模板详情”面板联动完成就地编辑；当选中职业条目时会发出 `player_class_selected` 信号，与右侧 `CombatPlayerClassPanel`“职业详情”面板联动完成“战斗 / 技能 / 节点图”三页的结构化编辑；当选中技能或道具条目时分别发出 `skill_selected` 与 `item_selected` 信号，由主窗口右侧的 `CombatSkillPanel` 与 `CombatItemPanel` 提供结构化编辑入口；列表主行仅展示预设名称，类型与关键属性、最近修改时间等信息通过 tooltip 与搜索聚合字段提供，整体风格与元件库的“只看名字”文件列表保持一致；功能包库右侧“战斗预设”分组下的子分类标题与本页保持术语统一，分别使用“玩家模板 / 职业 / 单位状态 / 技能 / 本地投射物 / 道具”而不是 `player_templates` / `player_classes` 等内部 key；在设置当前存档或视图模式切换到战斗预设时，如列表中已存在有效选中条目，页面会通过选中信号或提供给主窗口的查询接口将当前 `(section_key, item_id)` 上下文同步给右侧战斗详情面板，确保首次进入或再次返回战斗预设模式时左侧选中状态与右侧详情始终对应。
- 管理配置库：`management_library_widget.ManagementLibraryWidget` 作为管理模式下的列表式入口，接入 `DualPaneLibraryScaffold` 与 `SearchFilterMixin/ToolbarMixin/ConfirmDialogMixin`，左侧使用**扁平的管理类型列表**（例如“信号管理 / 结构体定义 / 外围系统管理 / 计时器管理 / 技能资源管理 / 背景音乐管理 / 装备数据管理 / 关卡设置 / 路径管理 / 多语言文本管理 / 光源管理 / 文字聊天管理”等），不再额外展示“系统服务 / 界面与模板 / 关卡配置”这类父分组；左列在布局上采用 SectionCard 作为容器，并通过卡片内容边距控制让管理类型树在水平方向尽量与卡片同宽，避免分类树在容器内部显得过窄；右侧统一使用 `QListWidget` 展示当前类型下的管理条目，右侧卡片标题会根据当前选中的管理类型更新为对应的 `ManagementSectionSpec.title` 而不是固定文案；管理条目由 `BaseManagementSection` 子类提供统一的 `iter_rows/create_item/delete_item/build_inline_edit_form` 接口，其中通用类型集中在 `management_sections.py` 中注册，部分体量较大或复用需求较强的 Section 拆分到 `management_sections_base.py` + `management_section_*.py` / `management_extra_sections.py` 等子模块中，例如计时器、变量、外围系统、技能资源、背景音乐、装备数据、文字聊天以及单位标签（仅暴露“标签名称”和可选的数字索引ID）、护盾、扫描标签等；外围系统管理 Section 以“外围系统模板”为行粒度枚举配置，每个模板在右侧通过 `PeripheralSystemManagementPanel` 提供“排行榜 / 竞技段位 / 成就”三个标签页承载具体配置，“+ 新建”会一次性创建一个带默认名称与三类子配置骨架的外围系统模板，不再在库页面中弹出类型选择或字段编辑对话框；预设点管理 Section 会直接在列表中展示“名称 / 位置 / 类型 / 索引”等基础信息，并在摘要中标注被关卡出生点与复苏点引用的数量，新建时会立刻在当前存档下生成一个带默认名称与初始位置的预设点条目，后续通过主窗口右侧的就地编辑表单补充索引、旋转、单位标签等字段；结构体定义相关 Section 复用统一的字段解析与编辑数据结构，使管理库右侧结构体面板与旧版结构体管理页在字段列表格式与类型规范上保持一致；局内存档管理 Section 会在右侧属性面板中以“模板名称 + 启用开关 + 概要 + 条目表格”的表单布局就地编辑每个局内存档模板：顶部提供模板名称编辑框，中部通过启用开关与概要提示展示当前模板的启用状态与条目数量，下方条目表格以“无左侧标签的整块区域”单独占据一行，标题与表格垂直堆叠避免与其他字段并排，条目表格按内容高度完全展开并关闭内部滚动条，由外层面板滚动承担溢出；内部列统一包含“序号 / 对应结构体 / 长度 / 数据量”并直接写回 `entries` 列表，文本与数值类字段统一通过点击进入编辑模式的内联文本输入组件承载，避免单击行背景或滚轮操作就修改数据；条目表格使用统一的“工具栏 + 表格”内联模板构建工具条和右键菜单，既可以通过工具栏上的“删除选中”按钮删除当前行，也可以通过右键菜单的“删除当前行”动作完成行级删除；字段变更通过统一的内联回调合并写入视图模型，并再由主窗口管理事件 Mixin 在事件循环空闲时触发列表刷新与 `PackageController.save_package()` 持久化，避免在单个控件的信号回调中直接重建整块表单；当前仓库中的管理类型（除 `ui_control_groups` 特例外）均已接入上述 Section 体系，默认不会在右侧列表中生成“打开旧页面”占位条目，`_build_placeholder_items_for_section/_open_legacy_page` 仅作为向后兼容与未来扩展 section 的兜底机制保留；页面在完成增删改后通过 `data_changed` 信号通知主窗口立即持久化，并通过 `active_section_changed` 信号与右侧“界面控件设置`UIControlSettingsPanel`”标签联动；列表选中变化时会基于 `ManagementRowData` 聚合字段调用主窗口的 `_on_management_selection_changed(...)` 回调，优先通过各 Section 的 `build_inline_edit_form(...)` 在右侧 `ManagementPropertyPanel` 中构建就地编辑表单（例如计时器、变量、关卡设置、货币与背包、技能资源、背景音乐、装备数据、路径、多语言文本、光源、聊天频道、单位标签、护盾、扫描标签、商店模板、局内存档与实体布设组等），未提供内联表单的 Section（例如信号、结构体定义或使用专用面板的类型）则通过各自的专用右侧面板完成编辑；当无有效选中、当前 section 下没有任何条目时，主窗口会清空并收起对应标签，其中“界面控件组”仍由 `UIControlGroupManager` 提供完整编辑能力，仅作为某个管理类型的特例嵌入右侧堆栈；管理配置资源本体始终位于 `assets/资源库/管理配置/*/*.json`，功能包/存档仅通过 `PackageIndex.resources.management[...]` 的 ID 列表引用这些 JSON 作为“索引/标签”，Section 与页面在具体存档视图下编辑的是 `PackageView.management.*` 的视图模型，由 `PackageController._sync_management_resources_to_index()` 将其写回资源与索引，全局/未分类视图下的 `GlobalResourceView/UnclassifiedResourceView.management.*` 主要提供聚合浏览能力；多语言文本管理 Section 在右侧 `ManagementPropertyPanel` 中以内联表单方式编辑原文、来源、是否需要翻译、翻译内容和说明等字段，长文本输入区域随内容自然增高，并通过面板滚动区域承载超长文本，保持右侧属性栏在条目较少时依然紧凑而不出现单行控件被垂直拉伸至整块高度的情况。
- 关卡变量 Section 现为只读展示，变量定义来自 `assets/资源库/管理配置/关卡变量` 下的 Python 代码资源，按源文件聚合为“关卡变量模板”列表；右侧属性面板以无滚动表格一次性列出同一文件内的全部变量，单元格开启换行；支持通过顶部“所属存档”多选一次性勾选/取消该文件中的所有变量，使用情况会在表单上方显示引用该文件变量的存档列表；仍不支持在 UI 中新增/编辑/删除变量本体。
- 页面实现统一复用 `app.ui.graph.library_mixins` 中的搜索、滚动、确认对话框与工具栏挂载逻辑。
- 搜索输入统一挂在 `PanelScaffold` 标题行右侧（actions 区），作为页面级全局过滤入口；模板库、实体摆放、战斗预设与存档库均遵循这一布局，保证用户在不同页面始终能在相同位置找到搜索框。
- 工具栏按钮行通过 `ToolbarMixin.init_toolbar()` / `setup_toolbar_with_search()` 或 `toolbar_utils.apply_standard_toolbar()` 创建，主要承载“新建/删除/刷新”等主操作按钮，并布置在标题下方一行；含搜索的场景统一改为“标题行右侧搜索 + 标题下方按钮行”的两段式结构，复杂编辑入口更多通过右侧属性面板或专用详情面板就地完成，而不是在列表中弹出编辑对话框。
- 模板库与实体摆放页的表单对话框统一通过 `app.ui.forms.schema_dialog.FormDialogBuilder` 动态装配字段，包含必填校验与变量输入区域，避免重复声明 QDialog 子类。
- `graph_card_widget.GraphCardWidget` 支持 `update_graph_info()` 在不重新创建 QWidget 的情况下刷新内容，用于节点图库的增量刷新。
- `library_scaffold.DualPaneLibraryScaffold` 提供左右分栏的 PanelScaffold 模板，元件库、实体摆放、战斗预设与存档库页面已接入，分栏结构统一由 `build_dual_pane()` 创建，避免每个页面重复搭建 QSplitter 与 SectionCard。
- 元件库、功能包库与节点图库基于 `app.ui.panels.panel_scaffold.PanelScaffold` + `SectionCard`，标题、搜索与按钮行的位置和间距保持一致；功能包库右侧详情树（`detail_tree`）在全局 `tree_style()` 基础上额外使用“整行平头”高亮（去掉 item 圆角与行间距），以避免多列选中行的渐变在列交界处出现分段与缺口，选中渐变与文字颜色仍复用主题系统提供的配置。
- 删除类操作的成功反馈统一采用右上角的 Toast 通知（`ToastNotification.show_message`），仅在需要用户确认或提示失败原因时使用阻塞对话框，避免删除完成后打断连续操作。
- 为了统一主窗口与各库页之间的协议，`library_scaffold.py` 定义了轻量的 `LibraryPageMixin`、`LibrarySelection` 与 `LibraryChangeEvent`：
  - 所有库/列表页组件（节点图库、元件库、实体摆放、战斗预设、管理配置库与存档库）均实现 `set_context(view)` / `reload()` / `get_selection()` / `set_selection(selection)` 四个入口，主窗口与控制器通过这些方法在模式切换或导航跳转时统一刷新与恢复选中；
  - `LibrarySelection` 用于跨页面表达“当前选中对象”，包含 `kind`（如 `"template"` / `"instance"` / `"graph"` / `"combat"` / `"management"` / `"package"`）、`id` 与可选的 `context`（如 section_key、scope 等）；
  - `LibraryChangeEvent` 用于表达“库页内部发生了一次真实数据变更”，包含 `kind`、`id`、`operation`（create/update/delete/...）与可选 `context`；
  - 模板库、实体摆放、战斗预设与管理配置库在执行增删改操作后会发射 `data_changed(LibraryChangeEvent)` 信号，主窗口通过统一回调拉起 `PackageController.save_package()`，而不再依赖每个页面各自维护无参 `data_changed` 回调。
  - `context["scope"]` 的生成应统一使用 `library_view_scope.describe_resource_view_scope(...)`（package/global/unclassified），避免各库页自行判断视图类型导致语义漂移。
 - 统一选中事件（降低主窗口信号绑定耦合）：
  - 元件库、实体摆放与战斗预设页面已收敛为 `selection_changed(LibrarySelection | None)` 单一信号表达“当前选中对象”（无选中时发射 None），不再依赖多条 `*_selected` 信号与“空字符串表示清空”的隐式语义。
  - “无有效选中 → 收起右侧”的行为仍统一通过 `LibraryPageMixin.notify_selection_state(False, context={...})` 上报给主窗口（source=template/instance/combat）。
  - 库页对外只保留 `set_context/reload/get_selection/set_selection` 四个入口；不再提供 `set_package/refresh/get_current_selection` 这类旧入口，避免双真源与调用点分叉。

## 注意事项
- 页面内部尽量通过 mixin 或工具函数复用搜索、滚动定位与确认弹窗逻辑，避免重复实现；新增库页面应优先继承 `DualPaneLibraryScaffold` 并组合 `SearchFilterMixin` / `ToolbarMixin` 等基础能力，而不是在各自模块中重新搭建 `QSplitter` 和工具栏骨架。
- 资源的真实读写应交由资源管理器或控制器处理，页面仅负责展示与发出操作请求；当前实现中，模板库与实体摆放页在本地修改完成后，会发出“数据已变更”信号，由主窗口统一调用 `PackageController.save_package()` 落盘；节点图库与复合节点管理器页面则遵循“仅所属存档可写”的约束：所有节点图与复合节点的逻辑/变量/结构性修改在 UI 层均视为只读，真正的落盘仅限包归属关系。
- 保持各页面在工具栏布局、搜索框位置和基本交互模式上的一致性，提升整体体验；主窗口右上角的保存状态标签在进入节点图库与复合节点模式时会固定显示“当前页面不允许修改”，与图编辑器中的“已保存/未保存/保存中”状态提示区分开来，明确这些库页面的只读定位。
- 新增或改造列表/库页面时，优先沿用 PanelScaffold + SectionCard，左侧树/列表、右侧详情或卡片遵循统一间距与栅格。
- 扩展功能包库树视图时，优先复用 `_add_resource_section`、`_add_nested_resource_section` 这类工具方法，并在类级映射中登记资源类型，避免重复写遍历逻辑。
- 新建模板、实体实例等资源时，请通过 `app.ui.foundation.id_generator.generate_prefixed_id()` 生成 ID，保证跨页面一致性。
- 列表/库页面中临时的文本或类型选择输入（例如重命名存档、选择战斗预设类型）统一通过 `app.ui.foundation.input_dialogs` 构建带统一样式的输入对话框，而不是直接使用 `QInputDialog`。
- 节点图库中的卡片选中状态复用主题系统的主色系渐变高亮（背景渐变 + 高对比文字色），与导航栏/树/表格等组件的“选中高亮”保持一致，避免不同页面出现割裂的选中视觉。
- 渐变与绘制代码需遵循 Qt6 的类型约束（例如 `QLinearGradient` 使用坐标或 `QPointF` 重载，避免依赖 `QPoint` 的隐式转换），确保在 PyQt6 下不会因类型不匹配中断 `paintEvent`。
- 刷新模板库与实体摆放等列表页时，优先通过 `rebuild_list_with_preserved_selection` 统一处理“恢复原选中 / 首次选中 / 清空选中”三种场景，并在回调中使用封装好的发射函数区分关卡实体与普通实体，保证右侧属性面板与保存逻辑的行为一致。
- 局内存档管理在 `<全部资源>` / `<未分类资源>` 视图下通过聚合配置集中维护模板内容与启用状态，在具体存档视图（`PackageView`）下仅按 `resources.management["save_points"]` 过滤展示归属于当前存档的模板，并通过管理属性面板顶部的“所属存档”多选行维护包级归属关系；在包视图下点击局内存档 Section 的“新建/编辑/删除”会弹出提示，引导用户切换到全局或未分类视图中修改模板本体，避免在包视图中直接改写全局聚合配置。
- 列表/树等视图在执行删除、刷新或重建操作后，避免继续访问旧的 Qt 项目（如 `QListWidgetItem`、`QTreeWidgetItem`），需要在刷新前先提取并缓存用于提示或日志的显示文本或业务键值，再刷新 UI 或调用底层删除逻辑。
