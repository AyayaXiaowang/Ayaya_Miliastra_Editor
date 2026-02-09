# UI 控件模块

## 目录用途
- 存放节点图编辑器的常量编辑控件、节点图变量表格控件以及信号管理等专用 UI 控件。

## 当前状态
- **常量编辑控件** (`constant_editors.py`)：
  - `ConstantTextEdit`：文本/整数/浮点数输入框（支持类型校验）；在读取节点输入常量时，会将文本值严格等于 `"None"`（忽略首尾空白）的端口视为“未填写”，在节点图中显示为空文本，避免在 UI 上把占位用的 None 强行渲染为字符串。控件文本颜色使用 `ui/graph/graph_palette.py` 中的固定深色调色板（文本 `#E0E0E0`、输入框底色 `#2A2A2A`、边框 `#3A3A3A/#5A5A5A`），不随主题切换，保证节点图画布内联编辑的外观稳定。
    - 当端口名为 `变量名` 且节点标题包含“自定义变量”时（例如【获取/设置自定义变量】），若常量值为 `var_...` 形式的 `variable_id`，画布会自动映射为中文 `variable_name` 展示（tooltip 保留 `variable_id`），避免在 UI 中直接暴露 ID；用户编辑/选择该端口时也会尽量将输入归一为稳定的 `variable_id`（仅在可唯一解析时生效）。
    - 图所属实体常量 `self.owner_entity` 会在画布内联输入中语义化显示为“获取自身实体”（tooltip 保留 `self.owner_entity`），避免用户误以为它是普通字符串常量，且便于复制与排查。
    - `GUID` 类型端口支持右键菜单“选择 GUID...”，通过 `engine.resources.RefResolver` 构建项目存档的 GUID 派生索引并选择唯一 GUID 写回端口常量；若包内存在重复 GUID，会提示先通过校验修复后再选择（不提供“取第一个”的隐式策略）。在共享资源视图下会先要求选择一个项目存档作为上下文，再列举该存档内 GUID（避免跨项目存档重复 GUID 误选）。
    - 常见字符串端口名为 `变量名` 时支持右键菜单“选择自定义变量...”，从项目存档的关卡变量聚合视图（按存档引用过滤）中选择条目写回端口常量；当该端口属于“自定义变量”节点时会优先写入稳定的 `variable_id`，并在画布中以中文 `variable_name` 展示（tooltip 保留 `variable_id`）。若当前项目存档未引用任何变量文件，会提示先在管理配置里补齐引用。在共享资源视图下会先要求选择一个项目存档作为上下文，再列举该项目存档可用变量。注意：该入口会排除【设置/获取节点图变量】与部分【局部变量】节点，避免将运行时标识误写为外部变量名。
    - 节点图内联输入控件（布尔下拉/向量输入）的 QSS 与尺寸常量统一由 `app/ui/graph/graph_component_styles.py` 提供，避免在控件文件中重复拼装样式字符串。
  - `ConstantBoolComboBox`：布尔值下拉框（是/否）：
    - 固定宽度由 `app/ui/graph/graph_component_styles.py::GRAPH_INLINE_BOOL_COMBO_WIDTH_PX` 统一控制；高度使用 `minimumSizeHint()` 与字体度量兜底取最大值，避免 Win10/DPI 缩放或字体回退时出现裁剪；端口行的“上下留白/紧凑程度”由 `engine.layout.internal.constants.UI_ROW_HEIGHT` 决定（UI 与布局共用）。
    - QSS 来自 `app/ui/graph/graph_component_styles.py`：`drop-down` 子控件显式设置宽度与定位；`down-arrow` 显式 width/height 画三角形，避免在部分样式/DPI 下退化成方块导致“显示不全”。
  - 兼容输入常量的真实 Python 类型：初始化时支持 `bool/int/float/str`（例如 IR/解析写入的 `True/False`）；写回时统一写入 `bool`，避免布尔常量被字符串化导致类型推断漂移或 UI 崩溃。
  - `ConstantVector3Edit`：三维向量输入框（X/Y/Z 三个数值输入）：
    - 容器固定宽度 150，避免嵌入 `QGraphicsProxyWidget` 时默认尺寸过大导致内部控件被拉伸（尺寸常量收口在 `app/ui/graph/graph_component_styles.py`）。
    - 每个轴的子控件/标签使用 Fixed size policy，输入框数值强制左对齐，确保数值视觉上贴近左侧轴标签（不会看起来“靠向下一个轴”）；容器样式（`QLabel`/`QLineEdit`）同样来自 `app/ui/graph/graph_component_styles.py`，与 GraphPalette 保持一致。
  - `create_constant_editor_for_port`：根据端口类型（如"布尔值/三维向量/实体/结构体/泛型"）选择合适的编辑控件或不创建控件，作为 `NodeGraphicsItem` 与类型系统之间的轻量适配层；其中实体/结构体/结构体列表等仅允许连线，不提供行内常量编辑控件。
  - `resolve_constant_display_for_port`：将 `node.input_constants` 的原始值解析为“画布展示文本”（变量 ID→中文名、`self.owner_entity` 语义化、字符串 `"None"` 视为未填写等），供节点图在开启 `settings.GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED` 时进行占位绘制，避免为每个端口常量常驻创建真实编辑控件。
  - 行内控件虚拟化协作：在虚拟化开启时（`GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED=True`），`ConstantTextEdit/ConstantBoolComboBox/ConstantVector3Edit` 会在退出编辑（失焦/提交）后自动释放自身，配合节点图元的“按需 materialize”策略显著降低大图下 `QGraphicsProxyWidget` 数量与重绘开销。
