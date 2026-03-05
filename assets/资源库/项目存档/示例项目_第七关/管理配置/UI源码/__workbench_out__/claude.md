## 目录用途
- 存放 UI Workbench 导出的 `*.ui_bundle.json`（页面扁平化/控件抽取后的结构化产物），供 `project import` 的“UI（界面）写回”阶段直接使用。

## 当前状态
- 本目录的 `*.ui_bundle.json` 与同级 `UI源码/*.html` 一一对应，写回端以 **bundle 文件名** 作为布局名消歧。
- 这里的 bundle 是写回的真源输入：若只修改了 `.html` 而未重新导出对应 `.ui_bundle.json`，写回仍会使用旧 bundle（可能导致节点图引用的 `UI_STATE_GROUP__*` 缺 key，或变量绑定仍沿用旧占位符）。

## 注意事项
- 建议把本目录视为“构建产物”：优先通过 Workbench/导出工具从 `.html` 重新生成，而不是手工编辑 JSON。
- 若节点图需要稳定引用 `UI_STATE_GROUP__<group>__<state>__group`，对应状态节点应在 HTML 侧具备稳定 `data-ui-key`，并确保 bundle 内的控件携带 `__ui_state_group/__ui_state` 元信息（由导出链路生成）。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

