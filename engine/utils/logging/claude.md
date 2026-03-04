## 目录用途
统一日志与控制台输出工具：提供 `log_info/log_warn/log_error` 等入口，以及 Windows 控制台编码处理与输出清洗，避免各处零散打印与口径漂移。

## 当前状态
- `logger.py`：统一日志接口与基础开关（info/debug 受 settings 控制）。
- `console_sanitizer.py`：控制台输出清洗（ASCII 安全替换等）。
- `console_encoding.py`：Windows UTF-8 输出流包装，供 CLI/工具脚本入口使用。

## 注意事项
- 仅依赖标准库与引擎层模块，禁止依赖 UI。
- 不使用 `try/except` 吞错；错误直接抛出，由上层决定呈现与中止策略。
- 控制台输出应统一走清洗/编码工具，避免中文路径与异常字符导致的终端显示问题。

