# graph_code/utils 模块

## 目录用途
提供节点图代码解析的公共工具函数，统一处理元数据提取、AST操作、注释提取等通用逻辑。

## 模块职责

### metadata_extractor.py
- 从 docstring 提取节点图基础元数据（graph_id、graph_name、graph_type、description 等），图变量一律忽略 docstring，仅在代码中声明。
- 解析代码级图变量声明：扫描模块顶层的 `GRAPH_VARIABLES: list[GraphVariableConfig]`，提取变量名、类型、默认值、是否对外暴露，以及字典类型变量的 `dict_key_type` / `dict_value_type`，统一写入 `GraphMetadata.graph_variables`，作为图变量的唯一事实来源。
  - 默认值提取支持一元 +/- 数值常量（例如 `-1` / `-1.0`），避免负数字面量在 AST 中被误判为不可提取。
- 解析动态端口信息（多分支节点的动态输出端口）。
- 统一元数据结构定义（GraphMetadata dataclass）。

### ast_utils.py
- 常量值提取：`extract_constant_value()` - 从 AST 节点提取静态常量值，统一供 IR 与复合节点等场景复用
  - 支持标准常量（int/float/str/bool/None）（项目要求 Python 3.10+，不再保留旧版 AST 节点兼容分支）
  - 支持一元 +/- 数值常量（例如 `-1` / `+1.0`），用于多分支 case 值与 range 参数等场景
  - 支持列表/元组等容器字面量（递归提取元素）
  - 对 `self.owner_entity` 返回字符串表达式供上层按“图所属实体”语义处理；
  - 对以下划线开头的实例字段默认视为运行期状态（不可静态提取），但若解析器已将节点图类体内的“类常量”以 key=`"self._xxx"` 注入模块常量上下文，则 `self._xxx` 可被静态提取（用于定时器名称、变量名等标识性参数回填）；
  - 其余公开字段返回 `"self.<字段名>"` 形式交由上层使用
- 格式检测：`is_class_structure_format()` - 判断代码是否为类结构格式（事件方法）
- 旧函数式复合节点格式已移除，不再提供“按顶层函数签名识别复合节点”的工具函数，避免支持口径漂移。
- AST通用工具：简化AST遍历与模式匹配

### comment_extractor.py
- 注释提取：`extract_comments()` - 使用tokenize提取代码中的所有注释
- 注释关联：`associate_comments_to_nodes()` - 将注释与节点关联（块注释、行尾注释、composite_id）
- 事件流注释提取：提取 "===事件流N===" 格式的注释
- 关联策略优先使用节点 `source_lineno` 精确匹配，缺失行号时再回退按创建顺序处理，并在写入事件流注释前自动扩容列表

### composite_instance_utils.py
- `iter_composite_instance_pairs()`：扫描 `self.xxx = ClassName(...)`，为解析和校验提供一致的实例别名/类名对。
- `collect_composite_instance_aliases()`：遍历整个模块，收集所有复合节点实例别名集合，供语法规则复用。

## 设计原则
1. **纯函数设计**：所有工具函数无副作用，易于测试
2. **类型安全**：完整的类型标注，使用dataclass定义结构
3. **错误透明**：不使用try-catch，错误直接抛出
4. **单一职责**：每个函数专注一项具体任务

## 当前状态
已完成基础工具模块的提取和整合，消除了原本散落在GraphCodeParser和CompositeCodeParser中的重复代码。

## 注意事项
- 工具函数不依赖具体的解析器实现
- AST工具函数需要处理Python 3.10+的match/case语法
- 图变量只解析代码级 `GRAPH_VARIABLES`，docstring 中的“节点图变量”段不再生效
- 常量提取需要正确处理 NOT_EXTRACTABLE 哨兵值，IR 层与复合节点解析应统一复用本模块的实现，避免在下游重复定义 `_NotExtractable` 或 `extract_constant_value`
- 注释关联不应覆盖节点已存在的有效源码行号：若 `source_lineno` 已为正数，则只关联注释文本，不重写行号。

---
注意：本文件不记录修改历史。始终保持对"目录用途、当前状态、注意事项"的实时描述。

