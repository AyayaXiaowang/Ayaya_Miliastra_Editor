# 工具脚本目录（tools）

## 目录用途
存放数据处理与开发辅助脚本，只作为 **CLI 包装层** 使用：负责命令行参数解析、文件或资源收集、调用核心库函数并格式化输出结果。此目录不参与运行时核心逻辑，也不承载兼容层/转发层等基础设施，只保留可以直接执行、具备实际价值的工具入口。

## 关键文件与入口

- 校验与基准 / 冒烟测试：
  - `validate/validate_package.py`：功能包级综合校验（等同 UI「验证」里的“存档包”部分），在项目根目录执行 `python -X utf8 -m tools.validate.validate_package`；仅检查 PackageIndex / PackageView 层结构与引用一致性（关卡实体 / 模板 / 实例 / 管理配置 / 节点图挂载关系等），不对节点图源码做代码规范或语法级静态校验，节点图内部错误请使用 `tools/validate/validate_graphs.py` 等入口。
  - `validate/validate_graphs.py`：节点图与复合节点的统一校验入口，支持 `--all`、目录 / 通配符 / 单文件（可用 `-f/--file` 快速指定）以及 `--strict` / `--strict-entity-wire-only` / `--no-cache`，输出按文件与目录分组并附带类别/错误码摘要，内部统一调用 `engine.validate.validate_files`。
  - `validate/benchmark_validate.py`：对全量节点图执行多轮校验，统计耗时、错误与警告数量，用于观察规则变更前后的性能与问题数量变化。
  - `smoke_test_ui_libraries.py`：UI 库页面（元件库、实体摆放、节点图库、存档库）的最小化冒烟测试入口，在项目根目录执行 `python -m tools.smoke_test_ui_libraries`；脚本仅构造相关 QWidget 并执行基础刷新与筛选（统一走库页协议 `set_context/reload`），不创建或删除任何资源文件；如运行环境缺少 onnxruntime 相关 DLL，可使用 `--skip-ocr` 跳过 RapidOCR 预热，仅做 UI 构造与刷新测试。
  - `build_ui_pages.py`：UI 页面构建脚本，在项目根目录执行 `python -X utf8 -m tools.build_ui_pages <ui_page_id>`，会从原始 HTML 执行扁平化生成 `_flattened.html`，并根据管理配置中的 UI 文本绑定资源将 `{{占位符}}` 替换为 `{1:ps./lv.变量.路径}` 形式的引擎变量引用。
    - 页面发现：通过扫描 `projects/锻刀英雄/ui_mockups/*_ui_mockup.html` 自动发现可构建页面（可用 `python -X utf8 -m tools.build_ui_pages --list-pages` 查看）。
    - 占位符同步：支持 `python -X utf8 -m tools.build_ui_pages --sync-placeholders <ui_page_id>`，将原始 HTML 中的占位符同步到对应的 UI 文本绑定 JSON 中（未绑定项可先留空，后续在管理配置界面补齐）。
  - `validate/validate_graph_cache_integrity.py`：校验 graph_cache JSON 的结构一致性（节点 / 边 / 端口名称对应关系），在项目根目录执行 `python -X utf8 -m tools.validate.validate_graph_cache_integrity`，可按单文件或目录进行定向检查。

