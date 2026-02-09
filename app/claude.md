# 目录用途
应用层装配：UI/CLI/运行态的组织与对接，仅通过公共 API 使用引擎与插件。

# 公共 API
不对外提供库级 API；对外仅有应用入口（CLI/GUI）。

# 依赖边界
- 允许依赖：`engine/*`、`plugins/*`
- 禁止依赖：`assets/*`（除只读）、任何内部开发工具链（默认不入库）

# 注意事项
- 运行态状态与缓存集中在 `app/runtime/` 管理。 

# 当前状态
- 设置与配置统一从 `engine.configs.settings` 获取
- 自动化能力仅从 `app.automation` 访问
- 应用元信息集中在 `app/app_info.py`（版本号、上游仓库信息、更新检查策略 `APP_UPDATE_CHECK_MODE`；当前默认 `latest_release_version`：仅对比本地版本号与 GitHub 最新 Release tag），供 UI 的“检查更新/下载更新包”等功能使用
- UI 启动装配已管线化收敛到 `app/bootstrap/`（OCR 预热顺序约束、看门狗、异常钩子等），`app/cli/run_app.py` 保持薄入口（仅解析参数与注入 settings）
- 不再依赖任何 `core.*` 兼容层
- `python -X utf8 -m app` 可作为 UI 启动短入口（委托到 `app.cli.run_app`）

