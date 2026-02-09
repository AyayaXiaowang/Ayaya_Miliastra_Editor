## 目录用途
`app/runtime/services/local_graph_sim_web/` 存放 **Local Graph Sim** 的浏览器侧静态资源（无需打包构建），由 `local_graph_sim_server.py` 启动的本地 HTTP server 直接提供。

## 当前状态
- `monitor.html`：监控面板页面（`GET /`）
  - 左侧：信号发送 / 布局切换 / 会话信息
  - 中间：iframe 预览 UI（可调分辨率、可缩放适配窗口）
  - 右侧：Trace 与实体/变量快照
- `local_sim.js`：注入脚本（`GET /local_sim.js`）
  - 自动注入到 `GET /ui.html` 返回的 UI HTML 中
  - 捕获点击（`data-ui-role="button"` + `data-ui-key`）并请求 `/api/local_sim/click`
  - 应用 server 返回的 patches（layout 切换、状态组显隐、文本绑定刷新、highlight dim 模拟等）

## 注意事项
- 资源需保持 **自包含**：不要依赖外部 CDN/构建产物，避免离线环境不可用。
- `local_sim.js` 需保持 ES5 风格（更适合“工具页面”的广泛兼容与调试）。
- 文件名与路由为协议的一部分：若调整命名，需要同步更新 `local_graph_sim_server_http.py` 的路由表与注入逻辑。
