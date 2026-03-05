<!-- markdownlint-disable MD022 MD032 MD041 MD012 -->

# UI源码（测试项目）

## 目录用途

`测试项目/管理配置/UI源码/`：测试/回归用的 UI HTML 源码与 Workbench 导出 bundle（`__workbench_out__/*.ui_bundle.json`）落点，用于 UI 静态约束校验与 Web UI 导入写回链路回归。

## 当前状态

- 提供最小可复现的第七关三页 UI 示例：
  - `关卡大厅-选关界面.html`
  - `第七关-游戏中.html`
  - `第七关-结算.html`
- 对应的 Workbench 导出产物位于 `__workbench_out__/`，用于批量导入/布局树不变量等回归用例。

## 注意事项

- 本目录仅用于测试/诊断回归，不作为业务 UI 资源维护入口。
- 修改后建议跑：
  - `python -X utf8 -m pytest tests/ui/html`
  - `python -X utf8 -m pytest tests/ugc_file_tools/test_web_ui_import_batch_layout_tree_invariants.py`
