## 目录用途
块间排版（BlockPositioningEngine）的求解阶段集合：列索引、列 X 坐标、列内堆叠、紧凑间距、孤立块放置等纯算法实现。

## 当前状态
- 每个 solver 文件聚焦一个可测试子问题：输入为只读配置/结构（dataclass），输出为纯数据结果或对运行态结构做最小更新。
- `types.py` 定义 `PositioningEngineConfig` / `PositioningRuntimeState` 等共享结构；其余模块按阶段拆分（`column_assignment_solver.py`、`column_x_solver.py`、`column_stack_solver.py`、`orphan_blocks_solver.py`、`tight_spacing_x_solver.py` 等）。

## 注意事项
- 仅依赖 `engine.layout` 的纯逻辑层，禁止引入 UI 或外设 I/O。
- 保持可复现：遍历 `set/dict` 必须稳定排序，避免块坐标漂移。
- 不使用 `try/except` 吞错；错误直接抛出，由上层处理。