- 运行期管理与诊断：
  - `clear_caches.py`：运行期缓存清理和重建入口（`python -X utf8 -m tools.clear_caches`）；支持 `--clear` 以及 `--rebuild-index/--rebuild-graph-caches` 的真实重建；提供 `--root <workspace>` 便于在临时目录/CI 中做无副作用验证。
  - `check_runtime_data_dirs_not_packages.py`：静态检查运行期数据目录（如 `app/runtime/cache`）中是否误放了 `*.py`（尤其 `__init__.py`），用于防止“数据目录被做成可导入包/模块”的结构回归。
  - `debug_graph_variable_default_value.py`：节点图变量默认值诊断脚本。会分别从源码 AST（GRAPH_VARIABLES）、`ResourceManager.load_resource` 以及 `app/runtime/cache/graph_cache/<graph_id>.json` 三个路径读取同一变量的 `default_value` 并打印，便于快速判断“UI 显示 None”是解析问题还是运行进程/路径不一致导致的数据源偏差。
  - `verify_layout_equivalence.py`、`verify_layout_copy_toggle.py`、`check_validate_graph_line_numbers.py`：比对布局缓存与 LayoutService 输出，验证 DATA_NODE_CROSS_BLOCK_COPY 开关下 UI 的“克隆布局+差异合并”是否与引擎增强模型一致，或辅助核对校验报错的行号是否与 graph_cache / 源码中的位置信息一致（缓存根目录以 `settings.RUNTIME_CACHE_ROOT` 为准，默认 `app/runtime/cache`）。
  - `dump_layout_y_debug.py`：对任意 graph_cache 图生成 `_layout_y_debug_info` 覆盖统计，辅助排查“调试感叹号缺失”等布局调试问题。
  - `compare_layout_positions.py`：在缓存坐标与 LayoutService 实际输出之间做差分，可选择重置初始坐标并输出跨事件的位移统计；事件归属会沿流程连线与数据连线一并传播，避免节点因仅连接数据端而落入“<无事件>”。
  - `scan_capture_emit.py`、`find_wrappers.py`、`print_node_counts.py`：扫描自动化捕获逻辑、薄包装函数及各类节点数量分布，用于梳理节点生态与自动化能力覆盖面；其中 `print_node_counts.py` 固定以脚本位置推导工作区根目录，避免因从子目录运行导致运行期缓存写入错误路径。

- 代码体量与实现规范：
  - `find_large_modules.py`：扫描超长 Python 文件，输出函数 / 类统计以及拆分建议，辅助定位需要重构的大模块。
  - `lint_node_impls.py`、`check_impl_node_specs.py`：以 `plugins/nodes/registry.py` 静态注册表为扫描源，对节点实现做一致性校验（实现函数存在、声明了 `@node_spec(category=...)`、禁止 `print()` 等）。
  - `check_duplicate_config_names.py`：扫描 `engine/configs` 下的重复类名；默认只输出报告不失败，可用 `--fail-on-duplicates` 作为强约束开关接入 CI。
  - `dedupe_node_specs.py`：清理相邻重复的 `@node_spec(...)` 装饰器块（默认仅检查，`--apply` 才会改写源码）；仅处理注册表引用的实现文件，避免误改 shared/helpers。
  - `split_impl_modules.py`：旧版 `node_implementations/*_impl.py` 单文件实现拆分迁移工具；当前仓库通常不需要，若未找到旧版输入文件会返回非零码并提示替代方案。

- 风格与 UI 规范检查：
  - `check_unstyled_qt_windows.py`：扫描继承 QDialog 却未使用 BaseDialog/FormDialog 的类，以及直接实例化原生对话框的位置，辅助统一主题样式。
    - 额外启发式：若文件包含常见基础控件（spin/combo/table/tree/list/text edits 等）且未引用 ThemeManager/StyleMixin，会输出“可能未套主题样式”的提示供人工复核。
  - `check_no_direct_qmessagebox.py`：扫描直接使用 `QMessageBox` 的位置，要求通过 `ui.foundation.dialog_utils` 提供的封装入口统一使用消息框。
  - `check_no_direct_qdialog.py`：扫描直接使用 `QDialog` 的位置；除基础封装层外，新对话框应优先继承 `BaseDialog` / `FormDialog` 或管理类对话框基类，避免在业务模块中直接从 `QDialog` 派生。
  - `generate_node_docs.py`、`generate_node_checklist.py`、`generate_plugin_registry.py`：基于 `@node_spec` 生成文档、清单与静态注册表；其中 `generate_plugin_registry.py` 通过字符串形式的模块路径与 `importlib.import_module` 实现懒加载注册，兼容包含全角符号的实现文件名。
  - `generate_server_stub.py`：旧版 `node_implementations` 的类型桩生成器；当前仓库已下线，运行会返回非零码并提示迁移后的路径与替代方案。
  - `extract_nodes_from_kb.py`：从知识库导出节点定义的批处理脚本。

