# tools/ 目录

## 目录用途
离线数据生成与构建辅助脚本，不随主程序启动，需单独执行。

## 当前状态

### fix_level_variable_owner.py
- **功能**：一次性迁移 `管理配置/关卡变量/**.py` 变量文件的 payload contract：补齐顶层 `owner(level|player|data)`，并移除 `metadata.auto_owner`（仅支持 dict literal / `LevelVariableDefinition(...)` 的静态可解析写法；不可解析直接 fail-fast）。
- **运行**：
  - 仅检查（不写盘）：`python -X utf8 -m tools.fix_level_variable_owner --package-id <id>`
  - 写回：`python -X utf8 -m tools.fix_level_variable_owner --package-id <id> --apply`
  - 只处理某些文件：`python -X utf8 -m tools.fix_level_variable_owner --file <relative.py> [--file <relative2.py>] ...`
  - 当条目缺失 owner 且无 `metadata.auto_owner` 时需显式指定：`--default-owner level|player|data`（建议搭配 `--file` 精准迁移）

### migrate_custom_vars_to_registry.py
- **功能**：将项目存档 `管理配置/关卡变量/自定义变量/*.py` 的散落变量声明迁移到 `自定义变量注册表.py`（单文件真源），并更新 JSON 中对旧 `VARIABLE_FILE_ID` 的引用为注册表派生的稳定 `auto_custom_vars__{player|level}__<package_id>`，最后删除散落 `.py` 文件。
- **运行**：
  - 预演（不写盘）：`python -X utf8 -m tools.migrate_custom_vars_to_registry --package-id <id>`
  - 写回：`python -X utf8 -m tools.migrate_custom_vars_to_registry --package-id <id> --apply`
- **约束**：仅支持“可静态提取”的变量文件写法（dict literal / `LevelVariableDefinition(...)` 常量列表）；不可静态提取会 fail-fast。

### migrate_registry_owner_entity_ref.py
- **功能**：一次性迁移 `自定义变量注册表.py` 的声明条目：移除 `per_player/ui_visible/frontend_read/data_store_key` 等已收敛字段，并将第三方变量从 `owner="data"+data_store_key="<k>"` 迁移为 `owner="data:<k>"`；同时丢弃非白名单的 `metadata`（仅保留 `sources`）。
- **运行**：
  - 预演（不写盘）：`python -X utf8 -m tools.migrate_registry_owner_entity_ref`
  - 写回：`python -X utf8 -m tools.migrate_registry_owner_entity_ref --apply`

### validate_level_variables.py
- **功能**：载入关卡变量 Schema 并触发引擎侧的 fail-fast 校验（例如局内存档 chip 命名规则、字典默认值嵌套约束）。
- **运行**：
  - 全库（共享+全部项目存档）：`python -X utf8 -m tools.validate_level_variables`
  - 仅某个存档：`python -X utf8 -m tools.validate_level_variables --package-id <id>`

### validate_custom_variable_registry.py
- **功能**：自定义变量注册表校验（静态加载 `自定义变量注册表.py`，不执行代码）：提前定位“写回阶段会崩”的问题（例如 typed dict alias 与 default_value 类型不一致、默认值无法按 VarType 解析、第三方 owner_ref 无法在索引中找到）。
- **运行**：
  - 全部项目存档：`python -X utf8 -m tools.validate_custom_variable_registry`
  - 仅某个存档：`python -X utf8 -m tools.validate_custom_variable_registry --package-id <id>`

### claude_md_audit.py
- **功能**：扫描仓库内所有 `claude.md`，生成可勾选的巡检 TODO 清单（会合并旧清单的勾选状态）。
- **运行**：`python -X utf8 -m tools.claude_md_audit [--scope private_extensions] [--output claude_md_audit_todolist.md]`
- **可选**：`--auto-check-parse-status` 自动勾选 `private_extensions/ugc_file_tools/parse_status/*` 下“自动生成的解析状态目录”条目（避免手工逐个点选）。

### minimize_ugc_file_tools_seed_gils.py
- **功能**：将 `private_extensions/ugc_file_tools/builtin_resources/seeds/*.gil` 裁剪为“最小必需 payload_root 顶层字段集合”，减少仓库体积并降低未授权/隐私内容误入风险（不改变写回逻辑）。
- **运行**：
  - 预演（不写盘）：`python -X utf8 -m tools.minimize_ugc_file_tools_seed_gils`
  - 写回（覆盖 seeds；写前自动备份到 `tmp/artifacts/seed_gil_backups/<utc>/`）：`python -X utf8 -m tools.minimize_ugc_file_tools_seed_gils --apply`

