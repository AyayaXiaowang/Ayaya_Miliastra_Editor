## 目录用途
节点系统核心：节点规格（`NodeSpec`/`NodeDef`）、端口类型系统、节点库构建管线（V2 AST pipeline）、节点注册表（`NodeRegistry`），以及复合节点（Composite Node）的解析与管理。

## 当前状态
- **实现节点发现**：实现侧节点位于 `plugins/nodes/**`，由 `engine.nodes.pipeline` 通过 AST 扫描 `@node_spec` 构建节点定义库（只解析不导入）。
- **节点库入口**：运行期通过 `engine.get_node_registry(workspace_root).get_library()` 获取节点库；节点定位使用 `NodeDef.canonical_key`（`node_def_key.py` 提供统一解析/反查工具），调用侧禁止自行拼接字符串当主键。
- **复合节点**：文件筛选规则在 `composite_file_policy.py`；解析/扩展在 `pipeline/composite_*`；运行期管理器 `CompositeNodeManager` 负责复合节点的 CRUD/落盘/懒加载子图。
  - 子图解析（load_subgraph=True）会使用“基础节点库 + 当前作用域内的复合节点 NodeDef”构建解析上下文，以支持复合节点内部调用复合节点的建模（嵌套复合）。
- **虚拟引脚类型收敛**：`CompositeVirtualPinManager.add_virtual_pin_mapping` 在绑定内部端口时会把“占位型 pin_type”（如 `字典/列表/泛型列表/泛型字典/枚举`）收敛为内部端口的具体 `port_type`，确保复合节点对外暴露的类型是确定且可导出的。
- **端口系统**：`port_type_system.py` / `port_name_rules.py` / `port_index_mapper.py` 管理端口类型推断与连线判定，类型语义单一真源以 `engine.type_registry` 为准。
- **迁移与桩**：`migrations/` 存放节点改名/端口改名迁移规则数据；`stubgen.py` 可导出 `.pyi` 供 Graph Code 编写时补全。

## 注意事项
- 避免循环依赖：复合节点加载/解析路径禁止在节点库构建过程中反向调用 `get_node_registry().get_library()`。
- 复合节点路径必须做安全归一化：只允许相对路径，禁止绝对路径/盘符/UNC/`..` 注入；字符串层分隔符归一化统一复用 `engine.utils.path_utils.normalize_slash`。
- 不写防御式“判空/缺数据兜底”；缺数据应直接抛错暴露问题。
- 文档与注释统一称工作区根为 `workspace_root`。

