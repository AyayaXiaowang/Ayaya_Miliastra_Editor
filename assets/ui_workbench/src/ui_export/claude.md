## 目录用途
- `src/ui_export/`：承载 `src/ui_control_group_export.js` 的导出实现（扁平 layers -> UI Bundle JSON），把“稳定 key / UI 多状态 / 文本与 ICON 规则 / 颜色与字号策略 / 模板与布局组装”等逻辑拆分为多个 ES Module，降低单文件体积与耦合度。

## 当前状态
- `ui_control_group_export.js`：对外门面（保持原导出 API），内部委托到本目录模块。
- `keys.js`：稳定 key 生成（`ui_key` / `__html_component_key`）与前缀管理（**全仓单一来源**）。
  - 多状态分组（重要）：当元素处于 `data-ui-state-group` 作用域内时，`__html_component_key` 仅由 `state_group + state` 生成（不再混入子元素自己的 `data-ui-key`），确保**同一状态的所有内容落到同一个组件组**，从而能通过 `...__group` 整体控制显隐（写回端按 `__html_component_key` 创建组容器）。
  - 可选显式分组：HTML 可用 `data-ui-component-key` 强制指定 `__html_component_key`（多控件写同 key 可进入同一组件组/组容器），用于“多个控件组成一个可复用控件组模板”等场景。
  - Workbench 复用：提供 `buildStableHtmlComponentKeyWithPrefix(...)` 作为无副作用 helper，供 Workbench/扁平化调试视图生成与导出/写回一致的组件组 key（避免复制式一致性）。
- `ui_state.js`：UI 多状态（`data-ui-state-*`）抽取与写入。
  - 初始显隐以 `data-ui-state-default="1"` 为准：导出时会把非默认态写为 `initial_visible=false`（写回 `.gil` 后能在游戏里正确初始隐藏），不要依赖作者手工写 `visibility:hidden` 来表达语义。
- **实体自定义变量默认值（新增）**：
  - HTML 可通过 `data-ui-variable-defaults`（JSON object 字符串）声明“变量默认值映射”。
  - Workbench 导出 bundle 时会把该映射写入 bundle 顶层 `variable_defaults`，供写回端在“自动创建实体自定义变量”时使用。
- `text_icon.js`：emoji / ICON 文本分析与清洗规则。
- `color_font.js`：颜色解析/规范化与字号策略（含进度条颜色映射、富文本 `<size>` 规则）。支持识别 45%/25% 阴影盖色（用于压暗 1/2/3 级归一化）。
  - 额外提供“小字号文本 + 暗色”的告警判定（基于相对亮度），用于规避引擎灰色描边在小字上降低可读性的问题。
  - 进度条 shape 推断：`圆环` 仅在元素显式声明为进度条（`data-ui-role="progressbar"` 或提供 `data-progress-*-var`）时启用；避免圆形按钮/徽章等装饰层被误导出为“带洞圆环”。
  - **文本对齐默认居中（新增约束）**：导出 TextBox 的 `alignment_h/alignment_v` 默认强制为“水平居中/垂直居中”；
    - 若需要非居中，必须在元素上显式声明 `data-ui-text-align="left|center|right"` 与 `data-ui-text-valign="top|middle|bottom"` 覆盖。
- `widgets.js`：widget 构建（进度条/文本框/道具展示）与按钮语义识别。
  - 按钮锚点“道具展示”默认导出为 **模板道具**，并绑定到一套 `关卡.UI_交互按钮_*` 变量（配置ID/数量/冷却），供写回端自动补齐实体自定义变量。
  - 文本框字号导出支持 `effectiveScale`：当上游扁平化计算到祖先存在 `transform: scale(...)`（例如 `--ui-scale`）时，会按同倍率缩放 TextBox 的字号/富文本 `<size>`，确保“缩放后的盒子”和“缩放后的字号”一致（避免 1600×900 下溢出叠字）。
