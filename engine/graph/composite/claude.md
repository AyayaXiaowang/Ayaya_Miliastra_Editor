## 目录用途
复合节点（Composite）相关的解析与格式转换工具：将类格式复合节点解析为统一 IR，并构建/维护虚拟引脚（流程入/出、数据入/出）与内部端口映射。

## 当前状态
- `source_format.py`：复合节点源码格式（payload / `@composite_class`）的单一事实来源，供 loader/parser/validate 复用，避免支持范围漂移。
- `pin_api.py`：维护 `流程入/流程出/数据入/数据出` 等声明式辅助函数（运行期 no-op），供 Graph Code 引用。
- `pin_marker_collector.py`：扫描 AST 提取引脚声明（pin marker + 方法签名），用于自动补全虚拟引脚。
- `class_format_parser.py`：解析类格式并合并多方法子图；发生节点/连线冲突时会重命名并同步更新虚拟引脚映射；合并时会保留 IR 产出的 `GraphModel.metadata["port_type_overrides"]`（避免预声明数据出变量的局部变量建模在结构校验阶段出现“端口类型仍为泛型”）；合并完成后运行 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成语义绑定；并会从 `__init__` 提取 `self.xxx = <复合类>(...)` 的实例声明，注入到 IR 环境以支持“复合内调用复合”建模。
- `param_usage_tracker.py`：统计参数读写/别名，用于更稳定的虚拟引脚映射（必要时基于源码行号范围定位对应节点）。

## 注意事项
- 保持纯逻辑实现，不访问磁盘/网络/UI。
- 避免与生成器/导出器形成循环依赖；必要信息通过参数传入。
- 新增语法/引脚推断规则时，需要同步生成、解析与校验链路，保证口径一致。

