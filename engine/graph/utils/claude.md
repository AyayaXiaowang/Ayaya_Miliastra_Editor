# engine/graph/utils

## 目录用途

Graph Code 解析/校验的公共工具：元数据与图变量提取、AST 常量提取、注释提取与关联、复合实例别名扫描，以及语法糖归一化改写等，为解析/IR/校验提供统一复用点。

## 当前状态

- `metadata_extractor.py`：解析 docstring 的基础元数据，并读取代码级 `GRAPH_VARIABLES`（图变量唯一真源）。
- `ast_utils.py`：从 AST 节点提取静态常量值，供 IR/解析/校验复用；支持解析“模块常量别名链”（例如 `POS_X = ZERO_FLOAT`）以便在节点入参处写 `X分量=POS_X` 仍能落为端口常量，避免结构校验误报“缺少数据来源”。
- `comment_extractor.py`：注释提取与基于行号的关联辅助。
- `composite_instance_utils.py`：扫描复合节点实例别名/类名对，供解析与校验一致使用。
- **语法糖归一化**：`syntax_sugar_rewriter.py`（以及 list/dict literal rewriter 等拆分实现）将不直接支持的 Python 写法改写为等价的节点调用；开关与上限集中在 `graph_code_rewrite_config.py`，供解析入口与校验规则复用。
  - 容器语法糖（字典/列表下标、len、in 等）支持引用**模块顶层**已注解的字典/列表常量（例如 `常量字典[key]`），避免仅因常量定义在方法外就被误判为列表下标并触发端口类型错误。
  - 模块常量上下文为**栈式（push/pop）**：支持在解析节点图过程中嵌套加载信号/结构体/关卡变量等代码级 schema 时自动恢复外层上下文，避免 strict 模式误报“缺少数据来源”。
- 三维向量常量写法（调用入参位置）：当端口期望类型为 `三维向量` 时，允许写 `(x, y, z)`（括号 tuple）；该写法会被识别为端口常量写入 `input_constants`，不会额外生成节点，确保预览与写回语义稳定。

## 注意事项

- 保持纯函数与确定性，不使用 `try/except` 吞错；读取源码统一使用 `utf-8-sig` 兼容 BOM。
- 图变量只解析代码级 `GRAPH_VARIABLES`，不要依赖 docstring 内的“节点图变量”段落。
- `GRAPH_VARIABLES` 的字段允许引用可静态解析的模块级常量（例如 `name=GRAPH_VAR_NAME`），以减少字符串拼写错误并提升可维护性。
- 语法糖改写规则必须与校验口径一致，避免出现“解析能过/校验不过”或反之的漂移。
