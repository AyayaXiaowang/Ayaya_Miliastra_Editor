## 目录用途
- 承载“扁平分组树（Flatten Group Tree）”的纯前端实现：数据存储、DOM 索引、渲染与交互事件处理。
- 对外通过 `controller.js` 暴露 controller（refresh / handleTreeClick / handlePreviewSelectionChanged / 显隐与排除开关等），供 Workbench 主页面与 `ui_app_ui_preview` 复用。

## 当前状态
- `controller.js`：controller 门面与核心编排；负责：
  - 从 preview compute 文档提取扁平层数据并渲染树
  - 维护显隐/排除/展开/选中等状态（通过 `store`）
  - 将“隐藏集合”规范化到真实预览 DOM key，并把隐藏状态应用到预览 iframe
- `events.js`：事件分发（树点击/预览选中回流）；强调“列表↔画布”联动的确定性与可测性。
- `dom_index.js`：预览 iframe 内扁平层 DOM 的索引与反查（layerKey ↔ element）。
- `render.js`：纯渲染（给定 layerList + store + toggle 状态 → HTML）。
- `store.js`：状态容器（隐藏/排除/展开/选中/缓存的 layerList 等）。

## 注意事项
- 本子系统会被多个页面复用；避免在内部写死页面特有的 DOM 假设（仅依赖传入/绑定的 container/status 元素）。
- 预览选中回流时，如树容器当前不可见（`display:none`），应避免触发 `scrollIntoView()` 造成外层滚动容器抖动。

