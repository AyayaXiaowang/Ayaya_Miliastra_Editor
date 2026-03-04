# ugc_file_tools/unified_cli 目录说明

## 目录用途
- 承载 `ugc_file_tools/ugc_unified.py` 的统一 CLI **实现拆分**：按子命令域（ui/entity/project/tool/gui）与功能块模块化组织，避免单文件膨胀。
- 目标：`ugc_unified.py` 保持稳定入口与兼容层，核心逻辑可复用、易维护。

## 当前状态
- `main.py`：统一入口 `main(argv)`（构建 argparse、挂载子命令、分发 entrypoint）。
- `common.py`：通用工具（参数解析小工具等）。
- 子命令域概览：
  - `tool.py`：统一转发 `ugc_file_tools/commands/<tool>.py`（工具清单/风险单一真源为 `tool_registry.py`；危险写盘需显式 `--dangerous`）。
  - `project.py`：项目存档与 `.gil` 互通（内部复用 `ugc_file_tools/pipelines/project_writeback.py` 与 `gil_to_project_archive.py`；支持 selection-json 选择式写回）。
    - 实体摆放写回：当所选 `instance_id` 在 base `.gil` 中不存在时，会按“新增实例（克隆样本 entry）”策略写入输出；模板类型/样本不足时会 fail-fast 报错，避免产物进游戏不可见。
    - `project import` 额外支持信号占位写回开关：`--signals-emit-reserved-placeholder-signal/--no-signals-emit-reserved-placeholder-signal`。
    - `project import` 支持 `--id-ref-overrides-json`：用于在 `entity_key/component_key` 按名称找不到时手动覆盖占位符 name→ID 映射（导出中心双击缺失行会自动生成并透传）。
    - `--dtype` 默认值指向 `ugc_file_tools/builtin_resources/dtype/dtype.json`（可通过参数覆盖）。
  - `ui*.py`：UI dump/写回/roundtrip/web import 等能力（dump-json 为纯 Python，不依赖额外 DLL）。
  - `entity.py`：实体/装饰物 `.gia` 相关子命令（按需扩展；二维码实体导出已收敛到 `ugc_file_tools.gia_export.qrcode_entity`）。
  - `gui.py`：GUI 子命令入口（`python -m ugc_file_tools gui`，Tkinter）。
- 推荐运行方式（仓库根稳定入口）：`python -X utf8 private_extensions/run_ugc_file_tools.py ...`。

## 注意事项
- 避免在 import 阶段触发重依赖初始化；需要时在具体命令函数内再导入，确保 `--help` 可用。
- fail-fast：不使用 `try/except` 吞错；失败直接抛错，便于定位与保持口径一致。
- 路径定位必须复用 `ugc_file_tools.repo_paths` 的单一真源，避免各子命令各写一套根目录探测逻辑导致口径分裂。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

