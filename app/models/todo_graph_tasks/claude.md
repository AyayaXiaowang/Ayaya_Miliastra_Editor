## 目录用途
- 将“节点图任务生成”（GraphModel → 事件流级 Todo 步骤）拆分为可维护的小模块：边索引、事件流遍历、节点创建/连线发射、动态端口/类型/参数步骤规划等。
- 仅包含纯模型/算法代码：不依赖 PyQt，不依赖自动化执行器；由上层 `TodoGraphTaskGenerator/GraphTaskCoordinator` 负责装配与调用。

## 当前状态
- `edge_lookup.py`：从 `GraphModel` 构建 `GraphEdgeLookup`（流程边/数据边、邻接与入度索引），供遍历与重排复用。
- `event_flow.py`：事件流任务 orchestrator：收集事件起点、按模式组织步骤生成，并在必要时调用布局服务获得稳定坐标。
- `event_flow_traversal.py`：事件流遍历策略实现（人类模式 / AI 模式），只通过 emitters 输出结果。
- `event_flow_emitters.py`：集中负责写入 TodoItem（创建节点/连线/数据节点链等），并在合适时机追加动态端口、类型与参数步骤。
- `dynamic_port_steps.py`：节点级“动态端口/类型设置/参数配置”步骤规划（与节点声明/连线情况联动），并对信号/结构体等语义节点生成独立的绑定步骤。
- `node_predicates.py`：节点角色判定工具（事件/流程等），避免遍历中散落硬编码。
- `composite.py`：复合节点相关的 Todo 生成与展开（若存在复合节点任务链路）。

## 注意事项
- **依赖边界**：只依赖 `engine.*` 与 `app.models` 内部工具；禁止反向依赖 `app.ui` 或 `app.automation`。
- **模型变更**：若生成阶段对 `GraphModel` 做了结构性修改（例如插入副本/重写连线），必须重建 `GraphEdgeLookup` 再继续遍历/重排。
- **步骤一致性**：所有子步骤必须沿用上层传入的 `task_type` 等上下文字段，避免 UI 统计/过滤口径分裂。
- **可读性优先**：复杂规则尽量收敛到 planner/emitters 内部的独立函数，避免单文件继续膨胀；本目录文档仅维护用途/现状/注意事项，不记录历史。
