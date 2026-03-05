# ugc_file_tools/pipelines 目录说明

## 目录用途
- 放置 **UI/CLI 共用的业务编排（pipeline）**：将“参数解析/交互”和“核心步骤编排”解耦，保证同一条链路只实现一次。
- 典型链路：`.gil → 项目存档`、`项目存档 → 导出/写回（.gia/.gil）`。

## 当前状态
- `project_writeback.py`：项目存档 → 写回生成 `.gil`（模板/实体/结构体/信号/节点图/UI 等），统一 out→用户目录复制策略与进度回调；支持 selection-json 的选择式写回与若干高级策略（同名冲突策略、`prefer_signal_specific_type_id`、`entity_key/component_key` 手动 overrides 等）。
  - 自定义变量（注册表）写回：支持 selection-json 的 `selected_custom_variable_refs`（owner_ref+variable_id）将变量补齐写入输出 `.gil` 的 override_variables(group1)；仅补齐缺失，同名类型不一致默认不覆盖并在报告列出。
  - out→用户目录复制使用“临时文件 + `os.replace`”的原子覆盖：避免大文件复制过程中被其它进程读到半文件（表现为无法解析/导入失败），也避免复制中断直接写坏目标文件。
  - 模板写回阶段会同步写回模板 `decorations` 到 `.gil` 的装饰物段 `payload_root['27']`（root27）；不再通过“自动启用实例写回闭包”的方式绕写到实体摆放段。
  - 实体摆放写回：当所选 `instance_id` 在 base `.gil` 中不存在时，会按“新增实例（克隆样本 entry）”策略写入输出；模板类型/样本不足时会 fail-fast 报错，避免产物进游戏不可见。
  - 节点图写回可自动启用信号定义写回：从 GraphModel 收集 `__signal_id` 与“静态绑定的信号名”，并兼容监听信号事件节点（`node_def_ref.kind=event`）的 `key/title` 形态，避免仅导出节点图时产出缺信号定义的 `.gil`。
  - 信号写回支持“占位无参信号”写入开关：`signals_emit_reserved_placeholder_signal` 控制是否将 0x6000/0x6080 口径的保留位占位信号写入产物（默认关闭：不写 entry，但预留其 node_def_id/端口块）。
- 写回前可按需补齐 base `.gil` 的基础设施段：当检测到 `root4/11` 初始阵营互斥字段缺失（entries 缺 key=13）或 `root4/35` 默认分组列表缺失时，会先从 bootstrap `.gil`（默认：`ugc_file_tools/builtin_resources/seeds/infrastructure_bootstrap.gil`）复制缺失字段（只补缺失、不覆盖 base 其它业务段），降低官方侧更严格校验失败的风险；当 bootstrap 判定无需写盘（`changed=False`）时，pipeline 会继续沿用原始 input_gil 作为后续步骤输入，避免引用不存在的中间产物。
- `gil_to_project_archive.py`：`.gil` → 项目存档导入（可选 codegen/validate），支持选择性导入与资源段开关（跳过大段解析以加速）。
- `project_export_gia.py`：项目存档 → 导出节点图 `.gia`（含依赖 bundle），支持多图 pack、bundle 模式、UIKey/entity_key/component_key 回填（含手动 overrides），以及可选“导出后注入到目标 `.gil`”。
  - 导出默认尽量 **自包含**（复合节点/信号依赖随图打包），避免导入到空存档时缺依赖而无法展开。
- 其它管线：模板/玩家模板/实例 bundle 的导出导入等（见同目录 `project_export_*` / `*_to_project_archive.py`）。

## 注意事项
- pipeline 只接收 **显式参数**，保持“纯编排”；具体读写实现下沉到领域模块（如 `project_archive_importer/`、`gia_export/` 等）。
- 整体以 fail-fast 为主：不吞异常；错误交由上层（UI/CLI）统一处理与展示。
- 但“导出中心/写回”这类批处理链路允许 **best-effort**：对单个节点图 strict 解析失败（`GraphParseError`）会跳过该图并在 report 中体现，避免阻断其它资源写回。
- 跨模块复用必须走 **公开 API（无下划线）**，避免越层导入私有实现造成边界坍塌。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