- 管理配置与定义生成：
  - `create_example_signal_all_types_package.py`：使用 ResourceManager / PackageIndexManager 创建一个演示 `signal_all_supported_types_example` 的示例存档包，并将 `server_signal_all_types_example_01` 节点图挂载到新建存档的关卡实体上，同时在存档索引中登记该信号的引用，便于在 UI 中直接打开和调试该教学用例。


- 布局与图像能力：
  - `debug_cross_block_copy.py`：从节点图 Python 源文件直接解析并调用 `LayoutService` 执行一次完整布局；脚本会先调用 `settings.set_config_path(WORKSPACE)` 以保证解析阶段的 quiet layout 可推导 workspace_path。支持按节点标题筛选目标数据节点，输出其所属基本块、位置与入/出边结构，辅助排查跨块复制与副本连线问题。
  - `audit_layout_copy_consistency.py`：对任意节点图执行一次完整布局后，审计跨块复制的一致性（副本归属、LayoutBlock 归属、启用复制时的幂等性等），用于把“视觉问题”快速落地为可定位的结构化错误信息；脚本会先调用 `settings.set_config_path(WORKSPACE)` 以保证解析阶段的 quiet layout 可推导 workspace_path。
  - `color_block_detector_internal.py`：基础色块检测与节点矩形检测的内部实现，供图像识别管线复用。
  - `one_shot_scene_recognizer.py`：一步式整屏识别节点矩形、标题与端口坐标，输出调试截图到运行时缓存根目录下的 `debug/one_shot_scene_recognizer/debug_steps/`（默认 `app/runtime/cache/debug/one_shot_scene_recognizer/debug_steps/`，也可用环境变量 `GRAPH_GENERATER_DEBUG_OUTPUT_ROOT` 覆写输出根目录），端口模板位于 `assets/ocr_templates/4K-CN/Node`；OCR 工具采用惰性导入以避免循环导入；内部通过基于 IoU 的 NMS 与同行去重规则过滤空间上高度重叠或同一行的重复模板命中，只保留每行用于构造端口索引的有效主端口，模板名以 `Settings` / `Warning` / `Dictionary` 开头的装饰类模板不参与同行去重；模板匹配阶段默认使用统一基础阈值，并对名称以 `Process` 开头的流程端口模板使用不高于 70% 的匹配阈值、对名称以 `Generic` 开头的泛型端口模板使用不高于 75% 的匹配阈值，以提高细窄流程端口与泛型数据端口的识别召回率；同时提供基于模板匹配结果的调试结构（包含被 NMS 与同行去重抑制的候选），供 UI 层在“深度端口识别”等调试功能中直接可视化所有置信度≥阈值的模板命中与被排除原因。
  - `check_executor_private_access.py`：静态检查执行器私有方法访问规则，扫描整个仓库内的 Python 源码，禁止出现 `executor._ensure_*` 或 `*_executor._xxx` 这类跨模块访问下划线开头成员的模式，仅允许在类内部通过 `self` / `cls` 访问私有实现；适合在本地开发或 CI 中定期运行。
## 注意事项与边界条件

