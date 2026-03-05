# __workbench_out__

## 目录用途

- 存放 UI Workbench 导出的 `*.ui_bundle.json`（页面扁平化/控件抽取后的结构化产物），供“项目存档 → 写回 `.gil`”的 UI 写回阶段直接使用。

## 当前状态

- 本目录的 `*.ui_bundle.json` 与同级 `UI源码/*.html` 一一对应，写回端以 **bundle 文件名** 作为布局名消歧。
- 写回端不会从 HTML 自动重生成：若只修改 `.html` 而未更新对应 `.ui_bundle.json`，写回仍会使用旧 bundle。

## 注意事项

- 建议把本目录视为“构建产物”：优先通过导出工具从 `.html` 重新生成（`python -X utf8 -m ugc_file_tools tool export_ui_workbench_bundles_from_html --project-root <项目存档根>`），而不是手工编辑 JSON（依赖 Playwright/Chromium）。

---

注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。
