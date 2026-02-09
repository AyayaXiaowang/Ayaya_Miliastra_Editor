## 目录用途
- `editor_exec_steps` 的“通用编排管线”拆分目录：将**步骤计划表 / 识别预热 / 视口同步 / 缓存失效 / 回放记录**等横切关注点从大文件中抽离。

## 当前状态
- `step_plans.py`：集中定义 graph_* 步骤的计划表（step_type → plan）与轻量 handler 绑定（handler 仅做业务委托）。
- `step_plans.py` 已覆盖信号/结构体绑定步骤：`graph_bind_signal` / `graph_bind_struct` 均在此处绑定到 `app.automation.config.*_config.execute_bind_*`，保持“编排层只做委托、业务在 config/editor_* 模块内”的分层约束。
- 连线链复用：`graph_connect` / `graph_connect_merged` 均会通过执行器的 connect_chain_context 复用首帧截图/节点检测/端口快照；仅在发生视口调度（同屏对齐/拖拽）或步骤失败时清理并触发重新截图，避免多条边重复 OCR/模板匹配。
- 快速链连接优化：在 fast_chain_mode 下，连接步骤成功后不会强制失效场景快照（scene snapshot），避免执行线程的可见性/守卫检查对每一步重复触发整屏识别造成卡顿。
- `recognition_prewarm.py`：连线前的识别预热（基于 executor 的 view token 判断是否需要刷新）。
- `viewport_sync.py`：单步模式下的“可见节点坐标同步”（视口 token 变化才触发）。
- `cache_policy.py`：步骤前后缓存失效策略（连线链上下文、视觉缓存、场景快照）。
- `replay_recorder.py`：关键步骤输入输出落盘（JSONL + 可选截图），用于回归定位与离线复现。

## 注意事项
- 本目录只做编排/策略/记录，不直接实现节点创建/连线/配置等业务；业务逻辑在 `editor_nodes.py` / `editor_connect.py` / `config/*` 中。
- 不在此层新增吞异常的 `try/except`；落盘失败应直接抛错暴露环境问题。
- 所有落盘路径统一从运行时服务派生：优先使用 `app.runtime.services.json_cache_service.JsonCacheService`（遵循 `settings.RUNTIME_CACHE_ROOT`），默认在 `app/runtime/cache` 下。

---
注意：本文件不记录任何修改历史。请始终保持对「目录用途、当前状态、注意事项」的实时描述。


