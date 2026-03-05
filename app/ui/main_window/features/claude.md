## 目录用途
主窗口的 Feature 收敛层：把需要跨多处修改的装配/连线逻辑逐步迁移为单文件自包含的 feature，提供渐进式的单点扩展口。

## 当前状态
- **协议与安装入口**：提供最小 `MainWindowFeature` 协议与默认安装流程。
- **中央页面装配**：`CentralPagesAssemblyFeature` 收敛各页面信号连接与页面级 binder 调用，降低 `ui_setup_mixin.py` 的连线堆积。
- **选中信号收敛**：库页选中逐步统一为 `selection_changed(LibrarySelection | None)`，未迁移页面保留旧信号回退。
- **右侧面板装配**：`RightPanelAssemblyFeature` 负责执行监控面板创建、右侧面板 binder 连线、tab 注册矩阵（tab_id/标题/模式约束）；管理模式 tabs 由 `management_right_panel_registry.py` 配置驱动。
- **右侧面板唯一入口**：创建 `RightPanelController` 作为主窗口对外入口，业务代码只表达意图，不直接操作 registry/policy。

## 注意事项
- Feature 内不做吞异常兜底；错误直接抛出，便于定位装配顺序问题。
- Feature 不承载复杂业务逻辑；流程应下沉到 controller/service 或 `app.models`。
- Feature 只依赖主窗口公开属性与 `app_state` 提供的稳定依赖，避免反向导入历史 Mixin 私有实现。

