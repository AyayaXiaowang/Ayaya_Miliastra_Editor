# UI源码（示例项目_第七关）

## 目录用途

- 存放当前项目存档的 **UI 网页源码（HTML+CSS 静态稿）**，作为“千星沙箱网页处理工具 / UI源码预览（Web）”的输入源，用于预览、扁平化与导出/写回。

## 当前状态

- 每个页面为一个独立 `.html`：自包含 `<style>` 与 `data-ui-*` 标注（控件语义、变量绑定、交互键位、多状态等）。
- 页面内容以“可导出/可扁平化”为目标：预览 iframe 默认禁脚本，因此源码不依赖运行时 JS。
- `1.html` / `2.html`：对照/草稿页面（可能保留更激进的模板沉淀标注），主流程以具名页面为准。
- `__hook_tests__/`：用于 Cursor hooks（afterFileEdit / commit 前）校验的临时测试页面集合（包含“故意错/故意对”的最小 HTML），不参与实际 UI 流程。
- `关卡大厅-选关界面.html`：
  - `settle_tip_status` 文本使用 `lv.UI选关_文本.settle_tip_status` 绑定，便于节点图按运行态写回提示语。
  - 投票遮罩倒计时标题使用 `lv.UI选关_投票.countdown_label` 绑定，支持“进入关卡/结算”等多种倒计时场景复用同一套遮罩。
  - 顶栏标题/作者等文本显式标注 `data-ui-text-align="left"`（避免 Workbench 默认对齐推断导致扁平化预览对齐漂移）。
- `第七关-游戏中.html`：
  - 顶栏右上角剩余亲戚：显示值拆分为 `lv.UI房间_文本.剩余亲戚_当前` / `lv.UI房间_文本.剩余亲戚_总`，由 HTML 拼接为 `current / total`（避免节点图侧做字符串拼接）。
  - 顶栏年夜饭完整度：显示绑定玩家变量 `ps.ui_battle_integrity`，节点图写回整数，`%` 后缀由 HTML 侧追加（避免节点图侧拼接字符串）。
  - 顶栏手办存活：显示绑定玩家变量 `ps.ui_battle_survival`（整数存活数），由 HTML 拼接 `/ 10`（避免节点图侧做字符串拼接）。
  - 顶栏个人 HUD：
    - 压岁钱：绑定玩家变量 `ps.ui_battle_money`（每名玩家各自一份）。
    - 当前排名：绑定玩家变量 `ps.ui_battle_rank`（由节点图按积分排序写回）。
  - 页面不维护 `data-ui-variable-defaults`；UI 字典/玩家变量的默认结构与默认值统一以 `管理配置/关卡变量/自定义变量注册表.py` 为准（Web 预览/导出链路如需注入默认结构，应从注册表派生）。
  - 游戏区域倒计时 badge：
    - 文案绑定：`lv.UI战斗_文本.回合倒计时`（仅写回数字；“倒计时”前缀由 HTML 固定拼接，避免节点图侧拼接字符串）。
    - 展示开关：新增状态组 `stage_countdown_state(hidden/show)`，默认 `hidden`；由节点图在**投票阶段**切到 `show`（进场 5 秒不展示倒计时）。
  - 游戏区域对白字幕（对白框）：
    - 展示开关：使用状态组 `stage_dialogue_state(show)`（初始无默认态=隐藏）；由节点图切到 `show` 展示对白框。
    - 导出约束：状态节点需带稳定 `data-ui-key`（本页为 `data-ui-key="stage_dialogue_state"`），用于生成 `UI_STATE_GROUP__stage_dialogue_state__show__group`，供节点图稳定引用。
  - 审判结果揭晓覆盖层 `battle_settlement_overlay`：
    - 状态：`hidden/result` 两态；`result` 仅用于展示最终结果。
    - 文案绑定：`lv.UI战斗_揭晓.结果_判定/结果_真相/结果_描述`。
    - 影响值绑定：
      - 个人资源变化（每人不同）：`ps.ui_battle_integrityd/ps.ui_battle_survivald`（完整度 `%` 后缀由 HTML 侧追加）。
      - 个人变化值（每人不同）：`ps.ui_battle_moneyd`（压岁钱变化）与 `ps.ui_battle_scored`（积分变化）。
  - 新手指引遮罩层 `tutorial_overlay`（即帮助面板）：
    - **样式优化**：使用更明显的“卡片+标签”风格（黄色胶囊标签、大号标题、正文背景框）。
    - **布局调整**：将“新手教学倒计时”从 `guide_1 / wait_others` 等状态中抽离，改为独立状态组 `tutorial_countdown_state(show/hidden)`，通过 `.tutorial-countdown-actions` 固定在**全局右上角**，保证在所有指引页常驻且可在“正式开始”后整体隐藏。
    - **层级保证（扁平化）**：倒计时 `show` 使用 `data-flat-z-bias="1000200"`；倒计时块放在 `tutorial_overlay` 末尾，确保在 `wait_others / done` 全压暗遮罩与高亮压暗 shadow layers（通常 `data-flat-z-bias="1000000"`）之上；注意扁平化层级不读取 CSS `z-index`。
    - **扁平化稳定性**：避免渐变/旋转等不稳定样式，用纯色/描边/阴影实现层次。
  - `tutorial_overlay` 默认态为 `guide_0`：进入页面先展示“背景故事”，点击下一步进入 `guide_1~guide_6` 新手指引。
  - 预览初始态覆盖（仅 Web 预览，不影响导出/写回）：页面根节点可声明 `data-ui-preview-initial-states="<group>=<state>; <group2>=<state2>"`（兼容简写 `data-ui-initial-states`），用于在切到该页面时自动应用“预览初始状态”（可叠加多个状态组，例如隐藏教程 overlay、隐藏教程倒计时、显示帮助按钮）。
  - 状态预览基底（仅 Web 预览，不影响导出/写回）：可额外声明 `data-ui-preview-state-preview-base-states="<group>=<state>; <group2>=<state2>"`（兼容简写 `data-ui-state-preview-base-states`），用于在工具条选择某个状态组进行预览时，先自动应用一组“干扰层隐藏”覆盖（典型：隐藏教程遮罩、隐藏全屏遮罩），再应用工具条的单组覆盖。