### minimize_ugc_file_tools_ui_fixture_gils.py
- **功能**：将 `private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/*.gil` 裁剪为“最小必需 payload_root 顶层字段集合”，用于对外仓库最小化 UI 夹具体积与误入库风险。
- **运行**：
  - 预演（不写盘）：`python -X utf8 -m tools.minimize_ugc_file_tools_ui_fixture_gils`
  - 写回（覆盖文件；写前自动备份到 `tmp/artifacts/ui_fixture_gil_backups/<utc>/`）：`python -X utf8 -m tools.minimize_ugc_file_tools_ui_fixture_gils --apply`

### minimize_ugc_file_tools_asset_gias.py
- **功能**：将 `private_extensions/ugc_file_tools/builtin_resources/gia_templates/**/*.gia` 裁剪为“最小必需 root 顶层字段集合”，减少对外仓库误入库风险（保持工具链硬引用模板仍可用）。
- **运行**：
  - 预演（不写盘）：`python -X utf8 -m tools.minimize_ugc_file_tools_asset_gias`
  - 写回（覆盖文件；写前自动备份到 `tmp/artifacts/asset_gia_backups/<utc>/`）：`python -X utf8 -m tools.minimize_ugc_file_tools_asset_gias --apply`

### inspect_gil_payload_root_fields.py
- **功能**：检查 `.gil` 的 `payload_root('4')` 顶层字段集合与粗略体积（便于决定最小裁剪保留字段）。
- **运行**：`python -X utf8 -m tools.inspect_gil_payload_root_fields --input <file.gil>`

### inspect_gia_root_fields.py
- **功能**：检查 `.gia` 的 root 顶层字段集合与粗略体积（便于决定最小裁剪保留字段）。
- **运行**：`python -X utf8 -m tools.inspect_gia_root_fields --input <file.gia>`

### md_txt_inventory_audit.py
- **功能**：扫描仓库内所有非 `claude.md` 的 `.md/.txt` 文件，抽取用途摘要与内容预览，并基于根目录 `.gitignore` 做“可能被排除/可能会进仓库”的判定；输出本地待确认报告到 `docs/diagnostics/md_txt_inventory/`。
- **运行**：`python -X utf8 -m tools.md_txt_inventory_audit --repo-root <repo_root>`

### find_hardcoded_absolute_paths.py
- **功能**：扫描仓库内 `.py` 文件，找出疑似“写死的绝对路径”（Windows 盘符路径 / UNC 路径）；输出 `file:line` 位置与原始行片段，并显式列出解码失败的文件。
- **运行**：`python -X utf8 -m tools.find_hardcoded_absolute_paths [--repo-root <repo_root>]`

### validate_graphs_ci_gate.py
- **功能**：CI 用 gate：解析 `validate-graphs --all --json` 的报告，仅当存在 `error` 时退出非 0；warning 不阻断 CI（但会保留在报告中便于审计）。
- **运行**：`python -X utf8 tools/validate_graphs_ci_gate.py <report.json>`

### diagnose_equal_string_constants.py
- **功能**：诊断 Graph Code 解析后的 `GraphModel` 中，【是否相等】节点的 `input_constants` 是否被错误清空；可选执行一次 `.gil` 纯 JSON 写回并从 `.gil payload` 解析 Graph IR 复核（用于定位导出 `.gil` 后字符串常量变空的问题）。
- **运行**：
  - 仅解析检查：`python -X utf8 -m tools.diagnose_equal_string_constants --graph-code <graph_code.py> [--strict]`
  - 纯 JSON 写回复核：`python -X utf8 -m tools.diagnose_equal_string_constants --graph-code <graph_code.py> --writeback-pure-json [--base-gil <base.gil>]`
  - 模板克隆写回复核（更接近导出中心口径）：`python -X utf8 -m tools.diagnose_equal_string_constants --graph-code <graph_code.py> --writeback-template-clone --template-gil <template.gil> --template-library-dir <dir> [--template-graph-id-int <id>] [--base-gil <base.gil>]`

