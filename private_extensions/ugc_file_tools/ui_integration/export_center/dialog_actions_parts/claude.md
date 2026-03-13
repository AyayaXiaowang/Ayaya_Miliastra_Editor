## 目录用途
- 承载 `export_center/dialog_actions.py` 的**拆分实现**：将“预检/冲突检查/worker 编排/成功提示”等大段动作逻辑拆成可复用小模块，降低单文件体量与回归风险。

## 当前状态
- `export_action.py`：导出中心“开始导出/开始修复”入口实现（薄编排），保持对外 API 不变，并将本次执行的 plan/预检/已选资源快照写入 runtime state 供失败复现信息展示。
- `identify_action.py`：导出中心“回填识别”入口实现（薄编排），保持对外 API 不变。
- `export_plan_utils.py`：导出 plan 校验 + 状态落盘（last paths）+ IDRef 手动覆盖注入。
- `export_prechecks.py`：导出前预检过滤（例如 templates_index.json）与“无事可做”提示文本生成。
- `base_gil_conflicts.py`：base `.gil` 冲突扫描报告的惰性获取与缓存（子进程隔离 + 进度转发）。
- `gil_ui_layout_conflicts.py`：UI Workbench bundle 过期/缺失检查与“布局同名冲突”策略收集。
- `conflict_utils.py`：冲突策略的通用命名分配与 base report 映射抽取。
- `gil_template_conflicts.py`：模板 JSON 的预检过滤与同名冲突策略收集。
- `gil_instance_conflicts.py`：实体 JSON 的预检过滤与同名冲突策略收集。
- `gil_template_instance_conflicts.py`：兼容薄转发层（保持导入路径稳定）。
- `gil_node_graph_conflicts.py`：节点图 Graph Code 的预检过滤与同名冲突策略收集。
- `export_worker.py`：QThread worker 启动、busy/progress 编排与成功/失败回调桥接。
- `export_success_dialogs.py`：导出完成弹窗文本构建与近期产物记录（recent artifacts）更新。

## 注意事项
- 避免在模块顶层导入 PyQt6；UI 相关依赖在函数内按需导入。
- 保持行为一致：不引入新的静默降级/兜底路径，失败需明确提示与可追溯。
