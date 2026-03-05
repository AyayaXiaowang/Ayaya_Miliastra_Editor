## 目录用途
`assets/ui_workbench/src/flatten/` 为 UI Workbench 的“扁平化（flatten）”子系统：将 `flatten.js` 中的 DOM 提取、layer 计算、扁平 HTML 输出与注入等职责拆分为模块；`src/flatten.js` 作为对外门面保持稳定导出 API。

## 当前状态
- **DOM 提取**：`dom_extract.js` 将 compute DOM 提取为 `elementsData`（几何/样式/data-ui-* 元信息），并产出 diagnostics（过滤计数/画布快照）供排障与导出前验收。
- **扁平输出**：`flatten_divs.js` 生成扁平预览用 divs；`layer_data.js` 生成导出复用的 layer 数据；对“视觉为空但具备按钮语义”的元素生成 `button_anchor` 以保持可交互锚点。
- **注入与重写**：`output.js` 负责生成注入 HTML + CSS、重写资源路径/页面跳转链接，并支持直接替换 `<body>` 内容为扁平层。
- **算法子模块**：`colors.js / shadows.js / text_layout.js / ...` 提供颜色吸附、阴影拆层、文本矩形扩展、分组调试覆盖等可复用算法；降级/近似会通过 diagnostics 输出 warning/error。
- **关键语义**：支持多状态初始显隐（默认态可见、其他态 `visibility:hidden`）、`.game-cutout` 背景挖空、`.highlight-display-area` 周围压暗高亮、以及 `data-ui-text-align/valign` 对齐覆盖。

## 注意事项
- 代码运行在浏览器侧：禁止依赖 Node.js API。
- 扁平化输出必须保持无脚本注入（预览 iframe 默认 sandbox 无 `allow-scripts`）。
- 稳定 key 规则（组件组/flat_layer_key 等）必须复用 `src/ui_export/keys.js`，禁止在本目录复制实现。
- 颜色/阴影等存在“允许调色板”与硬校验（例如禁止不透明纯黑）；规则变更需同步 diagnostics 与导出链路。

