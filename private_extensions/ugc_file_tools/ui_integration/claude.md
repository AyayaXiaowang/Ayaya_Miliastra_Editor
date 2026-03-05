# ui_integration 目录说明

## 目录用途

- `ugc_file_tools` 的 **主程序 UI 集成层**：把工具链能力接入 Graph_Generater 的界面（导入/导出中心、GIA 小工具等）。
- 本目录只负责 **UI 编排/参数收集/进度展示**；核心业务逻辑位于 `ugc_file_tools/commands/**`、各业务子模块与 `ugc_file_tools/pipelines/`。

## 当前状态

- **统一入口**：PACKAGES 页工具栏按钮（`package_toolbar.py`）→ `export_wizard.py`（非模态向导式对话框，导入/导出/修复信号统一在此）。
- **头部空间收敛**：导入/导出中心顶部仅保留极简标题行（`QLabel` 标题 + 样式），不占用大段说明文本；界面空间优先留给左侧资源选择与右侧配置/表格。
- **入口收敛**：目前仅在 PACKAGES 页注入入口按钮；不在“节点图库/图画布右上角”注入独立导出按钮，避免多入口口径漂移。
- **导出中心（默认尺寸）**：弹窗初始尺寸按屏幕可用区域自适配，并以主程序窗口为上限；步骤1 splitter 默认保证右侧“写回配置”的浏览按钮可见，避免用户左右拖拽。
- **子进程执行**：`_cli_subprocess.py` 封装运行 `ugc_file_tools` CLI（隐藏控制台窗口、解析 stderr 进度、收集尾部日志）；重任务尽量隔离到子进程，避免 PyQt 主线程卡顿。
- **资源与选择口径**：`graph_selection.py` 统一“选图模型”参数形态；`resource_picker.py` 提供 project/shared 资源树选择器（元件/实体摆放/玩家模板 JSON 的叶子节点优先展示 JSON 内的 `name`，仅扫描文件头以避免大文件卡 UI；并过滤 `templates_index.json`/`instances_index.json`/`player_templates_index.json` 与 `原始解析/*.pyugc.json` 等辅助产物，避免误选进入导出/写回流程）。
  - 资源条目的显示文本统一由选择器内部计算，并在“已选清单”中以 `展示文本 — 相对路径` 的形式核对，减少“树里看的是名字、列表里看的是路径”的心智割裂。
  - 管理配置（`mgmt_cfg`）为 **白名单收敛**：仅展示导出中心实际消费的代码级定义资源（`管理配置/信号/*.py`、`管理配置/结构体定义/{基础结构体,局内存档结构体}/*.py`），并排除 `校验*.py` 等工具脚本，避免把“管理配置目录里的杂项 JSON/缓存/历史工件”暴露给用户造成误选。
  - 管理配置叶子节点优先显示真实名字（如 `signal_name/struct_name/VARIABLE_FILE_NAME`），避免仅显示数字/ID文件名。
  - 导出中心 UI 中 `mgmt_cfg` 分类标题显示为“管理配置（信号/结构体）”；自定义变量来自 `管理配置/关卡变量/自定义变量注册表.py` 的静态解析结果（以 `custom_vars` 虚拟资源条目形式出现在左侧资源树，可按 owner 分组/按变量粒度勾选）。
- **导出中心拆分**：`export_center/` 存放纯逻辑（state/plan/actions/policy/models），对话框 UI 由 `export_center_dialog_*.py` 组装，后台执行由 `export_center_worker.py` / `export_center_gil_identify_worker.py` 承载。
- **导出中心预检**：启动导出前会对“用户勾选的输入文件”做轻量校验；对明显不符合单文件约定的输入（例如索引 JSON）自动跳过并在导出完成时汇总提示，同时写入 report 供执行页/历史查看。
- **导出中心（元件导出）**：自动选择两条策略并允许混合产出：
  - 模板导出（`export_project_templates_to_gia`）：语义生成 `.gia`（包含自定义变量），不要求 source，适合“空模型+自定义变量”等项目内元件模板。
  - 保真切片（`export_project_templates_instances_bundle_gia`）：当模板 JSON 携带 `metadata.ugc.source_*` 时，从真源 bundle.gia 做 wire-level slice 导出 templates+instances，以保留装饰物实例。
  - UI 仅在“模板包含装饰物但无法保真切片”时提示装饰物未随导出，避免普通模板导出出现“缺 source/回退”式的困惑。
