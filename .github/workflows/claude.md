# GitHub Actions 工作流目录（.github/workflows）

## 目录用途
存放 CI 工作流定义，用于在 PR/Push 时强制执行仓库护栏与回归测试，确保“节点库（SoT）变更”必须显式可见并可机器判定 breaking。

## 当前状态
- `ci.yml`：Windows（PowerShell）流水线，按顺序执行：
  - 自动化静态扫描护栏：`app.automation._static_checks.*`
  - UI 静态护栏：`app.ui._static_checks.check_large_files --fail --max-lines 1500`
  - 节点图/复合节点全量校验（CI gate：仅 error 阻断，warning 仅记录到 JSON 报告）：`app.cli.graph_tools validate-graphs --all --json` + `tools/validate_graphs_ci_gate.py`
  - 单测：`pytest`

## 注意事项
- PowerShell 不使用 `&&`；命令以逐行方式执行。
- 如需恢复“节点库 manifest 快照卡点 / 派生文档一致性检查”，请先将对应工具链模块纳入仓库版本管理，再在 CI 中启用（避免引用不存在的 `tools.*` 模块）。

