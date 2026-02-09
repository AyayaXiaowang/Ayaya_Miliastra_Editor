## 目录用途
- `src/flatten/`：Workbench 扁平化子系统拆分目录：把 `src/flatten.js` 中的 DOM 提取、扁平 div 生成、layer 数据计算、输出注入等职责拆开，降低单文件体积与维护难度；`src/flatten.js` 作为对外门面维持稳定导出 API。

## 当前状态
- `output.js`：扁平化输出辅助：
  - `buildFlattenedInjectionHtml(...)`：生成注入到 `<body>` 的扁平层 DOM + 注入 CSS（**不注入脚本**，兼容 iframe sandbox）。
    - 注入 CSS 会对多状态控件（`data-ui-state-group`）应用“初始态显隐”：默认态（`data-ui-state-default="1"`）可见，其它态使用 `visibility:hidden` 初始隐藏（不使用 `display:none`，避免丢失盒子影响导出/定位）。
  - `normalizeSizeKeyForCssClass(...)`：将画布 label 归一化为 CSS 安全 token。
  - `rewriteResourcePathsForFlattenedOutput(...)`：把 `<script src>` / `<link href>` 的相对路径统一改为 `../` 前缀（用于输出到 `_flattened.html` 子目录时仍可引用资源）。
  - `rewritePageSwitchLinksForFlattenedOutput(...)`：把 `.page-switch-btn` 的 `href` 重写为 `*_flattened.html`（避免依赖脚本改写）。
  - `injectContentIntoBody(...)`：将生成内容注入到 `<body>` 起始处（兼容旧路径）。
  - `replaceBodyInnerHtml(...)`：**直接替换 `<body>...</body>` 的内容**为扁平层（扁平化页面不再残留原始 DOM，例如原稿里的 `.preview-stage`）。
- `dom_extract.js`：DOM → elementsData（提取可视元素、计算样式与盒模型、附带 data-ui-* 元信息；并提取进度条导出语义所需属性：`data-progress-*-var` 与 `data-progress-shape`）。补充输出 `border*Color`、`visibility`、`position/zIndex` 以支持遮挡体可见性判断与 cutout 的层级过滤。
  - 提取结果会附带 `diagnostics`：包含 `bodyRect/canvasSize/canvasRect/--canvas-width|height` 快照，以及“为何被过滤掉”的计数（display:none / visibility:hidden / 0尺寸 / 裁剪范围外等），用于在“扁平化结果为空”时生成可读的实时排障说明与控制台定位。
  - 额外提取 `data-ui-variable-defaults`：用于把“实体自定义变量默认值映射”作为导出附加元信息写入 bundle（不参与扁平化几何）。
    - 约定：key 推荐使用 `lv.<变量名>`（关卡）/`ps.<变量名>`（玩家）；`ls` 前缀为旧写法，已禁用。
  - 额外提取 `data-ui-component-key`：用于作者在 HTML 中显式声明“多个控件属于同一个组件组”（影响导出侧 `__html_component_key`），从而让写回端把它们打到同一个组容器；常用于“多个按钮组成一个可复用控件组模板”的场景。
  - 额外提取 `data-ui-save-template`：用于作者在 HTML 中显式标记“该组件组需要沉淀为控件组库自定义模板”（导出/写回阶段使用，不影响扁平几何）。
    - 推荐写在组件根元素（通常为带 `data-ui-key` 的元素）。
    - 允许后代元素通过 `componentOwner*` 继承 owner 标记。
  - 额外提取 `data-ui-export-as`：用于作者在 HTML 中显式标记“导出语义提示”。
    - `data-ui-export-as="decor"`：保留元素可见/可分组，但导出阶段强制不把它当“按钮语义”（避免 `<button data-ui-key>` 触发“道具展示按钮锚点”）。
  - 为兼容 headless/早期加载场景，`getComputedStyle` 取值对 `document.defaultView=null` 做了降级（回退到全局 `window`），避免扁平化流程被异常中断。
  - 0 尺寸按钮兜底：当元素具备显式按钮语义（`data-ui-role/role/data-ui-interact-key/data-ui-action`）但浏览器计算出的盒子为 0×0（常见于 grid/flex + 绝对定位子层），会改用其子树（descendants）的 unionRect 作为元素盒子，保证后续能生成 `button_anchor` 并导出“道具展示”按钮锚点。
  - 新手指引卡片锚定（新增）：当 `.tutorial-card` 声明 `data-tutorial-anchor="highlight"` 时，扁平化前会在 compute 文档内按“同 state 的 `.highlight-display-area.tutorial-marker`”的 unionRect 预计算卡片 `left/top`（px），解决不同分辨率/媒体查询下“高亮区域与指引卡片脱钩”的问题；该过程不注入脚本，仅改写 compute DOM 的内联 style。
    - 可选 `data-tutorial-anchor-placement="auto|top|right|bottom|left"` 控制贴边方向（默认 `auto`）。
    - 可选 `data-tutorial-anchor-gap="<number>"` 控制卡片与高亮区域间距（默认使用 `--gap` 的 computed px 值）。
  - **整体缩放字号补偿**：当作者使用 `transform: scale(var(--ui-scale))` 做响应式缩放时，`getBoundingClientRect()` 会被缩放，但 `computed font-size/line-height` 不会；dom_extract 会计算并透传 `styles.effectiveScale`，由 `flatten_divs.js/layer_data.js` 用于对文本字号/行高做同倍率缩放，避免导出到 `.gil` 后出现“盒子小、字号大”的溢出叠字（常见于 1600×900）。
  - **文本框对齐显式覆盖（新增）**：支持作者在元素上声明：
    - `data-ui-text-align="left|center|right"`
    - `data-ui-text-valign="top|middle|bottom"`
    - 兼容别名：`data-ui-text-align-h` / `data-ui-text-align-v`
  导出时会透传到 `layer.source.attributes`，并在两个链路同时生效：
  - 导出：`ui_export/color_font.js` 优先用于 TextBox `alignment_h/alignment_v`（不再依赖 computed style 推断）
  - 扁平化预览：`flatten_divs.js` 的 `.flat-text-inner` 会优先按该声明设置 `justify-content/align-items/text-align`（避免预览仍左上导致误判“导出没生效”）。
  - **默认居中（新增约束）**：未声明时，扁平化预览与导出均默认按“水平居中 + 垂直居中”处理；若需要非居中，必须显式声明覆盖。
