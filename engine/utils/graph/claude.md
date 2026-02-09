# graph 子包

## 目录用途
存放图结构与节点图相关的纯逻辑工具模块，包括：
- 通用图结构算法（拓扑排序、事件分组等）
- 节点图数据处理与端口/常量判断工具
- 节点定义与实现库指纹计算逻辑

## 关键文件
- `graph_algorithms.py`：图结构算法（事件分组、拓扑排序、事件流收集等），复用 `_topological_order_from_edges` 统一实现 Kahn 排序，并对外暴露 `collect_event_flow_nodes` 供布局/flow 模块直接引用，兼容 `GraphModel` 和通用 `nodes/edges` 结构。
- `graph_utils.py`：节点图数据格式归一化（含 `_normalize_graph_collection`）、端口名称提取、流程口判定、常量判定、节点信息提取等。
- `node_defs_fingerprint.py`：节点定义/实现库指纹计算工具，为节点库缓存与节点图持久化缓存（`PersistentGraphCacheManager`）提供统一失效指纹；内置进程内分段缓存（工具链段/复合节点库段）并提供 `invalidate_*` 失效入口，避免高频调用导致的全目录扫描开销。

## 注意事项
- 仅依赖 `engine.graph` / `engine.nodes` 等引擎层模型与标准库，不依赖 UI、app、plugins。
- 流程边/流程端口判定统一通过 `graph_utils.is_flow_port_name()`，避免各处重复实现。
- 公用工具函数（如 `_normalize_graph_collection`、`_topological_order_from_edges`）需保持纯函数语义，扩展新功能时优先复用，避免再次出现重复实现。
- 算法应保持可预测、可测试，不在此目录引入任何 I/O 或日志副作用。
- `node_defs_fingerprint` 仅依赖文件元信息（相对路径、mtime、size）计算目录签名，不读取文件内容；签名覆盖实现库/引擎核心目录与资源库复合节点库（共享 + 当前项目存档作用域）；指纹对“修改了非最新文件但 max mtime 未变”的情况同样敏感，保证节点库/图缓存能可靠失效；并支持“外置工作区”场景：当工作区缺少 `plugins/engine` 源码目录时，会回退到工具链根目录计算签名；冻结运行（PyInstaller）时还会将 exe 的 mtime/size 纳入指纹段，确保升级后缓存可靠失效；为避免在节点图加载/缓存校验中反复扫描目录，指纹计算提供进程内缓存并允许上层在“资源库刷新/作用域切换”时显式失效。

---
注意：本文件不记录修改历史，仅描述“目录用途、当前状态、注意事项”。请在结构调整后保持描述同步。

