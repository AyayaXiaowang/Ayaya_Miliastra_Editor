## 目录用途
`engine/utils/` 提供引擎层通用工具与基础设施（纯逻辑）：工作区根目录解析、路径/源码读取、图语义工具、缓存路径与指纹、日志、撤销/重做、文本相似度等，供 `engine/*` 与上层模块复用。

## 当前状态
- 子包按语义拆分：
  - `graph/`：图算法与图语义工具（事件流收集、拓扑排序、流程口判定等）
  - `logging/`：统一日志接口与控制台输出清洗/编码
  - `cache/`：运行时缓存路径约定与指纹工具
  - `undo/`：纯模型层撤销/重做核心
  - `text/`：中文/字符串相似度工具
- 根目录常用模块：
  - `workspace.py`：`workspace_root` 解析与 settings 初始化的统一入口
  - `path_utils.py`：路径分隔符归一化等纯文本工具
  - `source_text.py`：源码读取（默认 `utf-8-sig`，兼容 BOM）
  - `name_utils.py`：命名与文件名清洗工具
  - `module_loader.py`：从任意 `.py` 文件加载模块（基于 `exec_module`，避免 deprecated `load_module`）

## 注意事项
- 工具层保持纯逻辑，禁止依赖 UI 与外设 I/O；错误直接抛出，不做静默吞错。
- “工作区根目录”统一称为 `workspace_root`，并统一通过 `workspace.py` 解析/注入，避免各处自行猜测。
- 需要跨子包协作时通过清晰的接口导入，避免循环依赖。

