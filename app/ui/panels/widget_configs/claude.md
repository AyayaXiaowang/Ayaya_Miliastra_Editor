## 目录用途
`ui/panels/widget_configs/` 存放 UI 控件类型化配置面板的实现，拆分为基类/共享字段部件以及按控件类型划分的子模块，避免再把所有配置写在单一文件里。

## 当前状态
- `base.py`：提供 `BaseWidgetConfigPanel`、字段绑定工具，以及 `WidgetConfigForm`、`VariableSelector` 等可复用输入部件；其中 `VariableSelector` 支持从关卡变量集合中选择变量并以 **中文 `variable_name`** 作为存储值；不再对旧展示文本（如 `name (variable_id)`、`name | ...`）或 `var_*` 形式的 `variable_id` 做自动归一化（输入即存储，最多去除首尾空白）。`WidgetConfigForm.add_key_mapping_pair` 为按键映射输入提供候选自动补全（0-9/A-Z/F1-F12 等）。
- `variable_picker_dialog.py`：变量库选择弹窗（带搜索与列表过滤），供 `VariableSelector` 的“选择...”按钮复用。
- `interaction_controls.py`：交互类控件（交互按钮、道具展示）配置面板；交互按钮支持大小与类型分支（交互事件/角色技能/使用道具）并按分支动态显示相关字段；道具展示面板按写回口径使用 `keybind_*_code`（**纯数字按键码**，写回到 `.gil` 的 item_display blob field_503/field_504）与 `组名.变量名` 形式的变量引用（`玩家自身/关卡/lv`），并包含“次数/数量（模板道具）/无装备时表现”等开关字段；道具展示的按键码输入提供 1..15（键鼠）/1..14（手柄）数字补全，并通过 tooltip 展示“奇匠按键”映射说明，避免把描述文本误写入配置。
 - `interaction_controls.py`：交互类控件（交互按钮、道具展示）配置面板；交互按钮支持大小与类型分支（交互事件/角色技能/使用道具）并按分支动态显示相关字段；道具展示面板按写回口径使用 `keybind_*_code`（**纯数字按键码**，写回到 `.gil` 的 item_display blob field_503/field_504）与 `组名.变量名` 形式的变量引用（`玩家自身/关卡/lv`），并包含“次数/数量（模板道具）/无装备时表现”等开关字段；为对齐“键鼠/手柄同号且同页≤14”的 Web 导入口径，道具展示按键码候选默认聚焦 1..14，并通过 tooltip 展示“奇匠按键”映射说明，避免把描述文本误写入配置。
- `textual_panels.py`：文本框、弹窗等文本展示类控件配置；文本框与弹窗内容均支持插入 `{{占位符}}` 形式的变量占位符；弹窗按钮列表支持增删改并写回 `settings["buttons"]`。
- `status_panels.py`：进度条、计时器、计分板等状态类控件；进度条颜色为固定枚举（绿/白/黄/蓝/红，对应统一色值 `#92CD21/#E2DBCE/#F3C330/#36F3F3/#F47B7B`），不再允许任意拾色；计分板支持 `player_bindings`（Player 1..N）表格绑定，每行一个 `VariableSelector`。
- `selection_panel.py`：卡牌选择器配置，使用折叠分组呈现“已知/未知/卡牌库”三块，并通过表格编辑器维护 `settings["cards"]`。
- `card_selector_editor_dialog.py`：卡牌库表格编辑器，对 `cards` 提供复制/粘贴/导入/导出/+新增行，并支持选择图片资源。
- `container_panel.py`：面板/容器类型的空配置面板（仅依赖通用字段，无额外 settings）。
- `registry.py`：集中维护控件类型到面板类的映射（含 `面板`）。

## 注意事项
- 新增控件类型时，应在对应子模块中实现面板，并在 `registry.py` 注册；尽量复用 `WidgetConfigForm` 的字段助手与变量选择器，保持交互一致。
- 如需额外的复合输入部件，请添加到 `base.py`，不要在各个面板内重复造轮子。
- 大多数字段应通过 `BaseWidgetConfigPanel` 的 `_bind_*` 方法读写配置字典；复合输入（如 `VariableSelector`）可直接使用 `_register_binding`。变量选择器写回的是中文名（`variable_name`），因此需要依赖“变量名全局/包内唯一”的约束与校验来避免歧义。
- PyQt6 的枚举/常量请优先从 `QtCore.Qt` 访问（例如 `QtCore.Qt.ContextMenuPolicy.CustomContextMenu`），不要使用 `QtWidgets.Qt`（在 PyQt6 下不存在）。

