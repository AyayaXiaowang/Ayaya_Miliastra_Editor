## 目录用途
- `src/`：UI HTML Workbench 的前端实现（浏览器侧 ES Modules），负责：
  - HTML 源码校验与自动修正
  - iframe 预览与选中/框选/检查器联动
  - DOM 扁平化（提取 → layers → 扁平输出 HTML）
  - 扁平层 → UI Bundle JSON（供导入到主程序 / 写回 GIL）

## 当前状态
- `main.js`：Workbench 页面入口（保持极薄），只调用 `workbench_main/index.js` 完成初始化。
- `dom_refs.js`：DOM 引用（按固定 id 强绑定），包含导入/导出（GIL/GIA）相关控件的引用；并包含 Workbench 状态显示与 browse 自动导入开关等控件引用（新增 GIA 快捷按钮引用）。
  - 预览相关 DOM 新增可选开关：`dynamicTextPreviewCheckbox`（用于在预览中切换 `data-ui-text` 绑定占位符显示，仅影响可视预览，不影响 compute/导出）。
  - 预览检查器支持“文本对齐锚点”面板：右侧检查器新增 `textAlignInspectorBlock/textAlignGrid/textAlignHint`（用于只读展示 `data-ui-text-align / data-ui-text-valign`，并随选中元素实时刷新）。
- `config.js`：画布尺寸目录、调色板等共享常量（支持 Base / 压暗 1 级（25%）/ 压暗 2 级（45%）/ 压暗 3 级（45%×2 叠加））。
- `utils.js`：通用工具（剪贴板、成功提示音 beep（AudioContext，需在点击等手势中解锁）、路径 basename、帧等待、HTML 转义、CSS 顶层逗号分割、**稳定 hash（FNV-1a）用于缓存 key**）。
- `layer_key.js`：扁平层 `layerKey` 的**唯一真源**（build/parse/posKey）。
  - 格式：`kind__left__top__width__height__round(z)`；rect 使用 `toFixed(2)` 对齐扁平 DOM 写入精度。
- `validation.js`：基础校验 + 常见问题自动修正（用于保证预览稳定）；滚动条校验以“实际 scrollWidth/scrollHeight 超出”为准，避免仅依赖 computedStyle 导致假阳性。
  - **字号硬校验（新增）**：对 compute iframe 依次切换 4 个画布尺寸，要求所有可见文本的 computed `font-size` 在各尺寸下完全一致；若发现随画布变化（典型：`vw/vh/clamp()/em/rem/%/媒体查询`），会报 `TEXT.FONT_SIZE_CHANGES_WITH_CANVAS_SIZE`（error）并阻断通过/导出。
  - **禁止缩放（新增硬校验）**：禁止在源码中使用 `transform: scale(...)`，且禁止任何“含文字元素”的 computed transform 出现缩放（scale/matrix scale）。该写法会触发扁平化的字号补偿机制，导致扁平/导出后的文字字号变化。
  - `.game-cutout`（游戏视口挖空）按“标了就切”的语义处理：只要标记存在就会作为矩形挖空参与裁切；校验侧不再要求近似正方形/透明/无边框阴影，仅保留 cutout 之间不允许重叠的保护性规则。
  - `.highlight-display-area`（高亮展示区域）用于“周围压暗”：扁平化会移除该元素本体，并自动生成 4 个包围该区域的压暗遮罩矩形（上/下/左/右），通过“周围变暗”实现高亮效果；可选 `data-highlight-overlay-alpha="0.45|0.25"` 控制压暗强度（默认 0.45）。
