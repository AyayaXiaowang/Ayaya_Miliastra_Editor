# 目录用途

关卡变量（Level Variables）代码资源根：本项目以 `自定义变量注册表.py` 作为单文件真源，Schema 从注册表派生虚拟变量文件。

## 当前状态

- 仅保留 Python 代码级定义（不维护同名 JSON）。
- 子目录区分普通自定义变量与局内存档变量：`自定义变量/`、`自定义变量-局内存档变量/`。
- `自定义变量注册表.py` 作为“统一声明入口”，收敛玩家变量与关卡实体变量声明；第七关对局变量（`ui_battle_money/ui_battle_score/ui_battle_moneyd/ui_battle_scored/ui_battle_rank/ui_battle_choice/ui_battle_integrity/ui_battle_i_min/ui_battle_i_max/ui_battle_integrityd/ui_battle_survival/ui_battle_s_min/ui_battle_s_max/ui_battle_survivald`）、结算页左栏文案变量（`ui_settle_i_st/ui_settle_s_st/ui_settle_ev1/ui_settle_ev2`）、选关预览变量（`ui_preview_entity_1/2`）以及 UI 关卡字典变量（如 `UI战斗_文本/UI结算_文本/UI房间_文本/UI选关_*`）均在注册表维护，作为 Schema 单一真源。
- `自定义变量注册表.py` 的 `owner` 直接填实体/元件 ID 或 `player`/`level` 关键字（支持列表形式多 owner）；第三方变量直接填 `instance_id`/`template_id`（例如 `owner="instance_boleshiqin_level07_relatives_data_store__测试项目"`）。
- UI 字典变量的键集合以 `default_value` 为真源；不再维护 `metadata.ui_defaults_managed_keys` 这类“受管理 key 列表”字段，避免重复信息与维护负担。
- 普通自定义变量文件不再落盘：当注册表存在时，`自定义变量/` 目录下的散落变量文件被明确禁止（会在校验中 fail-fast），避免多处真源漂移；变量文件引用统一使用注册表派生的稳定 `VARIABLE_FILE_ID`：`auto_custom_vars__{level|player|data}__测试项目`。
- 字符串锁变量默认值统一使用哨兵 `"无"`（例如 `选关_投票倒计时_模式`、`第七关_门_关闭完成后待办`），与节点图清锁口径一致，减少绕路启动的锁判定风险。
- 本目录不放置独立校验脚本；校验统一走 `python -X utf8 -m app.cli.graph_tools validate-project --package-id 示例项目_第七关` 或 `python -X utf8 -m tools.validate_level_variables --package-id 示例项目_第七关`。

## 注意事项

- 不要在 `自定义变量/` 目录新增变量文件；请只修改 `自定义变量注册表.py`。
- 项目存档通过“变量文件 ID 列表”引用整组变量；玩家模板通过 `metadata.custom_variable_file` / `metadata.ingame_save_variable_file` 选择变量文件。
- 局内存档变量的 `variable_name` 必须遵循 `玩家槽位_chip_序号`；普通变量禁止引用存档结构体。
- 字典变量类型应使用 **typed dict alias**（例如 `字符串-整数字典`、`字符串-字符串字典`）；默认值只允许一层键值表，复杂结构用结构体（或结构体列表）建模。
  - `字符串-整数字典`：default_value 的 value 必须可转成整数（例如 `1` 或 `"1"`）；若是中文文本/任意字符串，请使用 `字符串-字符串字典`。