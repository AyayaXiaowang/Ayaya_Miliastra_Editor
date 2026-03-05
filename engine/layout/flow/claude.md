## 目录用途
事件流程与布局前预处理逻辑：负责分析事件入口、构建流程树，以及在布局前对图模型进行必要的语义预处理。

## 当前状态
- 包含事件流分析与根节点发现、流程树生成以及布局前的模型预处理等模块。
- 流程口/流程边判定统一收敛到 `layout/utils/graph_query_utils`：以 `NodeModel.effective_input_types/effective_output_types` 端口类型快照为真源（名称规则仅作兼容回退），避免多分支/动态端口依赖字符串关键字识别。
- 仅依赖图模型与布局核心上下文，不直接参与具体几何计算与坐标回填。
- 纯数据图的树状展示复用 `layout/utils/data_graph_utils` 的分层结果，避免与核心层重复维护拓扑逻辑。
- 事件根判定通过 `_compute_flow_indegree` 统一统计忽略虚拟引脚的流程入度，减少重复遍历；当模型中不存在显式事件节点时，`find_event_roots` 会优先根据是否存在流程边与带流程端口的节点动态推断起点：若只有孤立的流程控制/执行节点（例如仅有一个带“流程入/是/否”的双分支节点），也会将这些节点视作事件起点参与布局与流程树分析，而不再简单将整图归类为纯数据图。
- `flow_tree_generator` 优先复用模型上 `_layout_context_cache`，否则才初始化新的 `LayoutContext`，并在此基础上构建数据边索引，供流程树与纯数据树共享；递归过程中复用单一 `visited` 集合避免指数级复制。
- `flow_tree_generator` 使用 `FlowTreeRenderContext` 统一封装模型、布局上下文与块关系快照，事件遍历、数据输入渲染与 ASCII 输出共享一份缓存，并在具备块关系快照时保持与布局顺序一致的分支排列。
- 流程树在无块关系快照时的端口排序直接调用 `LayoutContext` 的端口索引缓存，通过通用的 `get_ordered_flow_out_edges` 与块层保持一致。
- `find_event_roots` 无论调用方是否传入上下文，都会复用 `LayoutContext` 的缓存并在其上进行虚拟引脚拆分，避免额外构建独立索引；虚拟引脚集合直接读取上下文内置的 `virtualPinNodeIds`，不再额外遍历全图。
- `generate_flow_tree` 仅初始化一次 `LayoutContext` 并在事件根发现与数据索引之间共享，保持输出与布局一致且成本稳定。
- 当模型上无 `_layout_block_relationships` 快照时，流程树直接回退到端口顺序渲染，不再为了树状展示额外执行完整布局；同时 DFS 会记忆已展开节点，避免在菱形/合流图上指数级重复遍历。
- `_trace_flow_tree` 在所有递归路径上都显式传递 `LayoutContext`，确保多分支端口排序、块关系与数据索引一致，保持 ASCII 结构与布局语义同步。

## 注意事项
- 不应涉及具体坐标或 UI 尺寸常量，这些应由 `layout/internal` 或 `layout/utils` 提供。
- 避免在此处引入与块级几何实现强耦合的逻辑，保证事件流分析与预处理可独立演化。
- 发现与纯数据组件或公共算法重叠的逻辑时，应优先将实现下沉至 `layout/utils`。
- 字符串展示/调试输出需兼容 Python 3.10：f-string 的 `{...}` 表达式内不要出现反斜杠转义（如 `\"`），应先在普通表达式中计算再拼接。


