## 目录用途
`engine/graph/semantic/` 负责“语义元数据”的单一写入阶段（GraphSemanticPass）。

这里的“语义元数据”特指 **GraphModel.metadata 中的派生字段**，例如：
- `metadata["signal_bindings"]`
- `metadata["struct_bindings"]`

这些字段必须由本目录内的 Pass 在明确阶段统一生成，其它模块只能读，或写入节点本体的“意图/常量/端口”供 Pass 推导，避免出现多源写入互相覆盖导致的非确定性问题。

## 当前状态
- `GraphSemanticPass` 是唯一允许写入 `signal_bindings/struct_bindings` 的实现。
- Pass 的输出为**覆盖式重建**：每次运行都会重建整张图的 bindings 映射（按节点现状推导），保证幂等与可复现。
- Pass 会在必要时为节点回填“隐藏的稳定 ID 常量”（例如 `__signal_id` / `__struct_id`），用于在“显示名不唯一/被改名”时保持绑定稳定。
- `struct_bindings` 推导时，结构体相关节点的 `结构体名` 常量只允许填写结构体定义中的名字（`STRUCT_PAYLOAD.struct_name`）；不再接受把 `STRUCT_ID` 当作“结构体名”传入。
- Pass **不再**对“自定义变量”相关节点的 `变量名` 常量做旧写法迁移归一；严格要求该常量直接填写稳定 `variable_id`，否则交由校验层报错提示修复。

## 注意事项
- 保持纯逻辑：不得依赖 `app/*`、`plugins/*` 或任何 UI。
- 不使用 `try/except` 吞错；异常直接抛出，由上层处理。
- 本文件不记录修改历史，只描述“目录用途、当前状态、注意事项”的实时概况。


