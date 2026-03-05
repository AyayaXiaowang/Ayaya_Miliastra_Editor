## 目录用途
- `src/ui_app_ui_preview/`：`ui_app_ui_preview.html` 对应的前端实现（浏览器侧 ES Modules）。
- 该目录承载“UI源码预览页”的页面级逻辑：文件列表、预览/扁平化生成、左下导出控件/扁平分组联动、导出 GIA/GIL、基底 GIL 缓存恢复等。

## 当前状态
- 该目录的入口由根目录 `ui_app_ui_preview.js` 引用（作为 cache-bust 入口文件）；实际逻辑拆分在本目录的模块中，避免单文件过长难维护。
- 约束：保持模块粒度适中（单文件建议 ~800 行，上限 1000 行），并尽量按“DOM 绑定 / 状态 / API / 预览管线 / 导出”分层。
- 扁平化预览为“纯显示”产物：进入“扁平化”变体时由 `renderPreview()` 统一按需生成/缓存，避免与其它入口产生逻辑分叉；显隐/定位等依赖扁平 DOM 的交互会先确保处于扁平化预览。
  - 选中文件时会先渲染预览（确保扁平 DOM 就绪）再生成“导出控件列表”，从而可把导出控件的 `flat_layer_key` 归一化到预览 iframe 内真实的 `data-layer-key`（口径与实际游戏一致）。
  - 当扁平化结果为空时会显示“失败提示页”，且失败说明基于本次提取的 `diagnostics` 实时生成（例如：全部被隐藏/0尺寸/裁剪范围外/body 为 0×0 等），并暴露 `window.__wb_last_flatten_empty_diagnostics` 便于控制台定位。
- 顶部“延时摄影”按当前预览模式执行：
  - 扁平化模式：按 `.flat-*` 可见层逐个显现；
  - 原稿模式：按当前画布内可见的“有实际视觉贡献”的元素逐个显现（背景/边框/阴影/文本/原生可视控件等），并使用 `display:none -> 恢复原 display` 触发真实布局重排（例如同一行双按钮在只剩一个时会自动填满区域）。
  - 原稿候选不会做“只保留最外层容器”的去重，避免出现“整块一起出现”；容器与子组件可同时参与播放，由 DOM 顺序逐步显现。
- 显隐切换（眼睛图标）在执行前会刷新“当前预览 DOM 索引”（`.flat-*` → layerKey 映射），避免预览重渲染/切换尺寸后索引过期导致“点了没反应/隐藏状态判定错误”。
- 切换画布尺寸**不重渲染 iframe**：扁平化输出已包含 4 档 `.flat-display-area`，原稿模式也仅依赖 `--canvas-width/--canvas-height/--ui-scale` 等 CSS 变量；因此切尺寸只做 `preview.setSelectedCanvasSize(...)`（切换展示区域 + 更新缩放/变量 + 刷新选中框），避免蓝色选中框闪断与 iframe 选中态被清空。
  - 若后续确实发生预览重渲染（例如切文件/切预览变体/手动刷新），则按“layerKey 命中优先 + debug-label(base) 兜底”的策略恢复选中与蓝框，失败才清空，避免检查器残留旧信息造成“切分辨率检查器不变”的错觉。
  - 导出控件列表在切尺寸时**不重建 DOM**：仅原地同步各行的 `data-flat-layer-key` 映射与反向索引，避免滚动位置/展开状态被刷新打断。
    - 行 DOM 会写入 `data-ui-key` 作为稳定身份；原地同步优先按 `ui_key` 对齐（无 `ui_key` 才回退 `widget_id`），避免“重新生成 bundle 导致 widget_id 变化 → 行映射断裂/flat_layer_key 被清空”。
- “画布点选 → 左下联动”会先把选中元素规整到最近的 `.flat-*` 容器层，避免点在扁平层内部子节点时导致左下“导出控件”无法映射/滚动定位。
  - 当扁平层与导出控件模型发生“重叠/归一化误匹配”（典型：点到 `text-level-name` 却跳到 `text-level-author`）时，会使用 `data-debug-label + rect` 做受控纠正，确保仍能稳定命中对应控件条目。
  - 当点选的扁平层不是 `widget.flat_layer_key`（常见：点到 `element` 主体层/装饰层）时，会用 `data-debug-label + rect`（以及极保守的 rect-only 兜底）反推最可能的导出控件，避免出现“右侧检查器已更新但左下导出控件不高亮/不跳转”。
