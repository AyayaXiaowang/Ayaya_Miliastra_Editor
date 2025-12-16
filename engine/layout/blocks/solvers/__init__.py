"""
块间定位求解器（solvers）

这里存放 BlockPositioningEngine 的各个求解阶段实现（列分配、列X、列内Y堆叠、tight spacing、孤立块放置等）。
目标：
- 按阶段拆分，避免单文件过大
- 每步输入输出结构化，便于做阶段级回归与单元测试
- 保持现有布局逻辑与对外 API 完全不变（BlockPositioningEngine 仍是唯一入口）
"""