- `flatten_divs.js`：elementsData → 扁平 HTML divs（阴影/底色/文本层），并可选生成“分组调试覆盖层”。
  - 默认**不拆出 border 图层**：不输出 `.flat-border`；但扁平化预览会对“统一边框（四边同宽同色）”用 `outline` 在 `.flat-element` 上**仅做显示**，从而视觉上仍能看到边框。
  - 同时 **innerRect 仍按 border 宽度缩小**（内容区域为“去掉边框后的大小”），border 仅作为视觉描边，不占用额外图层。
  - 若存在 `game-cutout` 导致元素被切分为多个碎片（多个 `.flat-element`），outline 会按碎片分别描边（可能呈现为碎片化边框）；这是“仍要显示边框”与“切分语义”之间的折中。
  - 扁平层 `.flat-*` 会携带 `data-ui-state-group / data-ui-state / data-ui-state-default`（若源元素属于多状态容器），用于预览页做“状态切换/筛选”（不影响导出/写回语义）。
  - 扁平层的文字节点 `.flat-text-inner` 会透传 `data-ui-text`（若源元素声明了该属性），用于预览页在不切换“扁平/原稿”模式的情况下做“示例文本 ↔ 占位符”切换（仅影响可视预览，不影响 compute/导出）。
  - 对“视觉为空但具备显式按钮语义”的元素，会输出对应的 `.flat-button-anchor`（透明、`pointer-events:none`），与 `layer_data.js` 的 `kind="button_anchor"` 保持一致，用于预览侧/分组树/导出控件列表的 `flat_layer_key` 精确定位。
- `layer_data.js`：elementsData → 扁平 layer 数据结构（供 UI Bundle JSON 导出复用，与 `flatten_divs.js` 同语义）。
  - 默认**忽略所有 border 的可视化输出**：不输出 `kind="border"` 层；但 **innerRect 仍按 border 宽度缩小**。
  - 按钮锚点特殊处理：当元素具备显式按钮语义（`data-ui-role/role/data-ui-interact-key/data-ui-action`）但“视觉为空”（透明、无边框阴影、无文本）时，会生成 `button_anchor` 层以保证导出仍能创建“道具展示”按钮锚点；用于支持“多状态按钮视觉放在子层”的写法。
- `colors.js / borders.js / shadows.js / text_layout.js / group_debug_overlay.js`：扁平化核心算法的可复用子模块（颜色/边框/阴影/文本矩形扩展/分组标注）。
  - `shadows.js`：支持 `box-shadow` 解析（颜色按输入透明度吸附为 25%/45% 两档阴影矩形层），以及 `text-shadow` 解析（用于把多重文字阴影拆成独立图层）。
- `colors.js`：矩形底色/边框颜色统一吸附到“允许调色板”。若颜色本身已在允许列表（包含 base / dark1/2/3 / 阴影遮罩 hex），则直接保留为实色，避免额外生成 `shade-*` 盖色层。
  - 降级诊断（Diagnostics）：扁平化阶段对“不可写回的 CSS 效果”（渐变背景/opacity/transform/圆角/非调色板颜色/模糊阴影/字号吸附等）会做降级/近似，并输出结构化 warning（供 Workbench 汇总与 AI 修复包使用）。
  - 半透明黑底色（如 `rgba(0,0,0,alpha)`）会被自动吸附为允许的阴影遮罩档位（25%/45%），避免调色板量化导致“扁平化后看起来更黑”。
  - **强制校验（导出前）**：不透明纯黑（`#000/#000000/rgb(0,0,0)`）禁止用于矩形底色/边框/阴影；会输出 `COLOR.FORBIDDEN_SOLID_BLACK` 的 diagnostics error，供导出链路直接阻断（提示用户改用 `#0e0e0e73/#0e0e0e40` 或 `rgba(14,14,14,0.45/0.25)`）。

