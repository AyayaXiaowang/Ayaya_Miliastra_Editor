## 目录用途
`app/ui/workbench/` 存放内置 Web Workbench（UI 工作台）的 **后端桥接层**（不依赖 PyQt6），包括：
- 本地静态 HTTP 服务（用于加载 `assets/ui_workbench/` 前端）
- `/api/ui_converter/*` 接口的路由与门面（从主窗口/PackageController 获取上下文并转发到 service）

## 当前状态
- `bridge.py`：`UiWorkbenchBridge` 作为对外门面（被 `app.ui.ui_workbench_bridge` 薄封装导出），负责绑定主窗口、校验当前项目存档、并在导入后触发 `PackageController.mark_* / save_dirty_blocks` 保存链路；领域逻辑主要委托给 `app.runtime.services.ui_workbench.*`（UI 源码浏览 / 基底缓存 / UI Catalog / 布局导入 / 变量默认值写回注册表等）。其中“修复 UI 变量”接口已改为**只读校验**（不再生成变量文件/不改玩家模板）。
- `http_server.py`：本地静态服务与 `/api/ui_converter/*` 路由（handler 仅做参数解析与转发，不承载领域逻辑；只通过 bridge 的公开方法访问上下文）。
- `utils.py` / `types.py` / `variable_defaults.py`：稳定导入路径的薄封装（re-export 到 `app.runtime.services.ui_workbench`），避免旧代码/私有扩展路径失效。

## 注意事项
- 本目录 **不导入 PyQt6**：UI 侧只负责打开浏览器 URL；后端仅负责静态服务与数据接口。
- 错误不兜底：关键错误直接抛出，便于定位问题；与项目整体“不使用 try/except 静默忽略”约定保持一致。
- 涉及写盘应走存档保存链路（PackageController 的 mark/save_dirty_blocks 等），避免绕过增量保存体系。

