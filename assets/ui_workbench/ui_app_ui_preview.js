// UI源码预览页入口（薄入口）
// 说明：
// - 原 `ui_app_ui_preview.js` 过长，已按职责拆到 `src/ui_app_ui_preview/*`。
// - 该文件仅保留为 HTML 的稳定入口（用于 cache-bust querystring）。
import { main as runUiPreview } from "./src/ui_app_ui_preview/main.js";

runUiPreview();