- 所有脚本应尽量幂等，避免在无明确确认的情况下改写源码或资源库数据。
- 运行路径统一假定为项目根目录（即与 `README.md` 同级的位置），如需在其它位置执行，应显式传入 `--root` 或使用绝对路径。
- 控制台输出默认保持精简，仅在关键阶段输出少量信息；为兼容 CP936 / GBK 等控制台编码，工具脚本的 `print` 建议只使用 ASCII 安全字符（本目录已有脚本在必要时通过 `-X utf8` 与 `io.TextIOWrapper` 修正编码）。
- 临时调试或一次性迁移脚本可以放在本目录，但异常应直接抛出由调用方处理，不在脚本内用 `try/except` 吞没错误。

### 分层与依赖约束

- 工具脚本统一经 `engine` 顶层 API 导入，不直接依赖内部 `core/*` 实现细节。
- 工具脚本统一经 `engine` 顶层 API 导入，不直接依赖 `engine` 的私有实现细节（只依赖明确暴露的公共入口）。
- 核心层（`engine/*`）禁止直接引用 `tools/*` 模块；自动化能力在应用层通过 `app.automation.*` 使用。
- 视觉识别能力统一通过 `app.automation.vision` 访问（内部委托 `vision_backend`），本目录不再提供单独的视觉桥接模块，CLI 如需视觉能力请直接导入 `app.automation.vision`。
- 当脚本需要基于节点显示名称生成文件名时，应使用 `engine.utils.name_utils.sanitize_node_filename` 或相关工具函数，避免产生非法文件名或意外子目录。

### 当前能力概览

- 节点图代码规范校验与结构校验全部复用 `engine.validate.validate_files` 与 `engine.graph_code.validate_graph`，tools 目录仅负责组合文件列表与输出。
- 功能包综合验证通过 `engine.validate.ComprehensiveValidator` 完成，运行时验证适配器则由 `runtime.engine.node_graph_validator` 提供。
- 节点图相关工具默认假设图主要由 AI 或脚本通过 Graph Code 生成，只做静态结构与语义检查，不会执行任何节点实现逻辑；真实运行仍由官方 UGC 编辑器 / 游戏环境负责。
- OCR / 中文处理能力在工具与运行时之间统一：通过 `app.automation.vision.ocr_utils` 获取 RapidOCR 引擎、提取中文文本，保证识别行为一致。
- 主题适配辅助：`check_hardcoded_colors.py` 用于扫描 UI 源码中的硬编码颜色字符串（如 `#FFFFFF`、`#333333`、`QColor("#FFF")` 等），并在 `tools/hardcoded_colors_todo.md` 生成按文件分组的整改 Todo 列表，便于逐项迁移到 `ThemeManager/Colors` 体系；`tools/hardcoded_colors_todo.md` 作为生成的待办清单文件，可随时重新生成并按文件自上而下勾选完成项，保持勾选状态与实际迁移进度同步，用于跟踪“浅色/深色主题下不再直接依赖硬编码颜色”的总体完成度，并应与 Colors 落地进度保持一致。

## 当前状态
- 运行方式统一推荐从项目根目录使用 `python -X utf8 -m tools.<module>` 或 `python -X utf8 -m tools.validate.<module>`；tools 根目录脚本也兼容 `python tools/<script>.py`（通过 `tools/_bootstrap.py` 统一注入 workspace_root），但 `tools/validate/` 下入口统一要求 `-m`。
- 布局相关脚本在调用 `LayoutService.compute_layout` 时会显式传入 `workspace_path`（通常为脚本所在仓库根目录），避免布局层依赖隐式 workspace_root 回退或全局状态。
- `test_global_copy_rules.py` 为 `GlobalCopyManager` 的规则级自检脚本：规则2校验的是“旧连线语义断开并重定向到副本”（edge.id 可能保持不变并被原地重定向），而不是要求删除原 edge.id。
- 生成类脚本（如 `generate_plugin_registry.py` / `generate_node_docs.py` / `generate_node_checklist.py`）与仓库内节点定义同步维护；临时脚本完成一次性任务后会下线或并入正式入口，目录保持精简。

---
注意：本文件不记录任何修改历史，仅描述本目录的用途、当前能力与使用注意事项。