- `data-flat-z-bias`（层级偏移）用于“整体抬高某个组件的扁平层级”：
  - 取值为整数（允许负数），会叠加到该元素的扁平化基准 z-index（以及高亮展示区域生成的压暗层 z-index）。
  - 主要用于指引/遮罩类 UI：压暗层可设置较高 bias 覆盖所有普通 UI；指引卡片可设置更高 bias 保持始终可见。
  - 继承规则：若组件外层声明了 `data-flat-z-bias`，其子节点（标题/正文/按钮等）会自动继承该值，避免“外层抬高但内部文字仍被遮挡”的问题。
  - UI 多状态（`data-ui-state-*`）校验：同组最多一个默认态（`data-ui-state-default="1"`）；0 默认态视为“初始全部隐藏”（warning）；状态节点禁止 `display:none`（否则无盒子无法扁平化/导出），并提示“非默认态建议隐藏以贴近初始态”（info）。
  - 状态绑定规则（新增兼容）：`data-ui-state-group` 可写在“组根节点”，`data-ui-state/data-ui-state-default` 写在其子状态节点；扁平化会按“最近组根 + 同组范围内最近状态节点”绑定 state 元信息到可视元素，降低作者为每个子层重复写 group 的负担。
  - 文本对齐提示：对“靠近容器右边框但仍为左对齐”的文本给出 warning，降低程序员遗漏“应右对齐”的概率；支持 `data-ui-align="right"` 显式标注并做硬校验。
  - 颜色硬校验（新增）：禁止不透明纯黑（`#000/#000000/rgb(0,0,0)`）用于矩形底色/边框/阴影；命中会报 `COLOR.FORBIDDEN_SOLID_BLACK`（error）并阻断校验通过，提示改用 `#0e0e0e73/#0e0e0e40` 或 `rgba(14,14,14,0.45/0.25)`。
  - 禁止 `::before/::after`（含 `:before/:after`）伪元素：扁平化无法导出伪元素层。
  - 禁止 flex/grid 容器内“直写文本节点 + 子元素混排”；自动修正可将直写文本包为 `<span>`。
  - 装饰层（`deco-*` / `data-ui-deco=1`）必须后置；自动修正可将装饰元素移到同级末尾。
- `diagnostics.js`：结构化诊断模型（Issue/Diagnostics），用于统一校验输出，并生成“AI 修复包”（Diagnostics JSON + HTML）形成短反馈闭环；提供按 severity 分桶能力（errors/warnings/infos）。
- `preview/`：预览子系统（渲染、缩放、覆盖层、检查器等，入口 `preview/index.js`）。
- `workbench/`：主页面的左侧工具面板子模块（UI源码浏览、变量浏览等），用于把 `main.js` 拆薄。
- `workbench_main/`：Workbench 主页面逻辑拆分目录（入口编排/预览切换/自动验收等）。
- `flatten.js`：扁平化核心（DOM → 扁平 layers / divs）；内部算法细节拆分到 `flatten/internal/`。
- `flatten/`：扁平化子系统拆分目录（DOM 提取 / divs / layer 数据 / 输出注入 / internal 算法模块等；详见 `flatten/claude.md`）。
- `ui_control_group_export.js`：扁平 layers → UI Bundle JSON（layout + templates）的**对外门面**；实现拆分到 `ui_export/`。
- `ui_export/`：UI Bundle 导出实现拆分目录（稳定 key/多状态/文本与 ICON/颜色与字号/模板与布局组装等）。
- `app_ui_preview_main.js`：UI 资源预览页逻辑（`ui_app_ui_preview.html` 使用），从后端拉取并展示布局/模板 JSON。
- `ui_app_ui_preview/`：UI源码预览页的页面级逻辑拆分目录（对应根目录 `ui_app_ui_preview.js` 薄入口），用于避免单文件过长；包含文件列表/预览与扁平化生成/导出 GIA&批量导出 GIL/基底 GIL 缓存等编排逻辑。

## 注意事项
- **ID 强绑定**：`dom_refs.js` 使用 `getElementById`，`ui_app_ui_preview.html`/预览页相关 DOM 的 id 必须保持稳定，否则会导致功能失效。
- **无打包流程**：依赖浏览器原生 ES Module；本地开发建议用 http server 访问（避免 file:// 的跨域/缓存问题）。
- **预览禁脚本**：Workbench 预览 iframe 默认不含 `allow-scripts`，因此：
  - 扁平化输出必须保持 **无 `<script>` 注入**
  - 与页面切换相关的链接改写必须在生成阶段完成（不能靠脚本运行期改写）

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

