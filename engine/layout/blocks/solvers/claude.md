## 目录用途
块间排版的“求解器”子模块：承载列索引、列 X、列内堆叠、紧凑间距与孤立块放置等纯算法实现，供 `BlockPositioningEngine` 组合调用。

## 当前状态
- 每个 solver 文件聚焦一个可测试的子问题（输入为 dataclass/只读结构，输出为纯数据结果或对 runtime 结构做最小更新）。
- `types.py` 提供 `PositioningEngineConfig/PositioningRuntimeState` 等只读配置与运行期状态结构，供各 solver 共享。
- `tight_spacing_x_solver.compute_min_left_from_port_gap()` 入口约束同时考虑 flow/data 入边（依赖 `config.block_map` 可映射到 data 节点所属块），用于在开启紧凑排版时避免 data 连线右→左折返。

## 注意事项
- 仅依赖 `engine.layout` 的纯逻辑层（如 `engine.layout.internal.*`、`engine.layout.blocks.*`、`engine.layout.utils.*`），禁止引入 UI 或外设 I/O。
- 保持可复现：集合遍历必须稳定排序，避免因为迭代顺序差异导致块坐标轻微漂移。
- 不使用 `try/except` 吞错；错误直接抛出，由上层调用方处理。

# 块间排版求解器目录（engine/layout/blocks/solvers）

## 目录用途
存放块间排版（BlockPositioningEngine）中“可独立拆分的求解阶段”实现：列索引、列 X 坐标、列内堆叠、孤立块放置、重叠桶索引、紧凑间距等。该目录仅承载纯逻辑函数与轻量数据结构，供 `engine.layout.blocks.block_positioning_engine` 组合调用。

## 当前状态
- 统一从 `engine.layout.internal` 导入 `LayoutBlock`、布局常量与 `LayoutContext`（通过相对导入 `...internal.*`），不再引用不存在的 `engine.layout.core` 包路径。
- 求解函数保持“逻辑搬迁”语义：排序、过滤与副作用应与旧实现一致，避免因重构引入布局漂移。

## 注意事项
- 严禁依赖 UI、I/O、`app/*` 或资源库；仅通过参数注入获取上下文与配置。
- 遍历 `set/dict` 时必须使用稳定排序（例如按 `LayoutBlock.order_index` 或 `config.stable_sort_key`），确保布局可复现。
- 若新增求解阶段，应优先复用本目录已有桶索引/最长路径等工具，避免重复实现。


