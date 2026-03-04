# ugc_file_tools/commands 目录说明

## 目录用途
- 存放 **可执行的单工具入口脚本**（多数提供 `main()`），由统一分发器调用：`python -X utf8 -m ugc_file_tools tool <name> ...`（或仓库根 `private_extensions/run_ugc_file_tools.py tool <name> ...`）。
- 目标：工具命令名稳定、入口收口；复杂实现下沉到业务模块/`pipelines/`，本目录保持薄封装。

## 当前状态
- 工具注册与命令名以 `ugc_file_tools/tool_registry.py` 为单一真源（`ToolSpec.name` ↔ 模块入口）。
- `reports/`、`diagnostics/`、`misc/` 为“分类导航”视图；对外稳定入口仍是 `ugc_file_tools tool <name>`。
- `.gia` 导出类工具的 canonical 实现入口为 `ugc_file_tools.gia_export.*`；本目录脚本应保持 wrapper 语义，避免复制实现口径。
- 输出约定：可再生产物/报告统一落盘到 `ugc_file_tools/out/`（路径由 `output_paths.py` 收口）；参数侧的 `--output-dir/--output-*` 默认只传 basename/子目录名，不传 `out/` 前缀。
- 危险写盘：标记为危险的工具必须显式加 `--dangerous` 才允许运行（由 dispatcher 强制）。
- 常用工具示例：
  - `inspect_json`：通用 JSON 深层路径查询/探测（用于 dump/report 结构定位）。
  - `inspect_gil_signals`：只读提取 `.gil` 信号表与图内信号节点摘要（诊断/对照）；支持 `--reference-gil` 检测同名信号的 id 与 `signal_index` 口径漂移。
  - `report_gil_dump_json_diff`：将两份 `.gil` 导出为 dump-json 并做深度 diff（按路径列出差异）。
  - `report_gil_payload_root_wire_sections_diff`：wire-level 对照 `.gil` 的 payload_root 段 bytes（按 field_number 对比 length-delimited payload 是否完全一致，用于证明是否发生 payload drift）。
  - `patch_gil_add_motioner`：危险写盘：为指定实体实例补齐“运动器(Motioner)”组项（实例段 `root4/5/1[*].7` 追加 `{1:4,2:1,14:{505:1}}`），输出新 `.gil` 到 `out/`；默认使用 lossless 解码（`prefer_raw_hex_for_utf8=True`）以避免无关字段漂移。
  - `repair_gil_signals_from_*`：按“信号名 scope”的 wire-level 修复入口（内部实现下沉到 `gil_signal_repair/`）。
  - `export_center_scan_base_gil_conflicts` / `export_center_scan_gil_id_ref_candidates` / `export_center_identify_gil_backfill_comparison`：导出中心 UI 专用的子进程 helper（输出 `--report` JSON + stderr 进度行），用于冲突弹窗、缺失 ID 手动选择候选与回填识别，避免 UI 进程解码 `.gil` 触发闪退。
  - `merge_level_select_preview_components`：项目存档维护：合并“选关预览”双元件关卡展示元件为单母体（keep_world 合并 decorations），并同步补丁相关 GraphVariables 与执行图逻辑（默认 dry-run；需工具参数 `--dangerous` 才写盘）。
  - `merge_project_instances_keep_world`：项目存档维护：合并多个实体摆放实例为一个新实例（keep_world），输出新模板 + 新实例（默认 dry-run；需工具参数 `--dangerous` 才写盘并重建索引）。

## 注意事项
- 本目录入口脚本保持“薄”：不要在这里沉淀复杂可复用逻辑；公共能力应放到对应领域模块或 `ugc_file_tools/pipelines/`。
- 本目录脚本不再作为独立 CLI 入口：直接执行会提示改用统一入口（避免“入口满天飞”导致误跑/误用与口径漂移）。
- UI/自动化对接优先提供 `--report <path>` JSON；长任务可在 stderr 输出可解析的进度行供上层解析显示。
- 部分工具会依赖浏览器能力（例如 UI Workbench headless 导出），应避免顶层导入重依赖，并在缺少依赖时给出明确报错提示。
- fail-fast：不写 `try/except` 吞错；错误直接抛出。
- 避免顶层导入重型依赖；也不要让历史 `out/` 目录变成隐式输入依赖（需要输入文件/目录必须显式传参）。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