### cleanup_repo_root.py
- **功能**：清理仓库根目录的一次性调试产物/缓存/报告目录，将匹配到的条目归档到 `tmp/artifacts/`；并在 `docs/diagnostics/repo_root_cleanup.md` 写入归档路径与复现入口，同时在 `tmp/agent_todos/` 生成任务清单。
- **运行**：`python -X utf8 tools/cleanup_repo_root.py`

### diff_graph_ir.py
- **功能**：对比两份 Graph IR(JSON)（由 `parse_gil_payload_to_graph_ir --no-markdown` 生成），输出：
  - edges：基于 OutFlow/OutParam pins 的 connects 反推边集合，列出 missing/extra
  - pins：聚焦 `concrete_index_of_concrete_int` 差异（泛型/反射端口 concrete 收敛相关）
- **运行**：`python -X utf8 -m tools.diff_graph_ir --a <a.json> --b <b.json> [--label-a A] [--label-b B]`

### extract_gia_template_names_for_graphs.py
- **功能**：从 `.gia` 的 Root.field_1 抽取 `(resource_root_id_int -> name)` 映射；可选扫描指定节点图源码中的 10 位数字 ID，并反查出“这些 ID 在该 `.gia` 中对应的元件名清单”（用于把数字元件ID改成 `component_key:<元件名>` 占位符）。
- **补充能力**：
  - `--dump-templates`：输出 `.gia` 内全部模板条目（id/name）。
  - `--resolve-by-offset`：当节点图里的 ID 与 `.gia` 的 id 不一致时，尝试按“常见 offset”启发式反查；也可用 `--offset <N>` 显式指定 offset（可多次传入）。
- **运行**：`python -X utf8 -m tools.extract_gia_template_names_for_graphs --input-gia <file.gia> --graph-file <graph.py> [--resolve-by-offset] [--output-json out.json]`

### generate_level7_relatives_round_library.py
- **功能**：离线生成"第七关·亲戚来访"的 round library JSON（局数据预生成）。
- **核心数据结构**：
  - `RELATION_TABLE`：链式亲戚关系表 —— 每个角色（如 "堂弟"）映射到一组合法的关系链（如 `["爸爸", "兄弟", "儿子"]`），由 `chain_to_description()` 转为自然语言 "你爸爸的兄弟的儿子"。
  - `GENERATION_GROUPS`：按辈分分组的替换表（祖辈/父辈/平辈/子辈），同辈内可自由互换以生成"看似合理但错误"的关系链；跨辈不替换。同辈内的"离谱替换"（如 "兄弟" → "妻子"）有喜剧效果。
  - `_SUBSTITUTES`：预计算的逆索引（每个词 → 同辈内可替换候选）。
- **对白池（角色专属）**：
  - `dialogue.role.<role>.true`：该角色的真实台词池（10 条为宜）
  - `dialogue.role.<role>.fake`：该角色的伪人/错话台词池（5 条为宜）
  - 生成器会自动限制“每局抽取的真亲戚角色”必须在文案库中同时具备 true+fake 两个池（避免出现无台词的角色）。
- **对白生成规则**（每个来访者固定 4 句，保证不重复）：
  - **真亲戚**：
    - 首句使用 `dialogue.identity` 渲染“自报家门”（含 `{role}` + `{relation}`）
    - 第 2~4 句从 `dialogue.role.<role>.true` 抽取
  - **假亲戚**：
    - 命中 `身份异常/no_intro`：首句尝试抽取“不包含称谓（不含 role 字符串）”的句子；若池内没有可用候选，则 fallback 到 `dialogue.opener` 作为闲聊开场。
    - 命中 `关系异常`：首句仍自报家门，但 `{relation}` 会被篡改为与称谓不匹配的错误关系链描述。
    - 命中 `对话异常`：第 2~4 句改用 `dialogue.role.<role>.fake`（错话池）；否则仍用 true 池保持“更像真亲戚”。
