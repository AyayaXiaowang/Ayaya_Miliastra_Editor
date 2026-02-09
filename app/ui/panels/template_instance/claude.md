## 目录用途
`ui/panels/template_instance/` 收纳元件/实体属性面板的标签页子组件，每个标签独立维护 UI 与数据交互逻辑，便于 `TemplateInstancePanel` 仅负责装配与信号协调。

## 当前状态
- `basic_info_tab.py`：通用属性 Inspector（Common Attribute Inspector），作为“属性”标签页承载 **名字/GUID/类型** 以及 8 段 Accordion 模块（变换/模型/原生碰撞/可见性&创建/阵营/单位标签/负载优化/备注）。
  - 变换模块在实体摆放/关卡实体上下文可编辑 `position/rotation/scale`，并提供“锁定变换”开关（锁定后输入框禁用）；模板上下文展示提示文本。
  - 模型模块以“资源卡片”形式展示当前模型摘要，并按实体类型提供最小可用编辑入口：造物可从 `creature_models` 选择模型，物件支持输入模型名称，掉落物支持编辑模型ID；同时提供 **挂接点/装饰物** 编辑入口，统一写入 `metadata["common_inspector"]["model"]`：
    - `socket_editor_dialog.py`：挂接点编辑器（Unit Sockets + Custom Sockets）。
      - 单位挂接点：只读展示 `model.mountPoints: list[str]`；预览标记写入 `model.mountPointPreviews: list[str]`。
      - 自定义挂接点：编辑 `model.attachmentPoints: list[dict]`（`name/parentId/offset(x,y,z)/rotation(x,y,z)/showPreview`）。
    - `decoration_editor_dialog.py`：装饰物编辑器（Master-Detail 列表-详情）。编辑 `model.decorations: list[dict]`，每条包含 `instanceId/displayName/isVisible/assetId/parentId/transform(pos/rot/scale/isLocked)/physics(enableCollision/isClimbable/showPreview)`。
    - 说明：当前项目未接入 3D 视口，故“在场景选取/Gizmo 联动”不做实际渲染交互，仅维护数据结构与 UI 编辑能力。
  - 阵营/标签/优化/碰撞/可见性/备注等通用字段统一写入 `metadata["common_inspector"]`（结构与 UI 模块一一对应）；模板备注同时同步到 `TemplateConfig.description` 以保持列表/卡片等展示一致。
  - 折叠状态通过 `JsonCacheService` 记忆，下次打开保持用户折叠偏好。
- `vector3_editor.py`：可复用的 `Vector3Editor`（X/Y/Z 三轴输入 + 拖拽调节）组件，供属性面板与挂接点/装饰物编辑器复用，避免重复实现三维向量输入样式与交互。
- `combat_tab.py`：战斗标签页，为物件/造物模板与其实体摆放提供基础属性、仇恨配置提示、受击盒“初始生效”、战斗设置（不可元素附着/不可锁定/追踪点/特效引用）与能力单元入口；数据写入 `entity_config["battle"]` 段落，便于模板/实例对齐扩展配置。
- `graphs_tab.py`：节点图列表与暴露变量覆盖编辑，负责对接 `ResourceManager`、`PackageIndexManager` 与 `GraphSelectionDialog`，并向上游发射 `graph_selected` 信号；节点图增删及变量覆写统一委托 `TemplateInstanceService`，上下文列表通过基类 `_collect_context_lists` 汇总元件/实体摆放/关卡实体差异；图数据优先走共享的 `GraphDataService`/`GraphAsyncLoader` 缓存与线程池，错误与确认提示通过 `app.ui.foundation.dialog_utils` 封装的对话框函数展示；在元件/实体摆放属性面板中，处于“掉落物”上下文时整体会隐藏“节点图”标签页，如在其他场景单独复用本标签页，则内部仍以只读提示“掉落物不支持挂节点图”并禁用新增与修改能力；节点图列表支持工具条“+ 添加节点图 / 删除”按钮以及在列表上右键弹出“删除当前行”菜单项，删除操作仅移除当前对象上的引用，不会影响节点图库中的图文件本身；列表前缀使用“🔗 [继承]”标记模板来源节点图，使用“【额外】”标记仅挂在实体摆放或关卡实体上的节点图；下方“节点图暴露变量覆盖”区域复用 `TwoRowFieldTableWidget` 的两行结构表格（序号/变量名/数据类型/覆盖值），展示每个暴露变量的当前生效数值：当实体摆放/模板未设置覆盖时直接读取节点图内的默认值（包括列表/字典等复杂类型，按节点图变量编辑表格相同的展开样式展示），当用户在表格中修改数值时，仅当与默认值不同时才写入 `graph_variable_overrides[graph_id][var_name]`，将覆盖值以原始类型（字符串/列表/字典等）存储，用户将值改回默认值时自动清理对应覆盖条目，保证数据结构简洁。
- `variables_tab.py`：变量体系已收敛为“关卡变量代码定义 + 实例覆写值”：
  - 模板上下文：仅预览 `metadata["custom_variable_file"]` 指向的关卡变量文件（可为字符串或列表，支持多文件引用；只读展示变量名/类型/默认值），不在 UI 中新增/编辑变量定义（定义应在 `管理配置/关卡变量` 的 Python 文件中维护）。
  - 实例/关卡实体上下文：编辑 `InstanceConfig.override_variables`（`LevelVariableOverride`，按 `variable_id + value` 覆写值）。表格中“名字/类型”列固定锁定为只读，仅允许编辑“数据值”；继承默认值用浅灰底色表示，覆写值用浅蓝底色表示，额外覆写用浅绿底色表示。
  - 变量文件引用解析：优先按 `VARIABLE_FILE_ID` 匹配，兼容相对路径与文件名（不含扩展名）；解析逻辑集中在 `variables_external_loader.py`。
