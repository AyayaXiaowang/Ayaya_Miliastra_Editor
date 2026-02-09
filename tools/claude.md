# tools/ 目录

## 目录用途
离线数据生成与构建辅助脚本，不随主程序启动，需单独执行。

## 当前文件

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
  - **真亲戚**：从 `dialogue.role.<role>.true` 抽取 4 句。
  - **假亲戚**：
    - 命中 `身份异常`（`identity_first_line_mode=no_intro`）：首句会尝试抽取“不包含称谓（不含 role 字符串）”的句子；若池内没有可用候选，则 fallback 到 `dialogue.opener` 作为闲聊开场。
    - 命中 `对话异常`：第 2~4 句改用 `dialogue.role.<role>.fake`（错话池）；否则仍用 true 池保持“更像真亲戚”。
- **妈妈纸条（关键玩法线索）**：
  - `mom_note.clues` 是“纸条真正展示的关键外观维度”（固定包含 body，额外再抽 2 个维度）。
  - 为保证“不同称谓外形明显不同”，每局 6 个真亲戚会分配不同的 `clothes`；纸条线索默认不包含 `clothes`，避免伪人为了对不上纸条而换衣服导致跨称谓外形重叠。
  - UI 侧 `note.line` 模板的 `{appearance_summary}` 来自 `mom_note.clues` 的渲染结果（关键特征摘要），而不是全量外观摘要，避免纸条过度“开卷”。
  - 每条 clue 的“句式/风格”完全由文案库控制：
    - `note.clue.<key>.<pos|neg>`：妈妈纸条-单条特征线索模板池
    - `pos/neg` 选择规则：`clue_value == "无"` → `neg`，否则 `pos`
    - `<key>` 取值：`body/hair/beard/glasses/neckwear`
  - `note.clue.*` 模板支持的占位符（与其它文案模板共享一套校验规则）：
    - `{role}` `{relation}`：同 `note.line`
    - `{clue_key}` `{clue_name}` `{clue_value}`：当前线索的 key/中文名/值
- **异常类型**：对话异常（错话池）、身份异常（no_intro）、纸条对不上异常（外观维度不匹配）。
  - **可解性约束（重要）**：每个异常亲戚都会包含 `纸条对不上异常`，并且该不一致会被强制制造在“其冒充称谓对应的纸条关键特征维度”上，保证玩家可用纸条对照排假。
  - 生成器会在每局生成后做硬性自检：任何异常亲戚都不能完全匹配其冒充称谓的纸条关键特征。
- **输出**：JSON 文件写入 `assets/资源库/项目存档/<package_id>/管理配置/第七关/亲戚round库.json`。
- **依赖文案库**：`亲戚文案库.json`（同目录），提供模板化的对白、纸条（`note.line`）等。
  - 审判结果揭晓遮罩已改为运行时由节点图写入 `UI战斗_揭晓`，round library 不再预生成等待/揭晓/放行/拒绝阶段文案。
- **运行**：`python -X utf8 -m tools.generate_level7_relatives_round_library [--rounds N] [--seed S] [--pretty]`

### import_level7_relatives_round_library_to_template.py
- **功能**：将 `亲戚round库.json` 编译后写入“第七关亲戚数据存放元件”的自定义变量默认值，并生成/覆盖对应的实体摆放条目（数据存放实体）。
- **编译策略（运行时节点图友好）**：
  - 避免在运行态节点图中解包深层 `字典`；改为多组**扁平列表**（`字符串列表/布尔值列表`）+ 指针变量。
  - 运行时按索引规则取回：每局 6 条线索、10 位来访者；对白拆为 4 条并行列表（每条长度=rounds_count*10，避免超长列表），每条自动拼上 `"{称谓}："` 前缀。
- **输出**：
  - 元件库模板：`assets/资源库/项目存档/<package_id>/元件库/第七关_亲戚数据存放元件.json`
  - 实体摆放：`assets/资源库/项目存档/<package_id>/实体摆放/第七关_亲戚数据存放实体.json`
- **运行**：`python -X utf8 -m tools.import_level7_relatives_round_library_to_template [--rounds-limit N] [--sample-seed S]`（`rounds-limit` 最大 10，默认 10）

## 注意事项
- 本目录脚本不在主程序启动路径中，需显式命令行执行。
- 关系表（`RELATION_TABLE`）是游戏玩法的核心规则源，修改后应重新生成 round library 并验证输出。
- 辈分组（`GENERATION_GROUPS`）必须覆盖关系表中出现的所有链元素；如新增链元素无辈分组对应，`corrupt_chain()` 将跳过该位置（极端情况下抛出 RuntimeError）。
- 若调整了第七关数据服务节点图对自定义变量的字段名/索引约定，需要同步更新导入脚本的输出变量名与编译规则。