- 导出控件列表的渲染/重绘入口收敛到 `export_widget_list_render.js`：
  - 重绘后统一恢复选中样式（`exportSelectedWidgetId`）并按需消费 `pendingScrollExportWidgetId`，降低“重绘时序/element detached”类不稳定。
  - `exportWidgetPreviewCache` 仅缓存 model（不缓存 HTML），避免 filter/显隐状态变化导致缓存 HTML 漂移。
 - 导出 `.gil/.gia` 时 `pc_canvas_size` 以 bundle 自带的 `canvas_size_key` 为权威（通过 `config.getCanvasSizeByKey` 解析），避免出现“UI 当前选的画布尺寸”和“导出请求发送给后端的 pc_canvas_size”不同步，从而导致写回坐标整体按错误画布缩放（典型表现：在 1600×900 下控件乱飞/丢失）。
- bundle 导出会从 `source_html` 中提取 `data-ui-variable-defaults`（JSON object 字符串），合并写入 bundle 顶层 `variable_defaults`（以及 `variable_defaults_total`），用于后端写回时给“自动创建的实体自定义变量”写入默认值（包含字典变量如 `lv.UI选关_列表`）。
- 预览页新增“导入变量默认值”入口：把当前页面 `data-ui-variable-defaults` 中的 `lv.* / ps.*` 默认值同步写入当前项目的变量库（`管理配置/关卡变量/自定义变量/`），并对 `ps.*` 自动更新玩家模板 `metadata.custom_variable_file` 引用，便于节点图/占位符校验链路直接感知变量规格与默认值。
- UI 多状态导出策略固定为“整态打组（full_state_groups）”（与导出中心/CLI 口径一致）：
  - 每个 state 独立组件组，避免跨状态共享控件；
  - 并将 `<state_group>_content` 这类“共享内容组件”复制进各 state 组内（默认态迁入原件 + 其它态克隆），确保状态切换时内容与底色/边框真正整组一起切换；
  - 代价：导出控件更多、节点图维护更冗余。
- 预览页“状态预览”支持两类多状态结构：
  - **逐 state 元素声明**：`data-ui-state-group + data-ui-state` 写在同一元素上（常见：enabled/disabled 按钮）。
  - **组根节点声明 group**：`data-ui-state-group` 写在父容器上，子节点仅写 `data-ui-state`（常见：overlay 多页/弹窗多态）。
- 支持由 **HTML 页面自身声明**“预览初始态覆盖”（仅预览，不影响导出/写回）：
  - 页面任意元素可声明 `data-ui-preview-initial-states="<group>=<state>; <group2>=<state2>"`（兼容简写 `data-ui-initial-states`）。
  - 分隔符支持：`; , | 换行`（含中文 `；，`）；键值分隔支持：`=` 或 `:`。
  - 应用顺序：
    - 先应用 `data-ui-preview-initial-states`（可多组叠加）
    - 若工具条选择了某个“状态组”进行预览，则再应用 `data-ui-preview-state-preview-base-states`（可多组叠加；用于隐藏干扰层）
    - 最后应用工具条“状态预览”的**单组覆盖**
    - 点击“重置”会清除临时覆盖并恢复到页面声明的初始态 + 源码默认态。
  - **扁平化预览兼容**：扁平化输出会替换 `<body>` 内容，源码根节点可能不在预览 DOM 中；因此初始态声明会回退从 `source_html` 解析，保证在“扁平化/原稿”两种预览下都能生效。
- 支持由页面声明“状态预览基底”（仅预览，不影响导出/写回）：
  - 当用户在工具条选择了某个状态组进行预览时，会先应用 `data-ui-preview-state-preview-base-states="<group>=<state>; <group2>=<state2>"`（兼容简写 `data-ui-state-preview-base-states`）。
  - 用途：自动隐藏教程遮罩/全屏遮罩等干扰层，避免“想预览某个组却必须手动切多个组”。

## 注意事项
- **无打包流程**：依赖浏览器原生 ES Module（`import`/`export`）；静态服务需正确返回 JS MIME（见后端静态服务实现）。
- **ID 强绑定**：预览页的 DOM id 来自 `ui_app_ui_preview.html`，模块内通过 `getElementById` 直连；修改 HTML 时需同步更新对应引用。
- **共享依赖**：预览/扁平化/导出等核心能力复用 `src/preview/*`、`src/flatten.js`、`src/validation.js`、`src/ui_control_group_export.js` 等模块；本目录只做页面编排与交互，不重复实现底层算法。
  - 列表↔画布映射要求“确定性优先”：导出控件列表的 `flat_layer_key` 仅来源于导出端写入的 `__flat_layer_key/flat_layer_key` 并做“可验证的精确归一化”（通过 `findPreviewElementByLayerKey` 命中真实 DOM key）；缺失时 UI 明确拒绝定位/显隐/排除，不做“按 rect/z 猜测”推断，避免误伤与显隐失效。
  - `layerKey`（扁平层定位 key）的 build/parse 必须复用 `src/layer_key.js`，避免容差/舍入口径分裂导致“画布点选/列表定位”不一致。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