- `第七关-结算.html`：
  - 顶栏右侧为**装饰徽章**（不展示倒计时），用于占位与平衡视觉重心；避免在结算页塞入无业务意义的“新年钟声倒计时”信息。
  - 底部操作区仅保留一个『返回大厅』按钮：`btn_back`（不再提供 `btn_retry/再来一年`）。
  - 完整度/手办的数值标签与进度条统一绑定到玩家变量 `ps.ui_battle_integrity/ps.ui_battle_survival`（current）；min/max 也绑定到玩家变量 `ps.ui_battle_i_min/ui_battle_i_max`、`ps.ui_battle_s_min/ui_battle_s_max`（默认 0/100/0/10；避免常量不落入玩家模板自定义变量清单）。
  - 右侧榜单 money/points 文案拆分为 `lv.UI结算_文本.榜N钱前缀 + 榜N钱`、`榜N分 + 榜N分后缀`：避免节点图侧拼字符串，同时允许“缺人 slot”通过写回单空格 `" "` 让整行自然留空。
  - 页面不维护 `data-ui-variable-defaults`；结算页 UI 字典变量的默认结构以 `自定义变量注册表.py` 为准。

## 注意事项

- **字号硬约束**：文本字号必须是固定 `px`（禁止 `vw/vh/%/em/rem/clamp()` 或媒体查询分支改变字号），否则 Workbench 会阻断导出。
- **固有控件初始显隐（必须显式声明）**：页面根节点 `<html>` 必须声明 `data-ui-builtin-visibility`（JSON object），仅允许并且必须包含 5 个键：`小地图/技能区/队伍信息/角色生命值条/摇杆`。
  - 语义：写回 `.gil` 时会将对应固有控件 record 的 `initial_visible` 按该值落盘（`false`=初始隐藏）。
  - 约束：多写/少写/写其它控件名都会 fail-fast 报错（避免“默认值悄悄生效”）。
- **状态隐藏**：多状态控件非默认态不要用 `display:none`（会丢盒子），优先 `visibility:hidden` 或 `opacity:0`。
  - 若节点图需要引用 `UI_STATE_GROUP__<group>__<state>__group`，对应状态节点（带 `data-ui-state-group/data-ui-state`）必须带 `data-ui-key`，否则 Workbench bundle 可能不产出该状态组的组件组容器，导致节点图写回缺 key。
  - Web 预览中如需“页面级的预览初始态覆盖”，用 `data-ui-preview-initial-states` 声明；不要靠手工改动 `data-ui-state-default` 来表达“仅预览”的需求（`data-ui-state-default` 属于导出语义：会影响写回 `.gil` 的 `initial_visible`）。
  - 若需要“切换状态组预览时自动隐藏教程/遮罩”，优先用 `data-ui-preview-state-preview-base-states` 声明（而不是把教程默认态改成 hidden）。
- **文本对齐**：建议显式写 `data-ui-text-align="left|center|right"` 与 `data-ui-text-valign="top|middle|bottom"`，避免默认推断导致对齐漂移。
- **模板沉淀（data-ui-save-template）**：本目录页面默认不标注 `data-ui-save-template`（避免导出/写回链路把页面内控件沉淀回控件组库模板）。
  - 若确需沉淀模板：请在控件组库专用页面/工程中维护模板源；关卡页面只负责引用与使用。
- **退出按钮（装饰，不可点击）**：若某个“退出”仅用于视觉占位，不希望导出为可交互按钮锚点（避免占用 1..14 槽位），在该元素上标注 `data-ui-export-as="decor"`（样式仍保留，但导出/写回时不会生成可交互按钮）。
- **真实进度条变量绑定**：
  - HTML 标注：`data-ui-role="progressbar"` + `data-progress-current-var / data-progress-min-var / data-progress-max-var`。
  - **关键限制**：`.gil` 的进度条 binding 只支持 `(变量组 + 变量名字符串)`，没有“字典变量 + key”字段。
    - 因此进度条绑定 **禁止**写 `lv.<字典>.<键>` 这类“字典键路径”（会造成“看起来像字典、实际是标量”的歧义，且导出链路会拒绝）。
    - 进度条必须绑定到**标量变量名**（`lv.<name>` 或 `ps.<name>`，且 `<name>` 内不含 `.`）；min/max 语法上允许数字常量（例如 `0/100/10`），但本项目主流程要求改用自定义变量（确保写回/模板变量齐全）。
  - 实践建议：
    - **优先单一真源**：若一组数值既用于进度条又用于文本展示（例如进度条右侧数值），优先让文本占位符也直接绑定到同一套标量变量（例如 `{1:ps.ui_battle_integrity}%`），节点图只维护这一套标量变量即可。
    - **字典仅用于大批量字段**：只有当字段数量很多、需要按模块分组或复用一张字典时，才采用“字典占位符 +（必要时）镜像标量同步”的双写策略。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。
