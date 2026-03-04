## 目录用途
`ui/panels/combat/` 存放战斗预设相关的右侧详情/编辑面板与可复用子组件（玩家模板、职业、技能、道具等），用于在 `ViewMode.COMBAT` 下展示与编辑战斗域配置。

## 当前状态
- 面板以“上层装配 + 下层 sections/widget”组织：`combat_player_panel.py` 组合若干 `combat_player_panel_sections_*.py`，其余职业/技能/道具面板也各自拆出编辑控件模块，避免单文件膨胀。
- 面板对外以信号暴露“数据变更/跳转请求”等事件，由主窗口在对应 mixin 中统一处理持久化与导航。

## 注意事项
- 不在面板内部直接做资源写盘；写回应通过上层注入的 service/controller 或统一的 data_updated 链路完成。
- 不使用 `try/except` 吞异常；错误直接抛出，交由上层入口与 pytest 捕获定位。