- **妈妈纸条（关键玩法线索）**：
  - `mom_note.clues` 是“纸条真正展示的关键外观维度”（默认 2 个描述；从 `body/hair/beard/glasses/clothes/neckwear` 中抽取并优先非"无"；同时保证至少包含 1 个可被异常修改的维度：`body/hair/beard/glasses/neckwear`，以满足可解性约束）。
  - “同称谓真/伪”的外观差异仍保持轻微：异常亲戚不会改 `clothes`（衣服是跨称谓的最强区分维度）；纸条对不上会强制制造在纸条关键特征维度上（可包含 body/眼镜/领饰/头发/胡子等）；纸条可包含 `clothes` 作为辅助描述。
  - UI 侧 `note.line` 模板的 `{appearance_summary}` 来自 `mom_note.clues` 的渲染结果（关键特征摘要），而不是全量外观摘要，避免纸条过度“开卷”。
  - 妈妈纸条单条线索文本**必须 ≤10 字**；生成/导入阶段不做裁剪，超限直接报错，避免运行时做字符串切片或“生成后再裁剪”。
  - 每条 clue 的“句式/风格”完全由文案库控制：
    - `note.clue.<key>.<pos|neg>`：妈妈纸条-单条特征线索模板池
    - `pos/neg` 选择规则：`clue_value == "无"` → `neg`，否则 `pos`
    - `<key>` 取值：`body/hair/beard/glasses/clothes/neckwear`
  - `note.clue.*` 模板支持的占位符（与其它文案模板共享一套校验规则）：
    - `{role}` `{relation}`：同 `note.line`
    - `{clue_key}` `{clue_name}` `{clue_value}`：当前线索的 key/中文名/值
- **异常类型**：纸条对不上异常（外观维度不匹配）、关系异常（关系链描述错）、对话异常（错话池）、身份异常（no_intro）。
  - **设计原则**：
    - 假亲戚不一定外形对不上（可“外形对上，假在关系/对白”等），提升随机性；
    - 但一旦命中 `纸条对不上异常`，不一致必须强制制造在“其冒充称谓对应的纸条关键特征维度”上，保证玩家能用纸条对照排假。
  - 生成器会在每局生成后做硬性自检：**凡命中 `纸条对不上异常` 的异常亲戚**，都不能完全匹配其冒充称谓的纸条关键特征。
- **输出**：JSON 文件写入 `assets/资源库/项目存档/<package_id>/管理配置/第七关/亲戚round库.json`。
- **依赖文案库**：`亲戚文案库.json`（同目录），提供模板化的对白、纸条（`note.line`）等。
  - 审判结果揭晓遮罩已改为运行时由节点图写入 `UI战斗_揭晓`，round library 不再预生成等待/揭晓/放行/拒绝阶段文案。
- **运行**：`python -X utf8 -m tools.generate_level7_relatives_round_library [--rounds N] [--seed S] [--pretty]`

### import_level7_relatives_round_library_to_template.py
- **功能**：将 `亲戚round库.json` 编译后写入“第七关亲戚数据存放元件”的自定义变量默认值，并生成/覆盖对应的实体摆放条目（数据存放实体）。
- **编译策略（运行时节点图友好）**：
  - 避免在运行态节点图中解包深层 `字典`；改为多组**扁平列表**（`字符串列表/布尔值列表`）+ 指针变量。
  - 运行时按索引规则取回：每局 6 条线索、10 位来访者；对白拆为 4 条并行列表（每条长度=rounds_count*10，避免超长列表），对白文本仅保留“说话内容”，不拼接 `"{称谓}："` 前缀（由 UI/节点图决定展示样式）。
- **输出**：
  - 元件库模板：`assets/资源库/项目存档/<package_id>/元件库/第七关_亲戚数据存放元件.json`
  - 实体摆放：`assets/资源库/项目存档/<package_id>/实体摆放/第七关_亲戚数据存放实体.json`
- **运行**：`python -X utf8 -m tools.import_level7_relatives_round_library_to_template [--rounds-limit N] [--sample-seed S]`（`rounds-limit` 最大 10，默认 10）
  - 导入阶段会校验 `线索{i}文` 长度 **≤10**，不做裁剪（超限即认为源头文案不合规）。

## 注意事项
- 本目录脚本不在主程序启动路径中，需显式命令行执行。
- 关系表（`RELATION_TABLE`）是游戏玩法的核心规则源，修改后应重新生成 round library 并验证输出。
- 辈分组（`GENERATION_GROUPS`）必须覆盖关系表中出现的所有链元素；如新增链元素无辈分组对应，`corrupt_chain()` 将跳过该位置（极端情况下抛出 RuntimeError）。
- 若调整了第七关数据服务节点图对自定义变量的字段名/索引约定，需要同步更新导入脚本的输出变量名与编译规则。