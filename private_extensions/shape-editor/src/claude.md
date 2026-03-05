## 目录用途
- `shape-editor` 前端脚本源码拆分目录（由历史单文件 `app.js` 拆分），按职责分文件，便于维护与扩展。

## 当前状态
- 采用“多脚本按顺序加载”（非 ES Module）以保持兼容与行为一致；加载顺序由 `../index.html` 控制。
- 根目录 `../shape_editor_entry.js` 负责触发 `init()` 与 `bootRestoreProjectCanvas()` 启动。
- 主要文件职责（按加载顺序）：
  - `00_core.js`：全局状态/Fabric 初始化/坐标换算/历史记录/批处理与渲染调度/核心启动函数等。
  - `10_layers.js`：图层列表渲染与（对象多时）虚拟滚动。
  - `20_reference_images.js`：参考图管理、取色与右键菜单等。
  - `25_pixel_art_import.js`：像素图导入（PerfectPixel）与像素工作台（改色、会话持久化、实体化生成等）。
  - `30_ps_interactions.js`：旋转/创建/涂抹等交互与 HUD。
  - `40_clipboard.js`：复制粘贴与 Alt 拖拽复制。
  - `50_events.js`：主要 UI 事件绑定（`setupEventListeners()`）。
  - `55_properties_panel.js`：属性面板同步与应用变更。
  - `60_hotkeys.js`：快捷键；像素工作台打开时作为 modal 屏蔽画布快捷键。
  - `70_persistence.js`：localStorage 兜底保存/恢复。
  - `80_export_payload.js`：导出 payload/JSON 构建与 GIA payload 构建。
  - `81_export_gia.js`：导出 `.gia`（实体/元件）请求与日志。
  - `82_export_json_import.js`：导出选中组 JSON、导入 JSON。
  - `90_ui_feedback.js`：状态栏/日志/toast 等反馈与缓存。
  - `91_project_placements.js`：项目实体摆放列表与批量导出。

## 注意事项
- 以“只做拆分、不改语义”为第一原则：跨文件共享依赖仍通过全局变量/函数（与历史版本一致）。
- 尽量避免新增顶层副作用：优先放入 `init()` 或显式函数中。
- 性能关键路径（加载实体/像素批量导入）必须用 `beginBatch()` / `endBatch()` 包裹，避免 `canvas.add()` 触发 O(n²) 的图层列表重渲染。
- 图层虚拟滚动：`10_layers.js` 在对象数量超过阈值时切换为仅渲染视口可见条目；此模式下拖拽排序会禁用。
