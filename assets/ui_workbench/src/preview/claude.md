## 目录用途
- `src/preview/`：承载 Workbench 的“预览子系统”模块，把原本集中在 `src/preview.js` 的渲染/缩放/选择/检查器等逻辑拆分为更小的可维护文件。

## 当前状态
- `index.js`：对外 API 入口（供 `src/main.js` 使用），保持调用面稳定。
- `state.js`：预览子系统运行时状态（选中元素、缩放比例、当前预览文档、渲染序号等）。
- `render.js`：iframe `srcdoc` 渲染、空占位页、刷新恢复与“预览就绪”判定。
  - `srcdoc` 写入前会对 HTML 做“静态预览归一化”：剔除所有 `<script>` 与 `meta refresh`，避免 sandbox 预览产生控制台噪音或自导航影响稳定性（含对缺失 `</script>` 的不规范写法兜底）。
  - 同时会剔除 `onload/onclick/...` 等内联事件属性，以及 `href/src="javascript:..."`，避免 sandbox 禁脚本时浏览器仍打印 “Blocked script execution in about:srcdoc”。
  - 归一化函数对外导出：`normalizeHtmlForSandboxedPreviewSrcDoc()` 可作为“canonical HTML”用于缓存失效判定（sourceHash）。
  - compute iframe：内部会创建一个隐藏的 compute iframe，用于校验/扁平化/导出所需的 computedStyle 采样；可视 iframe 只负责显示，避免“源码/扁平”预览来回闪。
  - compute iframe 使用 `opacity: 0` + `z-index: -1` 隐藏并固定在视口内（不再用 `visibility: hidden` / 超远偏移），避免隐藏布局为 0 导致扁平化为空。
  - `normalizeHtmlForSandboxedPreviewSrcDoc()` 会稳定注入 `meta#wb-sandbox-marker`，渲染轮询会等待该 marker 出现在 `contentDocument` 后才 finalize（避免极端时序下错误绑定到 about:blank，导致 compute 提取为 0）。
  - 预览占位页：提供“空输入”与“处理中（生成扁平化）”两类占位页，避免首次切换时出现短暂白屏造成误解。
  - `srcdoc` 写入后采用 **load 事件 + 帧轮询/超时兜底**，避免部分浏览器在多次切换时丢失 load 导致“预览切换挂起”。
  - 当本次确实更新了 `srcdoc` 时，必须等待 `iframe.contentDocument` 对象切换到新 document 后才 finalize（避免监听挂在旧 document 上，导致“切换几次页面后点选失效”）。
  - 当 `srcdoc` 未变化（复用同一 document）时，渲染 finalize 不再强制清空 selection/隐藏蓝色选中框；只有在 `srcdoc` 确实更新、旧选中引用失效时才清空，减少隐式副作用。
  - compute iframe 同样需要该保护：若 compute 的 `contentDocument` 为空或仍为旧 document，会导致扁平化/分组树提取得到 0 元素。渲染逻辑会等待 document 切换，并在仍为空时向上层返回“未就绪”状态，由 UI 显示失败提示。
- `scaling.js`：画布尺寸应用与舞台缩放（含选中框随缩放刷新）；尺寸按钮 active 态按 `button[data-size-key]` 泛化，支持 4 种预览尺寸；当预览为扁平化页面时，会优先按 `.flat-display-area[data-size-key]` 切换对应尺寸的扁平层（回退用 `data-size` label 匹配）。
  - 兼容：在应用 `--canvas-width/--canvas-height` 时会同步注入 **无单位** 的 `--ui-scale` 数值（按参考 1920×1080 推导并做下限保护），避免部分页面用 CSS `calc(length/length)` 推导比例导致变量失效，从而出现控件 `height:0` 被扁平化跳过的问题（典型：真实进度条）。
  - 切换画布尺寸时会刷新选中态：在扁平化预览下，按 `data-debug-label`（并优先保持同类层：text/element/border/shadow）重新定位到当前尺寸对应的扁平层/多选集合；若无法确定性定位则清空选中，避免检查器显示 0×0 误导。
