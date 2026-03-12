## 目录用途
块间排版（BlockPositioningEngine）的求解阶段集合：列索引、列 X 坐标、列内堆叠、紧凑间距、孤立块放置等纯算法实现。

## 当前状态
- 每个 solver 文件聚焦一个可测试子问题：输入为只读配置/结构（dataclass），输出为纯数据结果或对运行态结构做最小更新。
- `types.py` 定义 `PositioningEngineConfig` / `PositioningRuntimeState` 等共享结构；其余模块按阶段拆分（`column_assignment_solver.py`、`column_x_solver.py`、`column_stack_solver.py`、`orphan_blocks_solver.py`、`tight_spacing_x_solver.py` 等）。
- `column_stack_solver.py` 在列内堆叠阶段执行多轮 Y 轴松弛，并在收敛后做“范围夹紧（clamp）”投影以满足用户的居中观感与紧凑性：居中口径以**块间连线端口的Y坐标（port anchors）**为准，而不是块矩形中心点；对父块的（exclusive）子块分叉，父块的出边端口Y均值需落在子块入边端口Y范围 `[min, max]` 内；仅当越界时才做最小的向下平移修正（父块在上则下移父块；父块在下则下移子块），避免为了追求严格均值把列间距拉大。

## 注意事项
- 仅依赖 `engine.layout` 的纯逻辑层，禁止引入 UI 或外设 I/O。
- 保持可复现：遍历 `set/dict` 必须稳定排序，避免块坐标漂移。
- 不使用 `try/except` 吞错；错误直接抛出，由上层处理。

