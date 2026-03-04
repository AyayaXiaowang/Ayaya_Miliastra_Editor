## 目录用途
- 存放“存档补丁/写回（非 UI、非节点图段）”相关工具：以 `.gil` 二进制为目标，通过可解释的结构定位并写回数据。
- 本目录聚焦“玩法/运行态数据”类写回：例如玩家模板、生效玩家集合、自定义变量等。

## 当前状态
- 计划提供玩家模板写回能力：
  - 新建玩家模板
  - 修改玩家模板生效玩家（8 玩家互斥约束）
  - 给玩家模板写入自定义变量定义（变量名/类型/默认值）
- 已提供基础模块：
  - `gil_codec.py`：`.gil` 容器读写 + protobuf-like 数值键 message 编解码（纯 Python）。
  - `gil_node_graph_injector.py`：`.gia` → `.gil` 的 **NodeGraph 注入**（文件级 patch，优先定位 10.1.1 blob，必要时回退全量扫描，并更新祖先 length；默认启用“非空且 name 非 `_GSTS*` 不覆盖”的安全检查；注入前会将 incoming NodeGraph 的 id/type 对齐到目标图，避免 ID 不一致导致无法注入）。
  - `player_templates.py`：玩家模板段结构定位（root4/root5）、生效玩家 packed bytes 写回、自定义变量定义写回。
  - `player_template_bootstrap.py`：空存档自举 section 外壳 + 从 seed 克隆创建“普通/角色编辑”两类条目。
  - `player_templates_tool.py`：命令行入口（dump/set-players/add-var/copy-vars/apply-vars/create）。

## 注意事项
- 不使用 try/except：结构不符直接抛错，避免 silent 生成坏存档。
- 所有写回必须建立在“字段语义可解释”的抽象之上：先定位字段路径与编码规则，再生成/修改 message。
- `player_templates_tool.py apply-vars/copy-vars` 采用 wire-level 局部补丁：只修改玩家模板变量定义字段，避免全量 decode/encode 造成 payload drift。
- 输出 `.gil` 统一写入 `private_extensions/ugc_file_tools/out/`。
- `.gia` 侧的 VarBase/decoded_field_map 语义提取统一使用 `ugc_file_tools.gia.varbase_semantics`（`gia_protobuf_like` 仅为兼容薄 wrapper）。