- `selection.js`：点击选中、多选、框选、删除快捷键与检查器/覆盖层联动；扁平模式下会忽略 `.flat-display-area` 这类“画布容器”的点击目标，并在 `event.target` 不是 `flat-*` 层时强制回退到“按点几何命中（含 `elementsFromPoint` + 忽略 pointer-events 的矩形命中）”挑选真实扁平层，避免误选中底层原始 DOM 容器导致出现“巨大选中框/总选到 panel 容器”。
  - 新增 `selectPreviewElement(...)`：允许外层 UI（例如“分组列表”）驱动预览选中，用于实现“列表 ↔ 画布”双向联动（选中框/检查器同步刷新）。
  - 兜底：在极端 load 时序下若 `state.previewDocument` 暂时为空，会从 `previewIframe.contentDocument` 按需恢复，避免出现“点击画布/点击列表都选不中”的无响应体验。
  - 点击目标归一化：若命中 `.flat-text-inner`，会提升为外层 `.flat-text` 进行选中，避免出现“文字能点到但看起来选不中/删不掉”的体验问题。
  - 调试/测试辅助：预览侧会同步写入 `window.__wb_last_preview_selected_layer_key` 与 `window.__wb_last_preview_selected`，用于端到端断言“确实发生了选中”以及排查 layerKey 映射是否为空（画布点击/列表点击口径一致）。
  - 兜底命中：扁平化输出默认对 `.flat-shadow/.flat-border/.flat-element` 使用 `pointer-events:none`（避免矩形层盖住文字）；当这导致扁平模式“点击选不中”时，会回退为**几何命中测试**（忽略 pointer-events），并遵循“**z-index 优先**（防止点到被遮挡的底层）→ 同 z 再按 **文本 > 主体（含 `.flat-button-anchor`） > 边框 > 阴影** → 同类同 z 再按面积更小更精确”。
  - 隐藏过滤：几何命中测试会跳过 `display:none` / `visibility:hidden` / `opacity:0` 的层，避免出现“已隐藏但仍能在画布上点击选中”的行为。
  - 坐标兼容：预览 iframe 外层使用 CSS `transform: scale(...)` 缩放；当 click 事件的 `clientX/clientY` 与扁平层坐标系不一致时，会尝试多组候选坐标（原始/按 scale 反算/offsetX+targetRect/（极端兜底）按 iframeRect 转换）再命中，避免出现“缩放后点矩形底色却选不中”的情况。
- `overlays.js`：选中框/拖选框/反向区域覆盖层的计算与渲染。
  - 支持“隐藏扁平层”的框选：当 `.flat-*` 层因调试显隐被设为 `display:none` 时，`getBoundingClientRect()` 会变为 0；此时选中框会回退使用扁平化输出写入的 `style.left/top/width/height`（并叠加 `.flat-display-area` 的偏移）来计算矩形，从而实现“选中但不改变隐藏状态”的定位体验。
  - 覆盖层回退同样支持 `.flat-button-anchor`（按钮锚点层），用于“视觉为空按钮”的列表/分组树定位时仍能正确画出选中框。
- `inspector.js`：检查器文本构建与输出（含反向区域信息拼接）。
  - 提供“文本对齐锚点（3×3）”面板：对选中的文本类元素只读展示/高亮当前对齐锚点（优先 `data-ui-text-align / data-ui-text-valign`；扁平化预览下会从 `.flat-text-inner` 的 `justify-content/align-items` 等 flex 样式推断），并随选中元素与属性变化实时刷新（不提供点击写回）。
  - 检查器尺寸/坐标同时展示两套口径：`iframe` 内的“画布像素”（未缩放）与父页面预览 `transform: scale(...)` 后的“预览显示像素”（按 `state.currentPreviewScale`（舞台缩放）换算），并额外展示预览文档的 `--ui-scale`（UI 缩放）以解释“舞台缩放长期为 1，但元素仍可能随画布变化”的情况。
- `color.js`：颜色文本 → `#rrggbb`/`#rrggbbaa` 转换（供检查器与 autotest 使用）。
- `labels.js`：元素标签（data-debug-label/id/class/tag）提取策略。
- `geometry.js`：DOMRect → 画布坐标系的几何计算工具。
- `shadow_inspect.js`：阴影检查模式（注入样式、按钮状态同步）。
- `ui.js`：与 Workbench 外层 UI 相关的状态切换（预览/扁平按钮态、纯预览模式等）。
  - 纯预览（专注模式）使用独立的 `data-preview-only="1"` 控制面板显隐，不复用 `data-workbench-mode`（browse/editor）。
- 支持“动态文本预览”（data-ui-text）：
  - 当开启后，预览会把带 `data-ui-text` 的元素显示为其绑定占位符文本（示例文本 ↔ 占位符切换），便于检查绑定是否正确；
  - 同时会按该元素的 computed `color` 把占位符包为字面量富文本标签（例如 `<color=#000000>{{lv.xxx}}</color>`），对齐导出 `.gil` 的 `text_content` 真实内容；
  - 该能力仅作用于可视预览 iframe，不影响 compute iframe（校验/扁平化/导出）。

## 注意事项
- **避免循环依赖**：保持依赖方向清晰：`state`/`color`/`geometry`/`labels` 为底层；`overlays`/`inspector` 在中层；`selection`/`scaling`/`render` 在上层；`index` 仅聚合导出。
- **DOM ID 强绑定**：外层 DOM 引用仍由 `src/dom_refs.js` 统一提供；此目录模块不要自行改 HTML 结构或 ID。
- **预览为静态检查模式**：为避免“动效/跳转”导致预览失真或 iframe 导航到 404，预览侧会注入 override 样式禁用 `animation/transition`，并在点击/提交事件上 `preventDefault()` 阻止默认交互。

