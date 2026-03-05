## 目录用途
- `src/ui_export/bundle/`：`layers -> UILayout + templates bundle` 导出的内部实现拆分目录，把原本集中在 `bundle_from_layers.js` 的几何计算、按钮打组、按键码分配、状态整态合并等逻辑拆细，降低单文件复杂度。

## 当前状态
- `rect_utils.js`：widget 的 rect 几何工具（面积/交集/中心点/包围盒）。
- `layer_order.js`：layer_index 的排序/最小层计算。
- `interact_keys.js`：可交互按钮的键位分配与一致性约束（1..14；导出尽量分配唯一键位，若数量超过 14 或键位用尽则将额外按钮统一映射到 14，不阻断导出）。
- `grouping.js`：以“交互道具展示锚点”为中心的按钮打组（把底色/阴影/文本/图标等吸附到按钮模板）。
- `state_consolidation.js`：UI 多状态的**组件内合并（最小冗余）**：
  - 优先把“同一组件的多个 state”合并到**同一个模板**内；
  - 依赖 widget 的 `initial_visible`（默认态 true，其它态 false）以及节点图侧显隐切换表达状态；
  - 设计目的：避免“仅颜色变化也要复制整组模板”，降低模板数量与节点图维护成本。
  - 可选禁用：上层 `bundle_from_layers.buildUiLayoutBundleFromFlattenedLayers(...)` 支持 `ui_state_consolidation_mode="full_state_groups"`，
    以回退为“整态打组”（每个 state 独立组件组；避免跨状态共享控件，用于兼容游戏侧可能存在的层级/底色异常）。
- `state_full_groups.js`：UI 多状态的**整态打组兼容增强**（仅在 `ui_state_consolidation_mode="full_state_groups"` 生效）：
  - 识别 `<state_group>_content` 这类“共享内容组件”（不带 `data-ui-state-*`，但 `data-ui-key` 末尾为 `_content` 且前缀匹配某个 `data-ui-state-group`）；
  - 将该 content 组件的控件**迁入默认态组**（保留 `ui_key/widget_id` 以复用 GUID），并为其它 state **克隆一份**（`ui_key/widget_id` 追加 `__ui_state__<group>__<state>` 后缀）；
  - 目的：让状态切换时“底色/边框/文本/图标”等真正**整组一起切换**，规避游戏侧可能存在的“切换状态后底色飞到顶部/层级错乱”问题；
  - 交互锚点（`道具展示 can_interact=true`）默认**只迁入默认态**，不克隆到其它态，避免重复键位/重复动作。

## 注意事项
- 该目录运行在浏览器侧：无打包流程；禁止引入 Node.js API。
- 该目录为内部实现：对外 API 仍以 `src/ui_control_group_export.js` 为准。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