- **导出中心（玩家模板导出）**：GIA 模式支持从 `战斗预设/玩家模板/*.json` 导出 `player_template.gia`（含自定义变量），需要提供“玩家模板 base .gia”（真源导出的默认玩家模板），产物落盘到 `ugc_file_tools/out/<out_dir>/player_templates/`。
- **导出中心（GIA 打包）**：启用“打包合并(.gia)”时可选填写输出文件名（仅文件名）；留空则使用默认 `<package_id>_packed_graphs.gia`。
- **导出中心（GIA 回填）**：GIA 模式提供“基底 `.gil`”用于节点图 `entity_key/component_key` 回填；并支持可选“占位符参考 `.gil`”覆盖（留空=使用基底）。
- **导出中心（实体摆放）**：写回实体摆放时，若所选实例在 base `.gil` 中不存在，会按“新增实例（克隆样本 entry）”策略写入输出 `.gil`；若无法解析模板类型/样本不足会 fail-fast 报错（避免产物进游戏不可见）。
- **导出中心（UI 写回）**：当用户选择 `UI源码` 且 Workbench bundle 过期/缺失时，会在导出前通过子进程调用 `tool export_ui_workbench_bundles_from_html` 自动更新 `UI源码/__workbench_out__` 产物，再继续写回导出（依赖 Playwright/Chromium）。
- **导出中心（自定义变量/注册表）**：GIL 模式在左侧资源树提供“自定义变量（注册表）”分类（`custom_vars` 虚拟条目）；按 owner 分组展示（关卡实体/玩家/第三方 owner），**同一 owner 必须整组一起勾选**（每组仅提供一个 `（全部）` 入口）。
  - 当用户勾选了 `UI源码`（并将写回 UI）时，UI HTML 中引用到的变量会被自动加入“已选资源”（强联动，避免漏写回）。
  - 当用户勾选了 `元件库(templates)` 或 `实体摆放(instances)` 时，对应模板/实例 ID 的第三方 owner 变量组也会被自动加入“已选资源”（按 owner 整组）。
    - 为避免 Qt 侧 re-entrancy 崩溃，自动勾选/移除使用 `QtCore.QTimer.singleShot(0, ...)` 延迟执行（而不是在 selection_changed 回调栈内同步修改 selection）。
  - 写回语义：仅补齐缺失变量；不修改已存在同名变量当前值；同名但类型不同默认不覆盖（报告列出）。
- **导出中心（GIL 冲突提示）**：UI 布局同名冲突弹窗会明确提示触发条件：仅在启用“UI 写回”时出现；“UI 回填记录”仅用于 ui_key→GUID 回填，不会启用 UI 写回。
- **稳定性**：导出中心的 base `.gil` 冲突扫描与“回填识别”均在子进程内执行，避免 `.gil` 解码在 UI 进程内触发 Windows access violation（闪退）。
- **回填识别进度**：导出中心步骤 2“识别”支持进度条展示；识别 worker 会持续发出 progress 事件供 UI 更新。
- **步骤2（回填分析）双标签页**：回填表按“缺失/待修复”和“已就绪”拆分为两个标签页；标签标题显示条目计数，用于替代冗长的汇总文本。
- **交互收敛**：步骤2不提供“清空结果”按钮；需要重新识别时直接再次点击“识别”即可。
- **进度条固定底部**：步骤2“识别”与步骤3“执行”的进度条位于各步骤页底部固定区域，不随内容滚动。
- **步骤导航（前置禁用）**：当步骤1未勾选任何资源时，顶部“步骤2/步骤3”页签与 footer“下一步”将直接置灰禁用，避免点击后再弹窗提示。
- **模式切换裁剪可见性**：导出中心切换格式会按模式限制资源分类并裁剪已选项；当发生裁剪时，会在左侧摘要区域显示提示语，避免“勾选消失但原因不明”。
- **回填识别表格状态**：当启用“UI 自定义变量自动同步”时，UI源码引用到但 base 缺失的变量在识别表中标为“一同导出”（写回会自动补齐），避免误判为失败。
- **回填识别缺失兜底**：识别表中实体/元件 ID 缺失行支持双击→从地图/参考 `.gil` 的候选全集中手动选择一个 ID；该选择会作为本次导出/写回的 `--id-ref-overrides-json` 透传到子进程生效（覆盖默认回填 0 的行为）。
- **其它入口**：`gia_tools_dialog.py`（装饰物合并/居中、元件↔实体转换等 wire-level 工具；作为独立对话框，不占导出中心顶部空间）。
- **Legacy**：历史 `export_*.py` 导出入口保留为**兼容薄封装**（统一跳转 `export_wizard.py` 的导出中心，并可指定默认格式），不再维护独立导出对话框；`read_*.py` 仍作为导入入口由“导入/导出中心”复用。

## 注意事项

- 与主程序交互应走公开 API（无下划线），不要调用 controller/executor 的私有方法。
- 避免顶层导入重型依赖（尤其 PyQt6）；尽量在入口函数内延迟导入。
- 默认仍 fail-fast（worker/子进程失败会直接失败并提示）；但导出中心会在启动前做预检并对“误选文件/索引文件”等可预期输入问题进行软跳过，避免单文件问题中断全流程。
- GIL 导出输出路径：相对路径按 `workspace_root`（子进程 cwd）解析，并做“禁止覆盖输入 base `.gil`”校验，避免误覆盖导致解析/写回不稳定。
- UI 样式尽量复用 `ThemeManager` 的现成样式与已存在 token，避免引用不存在的 token 导致对话框组装期崩溃。
- 复用/缓存 UI 控件时，确保 widget class/type 稳定（不要在点击回调里动态定义 class），避免 `isinstance` 判定失效。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。