- `widgets/`：`widgets.js` 的内部实现拆分目录（按钮语义/ID/三类控件构建/ICON 处理/座位推断等）。
- `template_from_layers.js`：layers -> 单模板（兼容旧“整页模板”输出）。
  - `__flat_layer_key/flat_layer_key` 的生成口径由 `src/layer_key.js` 统一提供（toFixed(2)+round(z)），用于预览页“导出控件列表 ↔ 画布”精确定位。
  - 导出控件命名增强：当扁平层元素自身缺少 `data-ui-key/id/data-debug-label` 而仅能落到通用 `dataLabel`（如 `btn-text`、`tone-3-stripe`）时，导出 widget 的 `widget_name` 会优先拼入 componentOwner（按钮根）的 `data-ui-key/data-debug-label`，形成 `owner:leaf` 的可读名称，避免导出控件列表里出现大量跨按钮同名条目导致误判“混组”。
  - 按钮“道具展示”锚点（`btn_item`）会尽量写入 `__flat_layer_key`：优先绑定 `button_anchor` 层（视觉为空按钮专用），否则绑定到该按钮的代表层（element/sample/icon），用于预览页“导出控件列表 ↔ 画布”精确定位，避免靠 rect 猜导致错高亮。
  - **按钮层级口径一致（重要）**：`btn_fill/btn_item` 的 zIndex 必须叠加 `data-flat-z-bias`（由 `dom_extract.js` 透传为 `source.attributes.dataFlatZBias`），与 `layer_data.js` 的 `layer.z` 口径一致；否则当按钮处于高层级容器（遮罩/指引卡片）内时会出现“按钮底色层级下沉，被面板底色遮住”的问题。
  - 交互/导出几何：button 的基础 rect 默认使用“去掉边框后的 innerRect”（从 `source.rect` 扣除 `border-*-width`），以对齐“忽略 border 但内容区域变小”的扁平化口径，避免出现“预览变小但导出 GIL 仍按 border-box 偏大”。
  - `data-ui-export-as="decor"`（导出语义提示）：
    - 若按钮根元素标记为 `decor`，导出时不会生成该按钮的“道具展示(可交互)”按钮锚点控件（避免占用 1..14 槽位）。
  - 单字符/emoji ICON 的导出策略（重要）：
    - 不再“自动把单字符/emoji 文本转换为道具展示(ICON)”。
    - 只有当该元素显式声明 `data-ui-role="item_display"` 时，才允许导出为“道具展示(ICON)”控件（建议同时提供 `data-inventory-item-id` 作为配置ID变量）。
  - 阴影层（`layer.kind="shadow"`）若为规范盖色阴影（`rgba(14,14,14,0.45/0.25)`），按强度分流导出：
    - **25%（浅压暗）**：导出为“空文本框 + 半透明黑底”（保留盖色半透明语义）
    - **45%（深压暗）**：导出为“空进度条（0%）”（更深的压暗效果）
      - 为避免进度条颜色映射告警，导出时固定 `settings.color=#E2DBCE`，并将原始 rgba 写入 `_html_color_source` 供排障对照。
  - 色块层（`layer.kind="element"`）若自身就是规范盖色阴影（例如作者用遮罩层表达压暗），导出为“空文本框 + 半透明黑底”，避免被进度条语义误用导致“阴影档位被写深”。
  - `data-ui-selected-highlight/data-ui-selected-default` **已废弃**：为避免和 `data-ui-state-*` 概念混淆，不再自动生成“选中高亮底板”。
  - 迁移方式：在 HTML 中显式写出高亮底板 DOM，并用 `data-ui-state-group / data-ui-state / data-ui-state-default` 表达互斥状态（状态切换由节点图负责显隐）。
  - 性能优化（导出侧）：默认过滤“小字号 text-shadow 拆层”（仅影响导出 bundle/GIL，不影响预览扁平化画面），可通过 `min_text_shadow_font_size` 调整阈值（默认 18；设为 0 关闭过滤）。
- `bundle_from_layers.js`：layers -> UILayout + 多模板 bundle（按钮打组、UI 多状态合并/整态打组、**全局 layer_index（zIndex）唯一化**、全局 `ui_key` 去重）。
- `bundle/`：`bundle_from_layers.js` 的内部实现拆分目录（几何/按键码/按钮打组/状态整态合并等）。
  - 导出警告：导出链路会产生一组 warnings（例如进度条颜色映射偏差提示），Workbench 会将其统一转为结构化 Diagnostics warning 并汇总显示/写入 AI 修复包。
  - 状态策略（重要）：
    - 默认：以 **widget 级显隐** 表达（`initial_visible` + 节点图切换），并可启用“组件内合并（最小冗余）”降低模板数量。
    - 兼容：可通过 `ui_state_consolidation_mode="full_state_groups"` 回退为“整态打组”（每个 state 独立组件组），用于规避游戏侧可能存在的层级/底色异常（代价是冗余增加）。
      - 兼容增强：在 full_state_groups 模式下，会将 `<state_group>_content` 共享内容组件复制进各 state 组内（默认态迁入原件 + 其它态克隆），确保状态切换时内容与底色/边框真正整组一起切换。

## 注意事项
- **浏览器侧**：无打包流程；必须使用相对路径 ES Module import；禁止引入 Node.js API。
- **稳定性约束**：对外 API 以 `src/ui_control_group_export.js` 为准；本目录内部模块可调整但需要保持导出结果与规则一致。
- **禁止复制稳定 key 规则**：Workbench/其它视图必须直接 import 本模块（`keys.js`）生成稳定 key，不允许在其它目录复制 `sanitizeIdPart/buildStableHtmlComponentKey/...` 的实现；否则极易出现“分组树 key ≠ 写回端分组 key”的联动错位。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

