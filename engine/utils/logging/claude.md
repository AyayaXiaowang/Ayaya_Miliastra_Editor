# logging 子包

## 目录用途
提供统一的日志与控制台输出相关工具，供引擎与上层应用复用。避免在各处零散创建 logger 或直接打印未清洗的信息。

## 关键文件
- `logger.py`：统一日志接口与基础配置（如 `log_info/log_print/log_warn/log_error` 等）。
- `console_sanitizer.py`：控制台输出内容清洗（`install_ascii_safe_print` / `ascii_safe_print`），避免异常字符或过长输出影响调试体验。
- `console_encoding.py`：Windows 控制台 UTF-8 输出流包装（`install_utf8_streams_on_windows`），用于 CLI/工具脚本在中文路径与非 UTF-8 控制台环境下稳定输出。

## 注意事项
- 不依赖 UI 框架和外部应用层，仅使用标准库与引擎内部模块。
- 日志接口应保持稳定，供 `engine` 与 `app` 统一使用。
- 不在工具函数中吞没异常，错误由调用方负责处理或向上抛出。

## 当前状态
- 日志分层约定：
  - `log_warn/log_error`：默认始终输出（面向用户与诊断摘要）。
  - `log_info`：由 `settings.NODE_IMPL_LOG_VERBOSE` 控制（用于“有用但不必每次刷屏”的信息）。
  - `log_debug`：由 `settings.DEBUG_LOG_VERBOSE` 控制（用于开发期细节与排查，默认关闭）。

---
注意：本文件不记录修改历史，仅描述“目录用途、当前状态、注意事项”。请在结构调整后保持描述同步。