- **表格 CRUD 基类** (`base_table_manager.py`)：`BaseCrudTableWidget` 统一封装"工具栏 + 搜索 + 表格"布局及启用/禁用逻辑，配合 `app.ui.foundation.dialog_utils` 可在任何派生控件内快速复用标准提示。
- **信号管理控件** (`signal_table_widget.py`)：基于 `BaseCrudTableWidget` 封装信号工具栏 + 表格 + CRUD，使用 `ThemeManager.table_style()` 和统一的调色板配置信号列表表格的行高/交替行配色；在对话框场景下默认使用 `SignalEditDialog` 作为参数维护入口，在管理面板中则可以切换为"外部编辑模式"，仅负责列表与搜索，将"新建/编辑"请求通过自定义信号抛给右侧详情面板的 `SignalEditorWidget`，同时通过 `app.ui.foundation.id_generator.generate_prefixed_id()` 派生信号 ID。
- **两行结构字段表格** (`two_row_field_table_widget.py`)：通用的字段表格组件，从结构体定义编辑器中抽取。采用两行结构（主行+详情行），实现"点击才能编辑"的交互逻辑：表格设置 `NoEditTriggers`，所有输入控件使用 `ClickToEditLineEdit`（`FocusPolicy=ClickFocus`）并通过 `app.ui.dialogs.table_edit_helpers.wrap_click_to_edit_line_edit_for_table_cell` 统一创建"QWidget + QVBoxLayout + addStretch"外层容器，点击单元格背景只选中行，必须显式点击输入框本身才能编辑；类型下拉框使用基于通用 `ScrollSafeComboBox` 的 `FieldTypeComboBox`，未聚焦时忽略滚轮事件避免误改，初始加载字段列表时会在内部关闭类型下拉的信号并整体禁用重绘，仅在批量插入完成后统一刷新行号与布局，以降低上百字段规模时的构建成本；列表/字典类型通过 `ListValueEditor`/`DictValueEditor` 的 `create_header_proxy()` 分离折叠按钮到主行，详情行显示完整子表格，子表格内部使用"尾部空白占位行 + 行级右键菜单"的方式完成元素/条目新增与删除，不再展示独立的"添加/删除"工具栏按钮；当调用方为"结构体 / 结构体列表"字段提供结构体 ID 列表时，数据值列使用 `ScrollSafeComboBox` 下拉选择结构体 ID，否则退化为可编辑的文本输入；支持右键删除、行级样式定制（只读/前景色/背景色/前缀），其中前景/背景色主要通过**序号列**的文字与底色表达字段来源状态，其余列保持统一卡片底色与控件只读样式，避免在嵌套输入框/子表格时出现只铺一小块的色块；表格自动行高调整，列宽策略上同时收窄"名字"和"数据类型"列，并将大部分剩余空间分配给"数据值"列，使长文本或复杂集合编辑时拥有更宽的编辑区域；基于 `ThemeManager.table_style()` 配置表格配色与 padding，让变量表格在模板实例面板、战斗玩家面板及结构体定义对话框中保持统一的卡片化视觉效果；当调用方通过工具条或其他入口显式新增字段时，表格会自动选中新插入字段的主行并滚动到可见区域，但批量加载或刷新字段列表仍保持当前位置不变。被结构体定义编辑器、节点图变量表格、实体/元件变量表格共同使用，保证交互一致性；当调用方传入的字段列表为空时，表格保持空白，由上层决定是否插入占位行，避免在"尚未配置任何字段/变量"时给出误导性的默认行；列头默认为"序号/名字/数据类型/数据值"，也允许调用方按需传入自定义列标题（仍固定为 4 列结构），以适配局内存档变量等仅需改列名而复用交互逻辑的场景；当字段为列表或字典且展开详情行时，会根据内联子表格的行数与表头高度动态放大详情行行高，目标是尽量让所有子项在父表格中完整展示，而不是依赖子表格自身的垂直滚动条；对于只读的结构体类型字段，会在数据值列右侧添加"查看"按钮，点击后发射 `struct_view_requested(struct_id)` 信号，由上层面板弹出 `StructViewerDialog` 以只读模式展示结构体定义详情；在 `set_value_mode("metadata")` 下支持“元数据模式”，此时字段 `value` 既可以是原始值，也可以是形如 `{"raw": Any, "display": Any}` 的字典，表格第四列仅展示 `display` 文本而在内部通过控件属性保留 `raw` 作为真实值，便于在局内存档变量等场景中以“结构体名称 + 最大条目数”等汇总文案取代表格编辑控件，同时仍可从表格读取精确的结构体 ID 或列表长度等数据；行高调试打印 `[UI调试/TwoRowField]` 默认关闭，可在“程序设置 → 输出与打印 → TwoRowField 行高调试打印”开启（对应 `engine.configs.settings.settings.UI_TWO_ROW_FIELD_DEBUG_PRINT`）。
  - 兼容“别名类型”（尤其是别名字典 `键类型-值类型字典` / `键类型_值类型字典`）：当从数据加载到不在基础类型下拉集合中的类型名时，会按行将该类型插入下拉框并选中，避免默默回退为默认类型导致误显示（例如回退成“实体”）；字典编辑器会据别名字典解析出键/值类型并在 UI 中展示为对应组合框默认值。