- 变量标签页相关组件拆分为：
  - `struct_list_editor_widget.py`：结构体列表变量的值编辑控件；
  - `variables_table_widget.py`：变量标签页专用的两行结构表格扩展；
  - `variables_external_loader.py`：按 `custom_variable_file` 引用解析关卡变量文件并返回 payload 列表。
  - 结构体下拉选项应使用当前上下文注入的 `resource_manager` 作用域（共享根 + 当前存档根）生成，避免在 `<共享资源>` 中混入其它项目存档目录的结构体定义造成“同名重复/归属错觉”。
- `components_tab.py`：通用组件标签页（Inspector 风格），区分元件继承与实体/关卡实体上的额外组件；主体为“可滚动组件卡片列表 + 底部固定【+ 添加通用组件】按钮”。添加入口弹出 `component_picker_dialog.py` 的 `ComponentPickerDialog`（带搜索），候选组件类型按当前对象推导出的 `entity_type` 以及 `engine.configs.rules.get_entity_allowed_components()` 过滤，掉落物上下文进一步收窄到“特效播放 / 碰撞触发源 / 铭牌”；为避免与变量体系冲突，组件选择器默认不提供“自定义变量”（本项目变量已独立为“自定义变量”标签页），若遇旧数据仍会在卡片中兼容展示并提示迁移。每张卡片提供折叠、菜单（删除/重置/复制/粘贴）与“详细编辑”展开区；继承组件在实体上下文中默认只读（禁用编辑与删除）。组件描述来自组件注册表 `COMPONENT_DEFINITIONS`；配置表单由 `component_form_factory.create_component_form()` 选择实现（背包/铭牌/选项卡），并通过 `on_settings_changed` 回调把表单变更去抖上抛到 `TemplateInstancePanel.data_updated` 落盘链路。
  - `component_form_factory.py`：仅保留“组件类型 -> 表单实现”路由，并统一接收 `on_settings_changed` 以把表单内的 settings 变更回传给上层面板。
  - `component_form_backpack.py` / `component_form_nameplate.py` / `component_form_tabs.py`：组件表单实现，优先使用 `ui/forms/schema_bound_form.SchemaBoundForm` 做字段绑定；内部在用户变更字段/增删配置时调用 `on_settings_changed`，避免“UI 已改但未触发去抖保存”的隐性问题。
- `tab_base.py`：提供 `TemplateInstanceTabBase`，统一各标签页的上下文注入/清理、依赖注入（服务、资源管理器与索引管理器）以及工具栏和通用布局构建；内置 `_collect_context_lists`、`set_service/resource_manager` 等辅助方法，避免每个标签重复管理状态或重复实现同样的集合聚合逻辑；额外提供 `is_drop_template_config()` 与 `_is_drop_item_context()` 辅助函数，用于判定指定元件或当前上下文是否属于“掉落物”类别，供各标签页按需调整 UI 与行为（例如隐藏节点图相关入口或收窄组件类型）。
- 所有标签页可按需实现 `set_read_only()`，由 `TemplateInstancePanel` 在任务清单等只读场景下统一切换为只读预览模式：外层仍可切换标签与更新上下文，但内部输入框与增删按钮会被禁用，避免在任务指引视图中误改真实资源。

## 注意事项
- 所有子组件通过 `set_context()` 注入 `current_object`/`object_type`/`package`，不要直接访问面板对象字段。
- 如需新增标签，请保持统一信号接口（`data_changed`、可选自定义信号），并在面板中集中转发。
- Tab 内部修改完数据后立即刷新自身 UI，保持状态与模型同步。
- 构建含增删操作的工具条时，优先复用 `TemplateInstanceTabBase._build_toolbar`，保持按钮顺序与样式一致。
- 各标签页中的提示文本、占位说明以及继承/灰显状态的前景色应统一复用 `ThemeManager.Colors` 中的文本/提示色 token（如 `TEXT_SECONDARY`/`TEXT_HINT`/`TEXT_DISABLED`），避免在 `setStyleSheet` 或 `QColor` 中直接写死灰度十六进制颜色，以便在暗色与浅色主题之间切换时保持可读性与对比度。
- 若需要输入弹窗（例如插入变量占位符等），统一使用 `app.ui.foundation.prompt_text/prompt_item/prompt_int`；消息框提示统一走 `app.ui.foundation.dialog_utils`。


