## 目录用途
- `src/ui_export/widgets/` 存放 Workbench “扁平层 → UI控件（widget）”导出的控件构建器与语义判定函数。
- 该目录的规则直接影响导出的 `UI布局 Bundle JSON`（`UILayout + templates`），并最终影响主程序导入与 `.gil` 写回。

## 当前状态
- **按钮语义判定**（`button_semantics.js`）以显式语义为主：优先把“显式标注”为按钮的元素视为按钮锚点。
  - 允许：`data-ui-role="button"`（推荐）、`role="button"`（ARIA）、`data-ui-interact-key`、`data-ui-action`
  - 不再自动：仅因为使用 `<button>` 标签或 `class="btn"` 就算按钮
  - 设计目的：避免 UI mockup 中大量“为了样式/排版方便”的 `<button>`/`.btn` 误判为可交互按钮，触发“同页可交互按钮 > 14”而阻断导出。
  - 兜底：若元素为真实 `<button>` 且具备 `data-ui-key`，也视作按钮锚点（认为作者已显式提供稳定语义键）。
  - 导出语义提示：支持 `data-ui-export-as="decor"`，用于显式标记“该元素不是按钮锚点”：
    - 即使是 `<button data-ui-key="...">`，也不会被当成按钮语义，因此不会导出为“道具展示(可交互)”控件。
- **单字符/emoji ICON → 道具展示（收紧为显式标注）**：
  - 不再自动将“单字符/emoji 文本”导出为“道具展示(ICON)”控件。
  - 若确实需要“纯展示 ICON 的道具展示”，必须在该元素上显式标注 `data-ui-role="item_display"`（推荐同时提供 `data-inventory-item-id` 作为配置ID变量）。
 - **模板沉淀标记（新增）**：
  - HTML 可选标注 `data-ui-save-template`，用于声明“该组件组需要沉淀为控件组库自定义模板”（导出 `.gil` 的后端写回阶段使用）。
  - 语义：
    - `data-ui-save-template="<模板名>"`：指定模板名（基底 `.gil` 已存在同名模板时应复用）。
    - `data-ui-save-template="1"/"true"`：仅声明需要沉淀，模板名由导出端根据组件组 key 生成默认名。

## 注意事项
- 若某元素应被导出为“可交互按钮锚点（道具展示）”，推荐在 HTML 中显式标注 `data-ui-role="button"`，并建议补充 `data-ui-interact-key="1..14"` 以稳定槽位；也可通过 `data-ui-interact-key` / `data-ui-action` 直接声明交互意图。
- 若只是视觉上的按钮外观（装饰/布局容器），不要标注 `data-ui-role="button"`；必要时也不要使用 `role="button"`，避免导出语义混淆。
  - 若必须使用 `<button data-ui-key>` 作为视觉/布局容器，但不希望其占用按钮槽位，使用 `data-ui-export-as="decor"`。
- “选中高亮底板”建议显式写 DOM，并用 `data-ui-state-*` 作为唯一互斥机制（不再使用已废弃的 `data-ui-selected-highlight/data-ui-selected-default` 自动导出）：
  - 推荐：为高亮底板元素标注 `data-ui-key="<base>_highlight"`，并同时标注 `data-ui-state-group / data-ui-state`；默认态写 `data-ui-state-default="1"`，其它态用 `visibility:hidden`（或 `opacity:0 + pointer-events:none`）初始隐藏。

## 目录用途
- `src/ui_export/widgets/`：Workbench 的“控件导出”子模块：把扁平 layer（shadow/border/element/text）转换为程序可写回的 UI widgets（进度条/文本框/道具展示等）。
- 该目录尽量保持“小文件 + 稳定导出函数名”，由 `src/ui_export/widgets.js` 统一 re-export 作为对外门面。

## 当前状态
- 主要模块：
  - `button_semantics.js`：按钮语义识别（显式：`data-ui-role="button"` / `role="button"` / `data-ui-interact-key` / `data-ui-action`；不再因 `<button>`/`.btn` 自动判定）。
  - `widget_ids.js`：widget_id 生成（基于 prefix + kind + DOM 元信息 + zIndex）。
  - `progressbar_widget.js`：进度条 widget 构建（颜色映射、shape 推断、变量绑定策略）。
  - `textbox_widget.js`：文本框 widget 构建（字号策略、富文本 `<color>/<size>`、对齐）。
    - 对“小字号（<30）+ 暗色文字”给出 warning（基于相对亮度），提示可能被引擎灰色描边影响可读性。
    - 支持 `data-ui-text`：允许将“网页用于排版测量的短示例文本”和“写回到游戏的实际文本/占位符”解耦（导出时优先使用 `data-ui-text` 作为 `settings.text_content`）。
    - 支持 `data-ui-text-align / data-ui-text-valign`：作者可显式指定 TextBox 水平/垂直对齐；导出时优先级高于 computed style（用于解决扁平化后文本框默认左上对齐的问题）。
    - **整体缩放字号补偿**：若上游扁平化检测到祖先存在 `transform: scale(...)`（常见：`--ui-scale` 响应式缩放），会在 layer 上透传 `effectiveScale`；TextBox 导出时会将字号按 `effectiveScale` 同倍率缩放，避免导出到 `.gil` 后出现“盒子缩小但字号没缩小”的溢出叠字（1600×900 常见）。
  - 支持 `settings.background_color`：用于把阴影矩形导出为“空文本框 + 半透明黑底”（写回阶段用于表达 alpha 盖色阴影）。
  - 对“极短文本/纯数字文本”的 TextBox 增加了更强的最小宽高兜底，避免导出到 `.gil` 后因 TextBox 过小导致文字被裁切不可见。
  - `item_display_widget.js`：道具展示 widget 构建（交互按钮锚点/纯展示 ICON、变量绑定、action/args 标注）。
  - `text_icon_normalize.js`：文本与 ICON 的归一化（单 ICON/混排/多 ICON 的处理规则）。
  - `icon_seat.js`：ICON 座位推断（将 ICON 道具展示吸附到更合适的背景矩形）。
- **进度条变量绑定（HTML 注解）**：
  - 元素标注 `data-ui-role="progressbar"` 后，可额外提供：
    - `data-progress-current-var="ps.xxx"`（当前值）
    - `data-progress-min-var="ps.xxx"`（最小值，可用常量 `0`）
    - `data-progress-max-var="ps.xxx"`（最大值，可用常量 `100`）
    - `data-progress-shape="横向|纵向|圆环"`（也允许 `horizontal/vertical/ring`；未声明时对“真实进度条”默认写回为横向）
  - 导出时会将其写入进度条 `settings.current_var/min_var/max_var`；未标注则使用默认“装饰进度条变量”。

## 注意事项
- 该目录代码运行在浏览器侧：无打包流程；禁止引入 Node.js API。
- 导出应保持确定性：同输入应产出稳定的 widget_id/ui_key（由上层 `keys.js` 约束）。
- 变量绑定字符串不做运行期容错；语法/来源闭包由 `validate-ui`（Python）在导出前静态校验。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

