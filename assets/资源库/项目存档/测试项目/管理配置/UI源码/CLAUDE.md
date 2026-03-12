## 目录用途

测试/回归用的 UI HTML 夹具与 Workbench bundle 落点。

## 文件清单
- __hook_tests__/：Cursor hook 夹具
- __workbench_out__/：Workbench bundle 输出
- ui_smoke_data_ui.html：data-ui 扫描夹具
- CLAUDE.md：本目录说明

## 注意事项
- [全局] 本目录仅用于测试/回归，不作为业务 UI 资源维护入口。
- [全局] `__hook_tests__/` 内包含“故意错/故意对”的最小样例，用于验证 afterFileEdit UI 校验。
- [全局] 第七关业务 UI 真源位于 `assets/资源库/项目存档/示例项目_第七关/管理配置/UI源码/`。