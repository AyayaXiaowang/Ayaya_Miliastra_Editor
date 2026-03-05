## 目录用途
`app/automation/`：千星沙箱编辑器自动化执行层（高危）：截图/OCR、节点/端口识别、坐标映射、键鼠输入、步骤编排与执行监控。强依赖 Windows 环境与外部 OCR/图像库。

## 当前状态
- **分层**：`capture/`（截图/OCR/模板/鼠标原语）、`input/`（键鼠/等待/日志/子进程）、`vision/`（识别与缓存）、`editor/`（执行器协议+步骤编排）、`config/`（参数注入/Settings 扫描/分支配置）、`ports/`（端口抽象与类型设置）、`runtime/`（真实执行器实现）。
- **对外入口**：UI/CLI 通过协议（如 `EditorExecutorProtocol`、`ViewportController`）访问执行能力；公共门面由 `AutomationFacade` 暴露基础功能。
- **可视化诊断**：执行链路通过 `emit_visual` 推送截图/OCR/点击点等 overlay 给监控面板，用于回放与定位失败原因。

## 注意事项
- 不使用 try/except 吞错；故障直接抛出，由上层决定重试与降级。
- 只通过 `capture/input/vision` 的公开入口调用底层能力；跨模块访问执行器必须走协议方法，禁止调用私有 `_ensure_*`。
- 所有等待/日志统一走 `input.common`；视口变化/画布改变后必须显式 `vision.invalidate_cache()` 失效识别缓存。
