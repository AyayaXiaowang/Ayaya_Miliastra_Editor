## 目录用途
`app/ui/_static_checks/` 存放 UI 层的静态扫描脚本（仅本地巡检），用于发现样式/QSS 散落、违规用法等一致性问题。

## 当前状态
- `check_inline_styles.py`：扫描 `app/ui/**/*.py` 中的 `setStyleSheet(...)` 调用，列出“直接内联字符串/拼接 QSS”的位置，便于逐步迁移到 `ThemeManager` + `theme/styles/` 的集中样式工厂。
- 扫描范围默认忽略 `app/ui/foundation/`（基础设施层）与本目录（避免自扫）；脚本同时忽略 `setStyleSheet("")` 这类“清空样式”的调用。

## 注意事项
- 脚本**不修改运行时逻辑**，只输出诊断结果；推荐模块方式运行：`python -m app.ui._static_checks.check_inline_styles`。
- 需要 CI/本地强制时可加 `--fail`：当检测到内联 QSS 时返回非 0；如需同时打印“来源未知（可能为变量/间接拼接）”可加 `--show-unknown`（或 `--verbose`）。
- 遵循项目异常策略：不写 `try/except` 兜底；若遇到语法错误或无法解析的文件应直接抛出，便于定位修复。