## 注意事项
- 该目录代码运行在浏览器侧：禁止引入 Node.js API。
- 扁平化输出必须保持 **无脚本注入**（Workbench 预览 iframe 默认 `sandbox` 不含 `allow-scripts`）。
- 分组标注（`group_debug_overlay.js`）生成组件组 key 必须与导出/写回端完全一致：直接复用 `src/ui_export/keys.js`，禁止在本目录复制稳定 key 规则实现。
- **游戏区域挖空（`.game-cutout`）语义**：`.game-cutout` 作为“游戏视口挖空”标记，会把**其下方绘制**的背景矩形切分成多个碎片（避免盖住游戏画面），但不会裁剪其上方的覆盖 UI（菜单/提示/高亮等）。
  - 判定基于 `componentOwnerElementIndex`（跨组件）+ dom_extract 先序遍历 index（同组件内）的启发式层级顺序。
  - 仍保留 overlap 校验（`validation.js`）避免多个 cutout 互相重叠造成“裁空一切”的灾难性误用。
- **高亮展示区域（`.highlight-display-area`）语义**：`.highlight-display-area` 作为“展示区域高亮”标记：
  - marker 本体不输出到扁平层（不会生成 element/border/text）。
  - 扁平化会生成 4 个 “shadow layer”（上/下/左/右）包围该区域，以压暗周围内容实现高亮。
  - 覆盖范围/显隐：由 marker 的 DOM 顺序与 `data-ui-state-*` 归属决定；推荐放在需要覆盖内容之后、或放在状态容器内用于分步高亮。
  - 可选 `data-highlight-overlay-alpha="0.45|0.25"` 控制压暗强度（默认 0.45）。
  - 可选 `data-flat-z-bias="<int>"` 抬高压暗层级（用于确保压暗层能盖住其它更高层级的 UI）。
- **混合内容文本导出（新增）**：元素即使包含子节点，只要存在“直接文本节点”（direct text），仍会生成 `.flat-text`；用于避免“按钮文本被 `<br>/<span>` 打断后整段文字消失”。
- **文字阴影拆层（新增）**：当 `text-shadow` 含多层时，会拆成多个“阴影文本层”（`color: transparent + 单条 text-shadow`）并置于主文字下方，解决“多重阴影在扁平化后只剩一个图层”的问题。
- **点选优先文字层**：扁平化注入 CSS 默认将 `.flat-shadow/.flat-border/.flat-element` 设为 `pointer-events:none`，避免矩形层盖住文字导致“点不到文字”；选中矩形层可通过分组树联动完成。
- **对齐意图提示（新增）**：对“短文本标签靠近带边框容器的右边界但仍为左对齐”的情况输出 warning（减少程序员遗漏“应右对齐”的概率）；支持 `data-ui-align="right"` 显式标注与 `data-ui-align-ok="1"` 忽略。
- **文本占位符排版护栏（新增）**：当元素可见文本疑似 `{{lv.xxx}}/{1:lv.xxx}` 这类“变量占位符”且未声明 `data-ui-text` 时，会输出 warning，提示“占位符过长会把网页测量宽度撑爆（运行期值可能很短）”。
  - 推荐写法：元素文本写短示例用于排版测量；真正写回文本放在 `data-ui-text`（供导出为 TextBox）。
- **遮挡剔除（已禁用）**：历史上用于“降噪优化”（剔除被上层完全覆盖的组），但在多状态控件/透明交互锚点/复杂层级覆盖场景副作用过大；当前策略为**正确性优先**：不做遮挡剔除，保证导出结果稳定且语义完整。
- **文本垂直对齐（扁平层）**：扁平化文本层统一用 `display:flex` 承载；当源元素不是 flex 容器时默认采用 `align-items:flex-start`，避免在“flex:1 拉高的文本块”场景下出现扁平化后文字垂直居中漂移。
  - `layer_data.js` 与 `flatten_divs.js` 的默认对齐策略必须一致，否则会导致 text layer 的 rect/layerKey 不一致，进而造成“分组树/导出控件显隐能隐藏边框但隐藏不了文本”的问题。
  - 例外：当元素位于 `button` 内且 class 含 `btn-text`（典型按钮中间短文本），会优先垂直居中，避免按钮文字在扁平化预览里“贴上”造成误判。
- **文本层扩展高度（小字号增强）**：文本层在高度方向会做“额外扩展”以提升点选与导出包围盒的稳定性；对小字号会更激进：约 16~18px 扩展到 ~1.4 行行高，14~16px ~1.8 行，12~14px ~2.2 行，10~12px ~2.6 行，≤10px ~3.0 行；并叠加固定像素兜底（小字号更大），降低游戏侧描边/取整导致的上下裁切风险。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

