## 目录用途
V2 节点解析管线的分层实现与对外检索封装。包含：
- discovery：实现文件发现（仅返回路径，不导入）
- extractor_ast：AST 提取 `@node_spec(...)` 原始项
- normalizer：字段与类别标准化（统一“...节点”后缀、生成标准键）
- validator：阻断式校验（类别/键/作用域/端口类型/别名冲突）
- merger：合并策略（server 优先；不兼容端口产生 `#{scope}` 变体）
- indexer：构建 `by_key` 与 `alias_to_key` 索引
- lookup：基于索引的查询工具函数
- node_library：对索引的面向对象封装（便于注入与替换）

## 当前状态
- 已与实现加载流程对接，且作为唯一实现启用：走“只解析不导入”的快速路径（discovery → extractor_ast → normalizer → validator → merger → indexer → lookup）。
- 查找能力既可通过 `lookup` 函数使用，也可通过 `NodeLibrary` 封装使用。
- V1 回退路径已移除（以 V2 为唯一实现）。
- 已引入轻量类型化数据结构（`types.py`）：`ExtractedSpec`/`NormalizedSpec`，便于单测与类型提示（向下兼容 dict 结构）。
- indexer 会为节点显示名自动注入“可调用别名”（如 `name.replace("/", "")` 与 `make_valid_identifier(name)`），用于支持 Graph Code/导出代码在遇到 `/`、`：`、括号等字符时仍能以合法 Python 标识符形式调用节点。
- 复合节点子管线（`composite_runner.py`：discovery/parse/validate/expand/augment）已直接使用 `CompositeCodeParser` 解析复合节点文件（payload / 类格式）并构建 `NodeDef`，不再委托 `CompositeNodeManager`；管理器仅用于编辑/运行期的库管理与懒加载。解析器会注入 `workspace_path` 并在解析期派生布局上下文，避免在节点库构建中反向触发 `NodeRegistry`。旧函数式复合节点格式不再支持。
- 复合节点文件发现规则由 `engine.nodes.composite_file_policy` 统一维护：仅解析 `assets/资源库/复合节点库/**/composite_*.py`，避免不同入口看到的复合集合不一致。
- 目录内不再保留 `composite_validator.py` 这类容易被误用的旧占位入口，复合节点校验以 `composite_validate.py` 为唯一通路。
- 管线会解析并透传 `@node_spec` 的 `input_generic_constraints`/`output_generic_constraints` 与 `input_enum_options`/`output_enum_options` 等元数据字段，在 `NodeDef` 中统一保留泛型约束与枚举候选项，供 UI、自动化与验证层复用。

## 注意事项
- 保持“只解析不导入”，避免导入副作用；全程使用 UTF-8 编码。
- 类别统一为内部“带‘节点’后缀”的标准键 `类别/名称`。
- 校验采用阻断式抛错；错误信息包含类别、键、作用域与端口信息。
- Python 文件的 `from __future__ import annotations` 必须放在文件首部（紧随可选的模块文档字符串之后）。
 - 类型名标准化：不再做“旧称→新称”的归一化映射。管线会在校验阶段禁止出现 `通用`/`Any/any/ANY`，要求直接使用“泛型”。`dynamic_port_type` 同样遵循该限制。

### alias / 作用域变体约定
- 合并阶段在端口不兼容时会生成 `#{scope}` 变体键（如 `执行节点/XXX#server`）。
- 索引阶段构建 `alias_to_key` 时**不允许**不带 `#scope` 的别名指向 scoped 变体：
  - `类别/名称` 与 `类别/别名` 只映射到不带 `#` 的基键；
  - 只有显式写成 `名称#scope`/`别名#scope` 才会命中 `类别/名称#scope` 变体键。

### scopes 推断约定（省人力）
- 若实现侧 `@node_spec(..., scopes=[...])` 未显式填写 scopes，则 normalizer 会尝试推断：
  - 优先从实现文件路径推断：`plugins/nodes/server/**` → `["server"]`，`plugins/nodes/client/**` → `["client"]`
- `doc_reference` 不参与作用域推断：文档路径/目录结构调整不应导致节点语义变化。
- `plugins/nodes/shared/**` 不参与实现扫描；shared 仅用于放置 helper，不用于放置 `@node_spec` 定义。

### 复合节点解析产物说明
- 输入/输出端口名称来自虚拟引脚；流程口类型统一为“流程”，其余使用引脚声明类型。
- 类别自动判断：有输入流程→“执行节点”；仅有输出流程→“事件节点”；否则“查询节点”。
- 所有复合节点 `NodeDef` 均带 `is_composite=True` 与 `composite_id`。

# 设计要点

- 任何阶段不得隐式导入实现模块，避免副作用。
- 校验阶段采用阻断式错误上报（不包裹 try/except）。
- 命名与键规范统一为内部标准键 `类别/名称`，变体通过 `#{scope}` 后缀表达。
- 校验器的类别/作用域合法值统一来自常量定义模块，避免分散维护。
- 实现发现路径：扫描 `plugins/nodes/**.py`（排除 `__init__.py` 与 `shared/` 以及静态注册表 `registry.py`）。


