# 目录用途
- 自动化目录的静态扫描规则集合（一次性/本地校验脚本）。

# 当前状态
- 收敛识别与文本规则，避免跨层直依与实现分叉：
  - no_direct_vision_bridge_import.py：禁止在 `app/automation` 内直接导入已废弃的 `vision_bridge` 历史路径（`tools.vision_bridge`），视觉识别能力统一通过门面包 `app.automation.vision` 暴露。
  - no_custom_chinese_regex_or_similarity.py：禁止在运行路径手写“中文正则”与“自实现相似度”；统一走执行器链路中的中文提取入口（`executor._extract_chinese` → `node_detection.extract_chinese` → `ocr_utils.extract_chinese`）与 `engine.utils.text.text_similarity.chinese_similar`。
- `utils.py`：提供 `iter_python_files()` 等共用扫描工具，避免脚本重复实现目录遍历。
- `check_executor_protocol.py`：执行器协议一致性检查入口，要求使用模块方式运行；工作区根目录推断复用 `engine.utils.workspace.resolve_workspace_root`，控制台输出复用 `engine.utils.logging.console_encoding/console_sanitizer`。

# 注意事项
- 这些脚本不改变运行时逻辑，仅用于本地巡检；如需纳入 CI/预提交，请在外层工具链中调用。
- 保持扫描范围为本目录上层的 `app/automation/`；必要时可增加白名单例外（例如门面模块）。
- 校验脚本尽量不要依赖 `engine` 包的导入副作用（例如 `engine/__init__.py` 可能拉起整套验证/布局依赖），优先保持为“只导入 automation 相关模块”的轻量脚本。
- 若脚本需要导入项目根目录下的包，必须在 import 项目前先将仓库根目录加入 `sys.path`，保证可直接执行。
- 为支持相对导入（如 `from .utils import ...`），推荐使用模块方式运行：`python -m app.automation._static_checks.<script_module>`。


