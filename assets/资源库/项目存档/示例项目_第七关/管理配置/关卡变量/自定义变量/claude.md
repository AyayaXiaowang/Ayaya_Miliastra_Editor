# 目录用途

历史目录：曾存放“测试项目”的普通关卡自定义变量文件（Python 代码定义）。
当前项目已收敛为 `自定义变量注册表.py` 单文件真源，本目录应保持为空（不允许再放变量定义文件）。

## 当前状态

- 自定义变量统一在 `自定义变量注册表.py` 声明；Schema 从注册表派生虚拟变量文件（稳定 `VARIABLE_FILE_ID` 为 `auto_custom_vars__{level|player|data}__测试项目`）。
- 本目录下若存在任意 `.py` 变量文件，将在 `validate-project/validate-file` 中 fail-fast 报错（强制单文件真源，避免多处真源漂移）。
- UI 占位符变量通常以中文分组名组织（如 `UI房间_文本/UI战斗_文本/...`），要求 `variable_name` 与 HTML 中 `lv.<variable_name>.<key>` 完全一致。
- UI 字典类变量统一使用 **typed dict alias**（例如 `字符串-字符串字典`、`字符串-整数字典`），以便校验与导出链路准确感知字典 value 类型。
- UI 字典变量的键集合以注册表声明 `default_value` 为唯一真源；不再维护 `metadata.ui_defaults_managed_keys` 这类冗余字段。
- 工具链可能生成 `metadata.category=UI自动生成` 的变量文件用于对照/迁移；在本项目中此类文件不应落盘进入真源目录（应保持注册表为唯一声明入口）。
- 进度条等只接受标量变量名的绑定场景，应使用镜像标量变量（例如 `dict__key`），由节点图/工具同步写回。
- 第七关选关预览：玩家变量 `ui_preview_entity_1/2` 使用 `实体` 类型存放运行时预览元件引用，便于清理（创建元件通常没有可用 GUID）。
- 第七关对局：玩家变量 **压岁钱/积分拆分**：
  - 压岁钱：`ui_battle_money`（顶栏 HUD 展示），变化值 `ui_battle_moneyd`（揭晓面板）。
  - 积分：`ui_battle_score`（审判庭/排名/结算榜单 points），变化值 `ui_battle_scored`（揭晓面板）。
  - 顶栏资源：`ui_battle_integrity`（完整度）与 `ui_battle_survival`（手办存活数），变化值 `ui_battle_integrityd/ui_battle_survivald`。
  - 真实进度条 min/max：`ui_battle_i_min/ui_battle_i_max`（完整度，默认 0/100）、`ui_battle_s_min/ui_battle_s_max`（手办，默认 0/10），用于 UI 侧避免使用数字常量导致玩家模板变量缺失。
  - 结算左栏文案：`ui_settle_i_st/ui_settle_s_st/ui_settle_ev1/ui_settle_ev2`（字符串；每玩家独立），用于结算页左侧状态与评语。

## 注意事项

- 禁止在本目录新增/修改变量文件；请只修改 `自定义变量注册表.py`。
- 自定义变量名（`variable_name`）长度上限为 **20 字符**；超长会在 `validate-project/validate-file/validate-graphs` 中被视为错误并阻断导出/写回链路。
- 默认值禁止使用 `None`；会参与运算/比较的变量必须提供数值型默认值。
- 字符串锁变量默认值统一使用哨兵 `"无"`（例如 `选关_投票倒计时_模式`、`第七关_门_关闭完成后待办`），避免“默认值为空串但节点图按无哨兵清锁”造成绕路启动判定异常。
- 列表类变量若会按下标读取，应提供可安全索引的默认结构；注意节点图侧列表/字典元素数量存在上限，必要时拆分为并行列表。
- UI 字典占位符缺键应直接在 `自定义变量注册表.py` 补齐默认结构（唯一真源）；UI HTML 不再维护 `data-ui-variable-defaults` 作为真源，默认结构以 `自定义变量注册表.py` 为准。
- UI 展示型后缀（如 `%`）优先由 HTML 模板拼接：对应变量（例如 `UI战斗_文本.完整度`）建议存“纯数字字符串”，避免节点图侧拼接展示字符串。