- **只读表格的清除按钮策略**：所有在表格单元格中使用 `ClickToEditLineEdit` 的输入控件，在被上层切到只读/禁用后会自动隐藏输入框右侧的清除（X）按钮，避免“禁止编辑”的表格仍出现可编辑暗示；恢复可编辑时按调用方对清除按钮的配置恢复显示。
  - 值列编辑控件的创建与取值逻辑已抽离到 `two_row_field_value_cell_factory.py`，表格类主要负责行结构、信号与装配编排。
  - 列结构：默认 4 列（序号/名字/数据类型/数据值），但允许调用方在“数据值”列之后追加少量额外列（例如勾选列），保持名字/类型/值列索引不变（1/2/3），以最小改动复用同一套两行结构与集合编辑器逻辑。
- **节点图变量网格** (`graph_variable_table_widget.py`)：基于 `BaseCrudTableWidget` 和 `TwoRowFieldTableWidget`，提供工具栏/搜索框 + 两行结构内联编辑；点击"+ 新建变量"直接在表格中添加默认字段（名称从"新变量"起，并在已存在同名变量时依次生成"新变量_1"、"新变量_2"… 以避免重复，类型默认"字符串"），用户在表格中内联编辑而非弹窗；变量类型来源于 `get_all_variable_types()`，支持基础类型、列表类型、字典及结构体类型；当上层传入结构体定义资源管理器时，“结构体 / 结构体列表”变量的数据值列会展示结构体 ID 下拉框，选项来自当前工程中已定义的结构体；列表/字典类型使用内联子表格编辑并支持折叠展开（详情行仅对这些集合类型可见，标量/结构体类型始终保持单行展示）；行高根据内容自动调整；搜索功能针对两行结构优化，只在匹配时显示主行并按需联动集合类型的详情行；在节点图库与图属性面板等只读视图中可以通过 `set_read_only_mode(True)` 切换为“只读浏览模式”：此时工具栏与搜索框会禁用，字段名/类型与子表格中的输入控件改为只读，但列表/字典的折叠按钮仍可点击展开以便查看复杂默认值；当前会显示“对外暴露”勾选列并写回 `GraphVariableConfig.is_exposed`；描述字段仍不在表格中展示，但会在写回时尽量保留原值。
- **内联表格编辑模板** (`inline_table_editor_widget.py`)：提供通用的“工具栏 + 表格”内联编辑骨架，支持通过 `InlineTableColumnSpec` 配置列标题与宽度策略，并统一表格的行高、交替行配色与调色板；顶部提供可配置文案的“添加 / 删除”按钮，内部通过信号 `row_add_requested` 与 `row_delete_requested(row_index)` 将行级新增/删除请求抛给业务层；右键菜单使用 `ContextMenuBuilder` 提供统一的“删除当前行”等行级操作，调用方只需连接删除信号并在外部维护行数据与持久化逻辑即可；对于嵌入表格单元格的行内控件（如 `QLineEdit`、`QComboBox`、`QSpinBox`），可通过 `attach_context_menu_forwarding` 将其右键事件转发到表格级菜单，使信号参数表格、局内存档条目表格等右侧属性区域在“添加 / 删除 / 右键删除当前行”等操作上复用同一套交互与样式；同时提供 `create_click_to_edit_line_edit_cell(row, column, text, placeholder, on_edited)` 辅助方法，使用 `ClickToEditLineEdit + wrap_click_to_edit_line_edit_for_table_cell` 为指定单元格创建“点击才能编辑”的标准文本输入单元格，并默认通过 `editingFinished` 触发回调，减少后续开发中遗漏这一交互约定的风险；对于需要在只读预览场景中完整展示所有行的表格（例如信号管理面板中的参数列表），可以在外层组件中结合当前行数和行高按需调整表格高度，并交由包裹它的 `QScrollArea` 负责整体滚动，从而避免表格内部再出现垂直滚动条。
- CRUD 表格支持增量刷新：Signal / 变量的新增、编辑、删除不再重建整张表格，直接更新当前行并复用 `dialog_utils` 提示，降低大数据量下的 UI 抖动。
- **节点图引用列表控件** (`graph_references_table_widget.py`)：封装“类型 / 名称 / 所属存档 / 操作”四列表格及说明标签，通过 `set_references(references, package_name_map)` 刷新内容；支持元件/实体/关卡实体以及战斗预设（玩家模板/职业/技能）等引用类型的统一展示与跳转；表格复用 `ThemeManager.table_style()` 并统一行高/调色板/交替行配色；操作列使用居中对齐的“跳转”文本单元格而非嵌套按钮，整列作为点击区域，在双击行或点击操作列单元格时发射 `reference_activated(entity_type, entity_id, package_id)` 信号，供节点图详情对话框与节点图属性面板等复用，保持引用列表的结构与跳转行为一致。
- **全局搜索 / 命令面板** (`command_palette_dialog.py`)：提供通用的 `CommandPaletteDialog` + `CommandPaletteEntry`，支持输入关键词实时过滤并在 Enter/双击后执行动作；由主窗口聚合跨页面跳转（元件/实体/战斗预设/节点图/管理项/项目存档），快捷键由主窗口通过 `KeymapStore` 绑定（默认 Ctrl+K / Ctrl+Shift+P / Ctrl+E，可自定义）。
- **快捷键面板** (`shortcut_help_dialog.py`)：提供 `ShortcutHelpDialog` + `ShortcutHelpItem`，以表格形式展示主要快捷键并支持搜索过滤；支持一键打开“快捷键设置”，并在保存后刷新展示内容。
- **快捷键设置** (`keymap_settings_dialog.py`)：提供 `KeymapSettingsDialog`，用于编辑并保存快捷键到 `<runtime_cache_root>/ui_keymap.json`，保存后立即生效。

## 注意事项
- 所有编辑控件在失去焦点时触发保存，并通过 `scene.on_data_changed` 触发自动保存
- 字体：需要显式设置字体时统一使用 `app.ui.foundation.fonts`（如等宽字体用于代码/数值对齐），避免硬编码 `Consolas` 等平台字体名导致跨平台缺字告警。
- 文本编辑框使用 `app.ui.foundation.debounce.Debouncer` 延迟布局操作，避免焦点切换时的界面跳转
- 控件 Z-order 设为 25，高于端口（20）和节点（10），确保可交互
- 使用 `TYPE_CHECKING` 避免循环导入 `NodeGraphicsItem`
 - 基于表格的控件（信号列表、变量编辑、两行字段表格等）在样式上优先复用 `ThemeManager.table_style()` 与统一的调色板配置，保证行高、配色与内联编辑 padding 一致；选中行默认使用浅色主题的 `BG_SELECTED` 纯色高亮，避免在复杂单元格内容上造成过强对比。

