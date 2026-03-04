## 目录用途
`app/runtime/services/local_graph_sim_web/` 存放 **Local Graph Sim** 的浏览器侧静态资源（无需打包构建），由 `local_graph_sim_server.py` 启动的本地 HTTP server 直接提供。

## 当前状态
- **监控面板**：`monitor.html`（`GET /`）+ `monitor_parts/*.js`（拼接后以 `/monitor.js` 提供）用于展示会话信息、Trace/快照与 UI iframe 预览，并通过 `/api/local_sim/*` 调用导出复现包/暂停/单步等能力。
- **共享工具**：`local_sim_shared.js` 统一 query 解析与 API endpoints 读取（优先使用 protocol 自描述）。
- **注入脚本**：`local_sim.js`（`GET /local_sim.js`）注入到 `ui.html`，负责捕获点击并请求 `/api/local_sim/click`，同时应用 server 返回的 UI patches（布局切换/显隐/绑定刷新等）。
- **扁平化预览**：`local_sim_flatten_overlay.mjs` 仅在 `flatten=1` 时注入，用于浏览器侧生成 `flat-*` layers。

## 注意事项
- 资源需保持自包含：不要依赖外部 CDN/构建产物，确保离线可用。
- `local_sim.js` / `local_sim_shared.js` 需保持 ES5 风格；`local_sim_flatten_overlay.mjs` 为 ESModule。
- 文件名与路由属于协议的一部分：调整命名需同步更新 `local_graph_sim_server_http.py` 的路由与注入逻辑。

