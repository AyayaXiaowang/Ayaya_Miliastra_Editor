## 目录用途
Todo 生成流水线的横切能力收敛层：为 `todo_generator.py` 与模型层其他模块提供可组合的图任务编排与调度小服务（无 PyQt 依赖）。

## 当前状态
- `coordinator.py` 包装 `TodoGraphTaskGenerator`，集中管理节点图根任务创建、图名解析与图任务展开；支持去重 `graph_ids`，并可透传 `progress_callback(stage, completed, total)` 供 UI 在超大图懒加载时展示进度。
- `step_mode.py` 读取 `settings.TODO_GRAPH_STEP_MODE` 并提供语义化判定/描述，避免各模块重复硬编码模式字符串。

## 注意事项
- 保持纯逻辑与无 PyQt 依赖；不要在导入阶段访问磁盘/启动线程。
- 新增流水线能力时优先复用 coordinator/step_mode 的单一真源，避免在 UI 或其它模型模块分叉实现。

