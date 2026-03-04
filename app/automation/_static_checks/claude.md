## 目录用途
`app/automation/_static_checks/` 存放自动化子系统的本地静态检查脚本（一次性巡检/开发期护栏），用于守住依赖边界与关键约定。

## 当前状态
- **规则脚本**：例如 `no_direct_vision_bridge_import.py`（禁止使用历史 `tools.vision_bridge` 路径）、`no_custom_chinese_regex_or_similarity.py`（禁止手写中文正则/相似度，统一走 OCR/文本相似度公共入口）。
- **扫描工具**：`utils.py` 提供 `iter_python_files()` 等通用遍历助手。
- **协议一致性**：`check_executor_protocol.py` 检查执行器协议一致性，workspace_root 推断复用 `engine.utils.workspace.resolve_workspace_root`，控制台输出复用 `engine.utils.logging` 的编码/净化工具。

## 注意事项
- 这些脚本不改变运行时逻辑，仅用于本地巡检；如需纳入 CI/预提交，应由外层工具链调用。
- 扫描范围默认面向 `app/automation/`；必要时通过白名单控制例外。
- 脚本应保持轻量，避免依赖 `engine` 的重型导入副作用；推荐使用模块方式运行：`python -m app.automation._static_checks.<script_module>`。

