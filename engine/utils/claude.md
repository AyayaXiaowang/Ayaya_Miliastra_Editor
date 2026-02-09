# Utilities 模块

## 目录用途
提供通用工具与基础设施能力，供 UI 与核心逻辑复用。根据语义拆分为若干子包：
- `graph`：图结构算法与节点图数据处理工具（事件分组、拓扑排序、端口判定等）。
- `logging`：统一日志接口与控制台输出清洗工具。
- `cache`：运行时缓存路径与邻域指纹等通用缓存辅助工具。
- `undo`：纯模型层的撤销/重做命令系统（通过 `engine.utils` 顶层延迟导出）。
- `text`：文本相似度与中文近似匹配等通用文本工具。

根目录仅提供：
- `name_utils.py`：命名与文件名规范工具，包含：
  - 标识符/类名/节点文件名清洗：`make_valid_identifier` / `sanitize_class_name` / `sanitize_node_filename`
  - Windows 文件名清洗：`sanitize_windows_filename` / `sanitize_resource_filename` / `sanitize_package_filename` / `sanitize_composite_filename`
  - 通用“唯一名称”生成：`generate_unique_name(base_name, existing_names, separator="_", start_index=1)`，用于在 UI 或引擎层根据已有名称集合生成如 `名称` / `名称_1` / `名称_2`… 等不重复名称
  - 顺序去重小工具：`dedupe_preserve_order(items)`，在保持首次出现顺序的前提下对任意可哈希元素序列做去重，供端口类型推断、事件流任务与 Graph Code 解析等模块统一复用，避免在各处手写 `dict.fromkeys` 或 `seen` 集合逻辑
- `workspace.py`：工作区根目录解析与 settings 初始化（唯一真源）：统一覆盖源码仓库/便携版/直接运行节点图脚本场景，并提供 `resolve_workspace_root` / `ensure_settings_workspace_root` / `init_settings_for_workspace`；其中 `ensure_settings_workspace_root(load_user_settings=True)` 即使在 workspace_root 已注入时也会加载用户设置，保证“先注入根目录、后加载设置”的入口不会口径漂移；同时提供代码生成器复用的 bootstrap 片段生成 `render_workspace_bootstrap_lines(...)`，避免多处复制“向上找根”的代码。
- `path_utils.py`：路径文本归一化（统一真源）：提供 `normalize_slash(text)` 将 `\` 统一为 `/`，用于 UI/CLI 展示与稳定 key，避免各处手写 `replace("\\", "/")`。
- `source_text.py`：源码读取单一真源：提供 `read_text(...)`（默认 `utf-8-sig`，兼容 UTF-8 BOM）与 `read_source_text(...)`（bytes+text+md5），供解析/校验/工具层复用，避免各处重复写 `encoding="utf-8-sig"` 与 md5 逻辑。
- `graph_path_inference.py`：节点图路径推断单一真源：提供 `infer_graph_type_and_folder_path(...)`（从 `.../节点图/<server|client>/...` 推断分类与 folder_path）与 `sanitize_folder_path(...)`，供解析/资源层/校验层复用，避免“folder_path 推断口径”在不同入口漂移。
- `id_digits.py`：数字 ID 文本工具：提供 `is_digits_1_to_10(value)` 用于判断 `GUID/配置ID/元件ID` 等数字标识是否为 **1~10 位纯数字**（允许用字符串包裹数字，允许前导 0）。
- `loop_protection.py`：循环保护工具：提供 `LoopProtection`（纯逻辑、无 I/O），用于防止节点执行/生成代码出现意外无限循环。
- `resource_library_layout.py`：资源库目录布局工具：提供 `共享/` 与 `项目存档/<package_id>/` 的根目录枚举、文件归属判断，以及“默认未归属项目存档”（当前约定为 `测试项目/`）落点函数，供资源索引/校验/迁移与保存策略复用。
- `runtime_scope.py`：运行期作用域（进程内全局）：维护 `active_package_id`（共享根 / 共享+当前存档）这一上下文，供复合节点扫描、节点定义指纹与代码级 Schema 等模块读取，避免跨项目存档全量聚合导致重复 ID 或串包。
- `__init__.py`：延迟导出 `UndoRedoManager` / `Command`，其余功能请直接从子包导入。

## 子包结构
- `graph/`：`graph_algorithms.py`、`graph_utils.py`、`node_defs_fingerprint.py`。
- `logging/`：`logger.py`、`console_sanitizer.py`。
- `cache/`：`cache_paths.py`、`fingerprint.py`。
- `undo/`：`undo_redo_core.py`。
- `text/`：`text_similarity.py`。

统一从子包导入具体工具函数或类：
- `from engine.utils.graph.graph_utils import is_flow_port_name`
- `from engine.utils.logging.logger import log_info`
- `from engine.utils.cache.cache_paths import get_runtime_cache_root`
- `from engine.utils.undo.undo_redo_core import UndoRedoManager`
- `from engine.utils.text.text_similarity import chinese_similar`

## 注意事项
- 工具层不依赖 UI、不直接做外设 I/O，仅依赖标准库与 `engine/*` 内部模块。
- 严格避免循环依赖；需要跨子模块协作时通过清晰的接口函数或类实现。
- 工具层函数不使用 `try/except` 吞没错误，异常应直接抛出，由上层显式处理。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。


