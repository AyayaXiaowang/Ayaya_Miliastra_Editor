# project_archive_importer 目录说明

## 目录用途
- 从 Graph_Generater 的“项目存档”目录读取资源（`assets/资源库/项目存档/<package_id>/` + 共享根），按“已支持的范围”写回生成新的 `.gil`（不覆盖输入文件）。
- 为 UI/CLI 的“项目存档 → 写回 `.gil`”提供可复用实现；上层编排集中在 `ugc_file_tools/pipelines/project_writeback.py`。

## 当前状态
- 大体量导入器已拆分为“薄门面 + parts 实现”，避免单文件膨胀：
  - `node_graphs_importer.py` → `node_graphs_importer_parts/`
  - `struct_definitions_importer.py` → `struct_definitions_importer_parts/`
  - 对外导入路径保持不变；外部禁止依赖 `*_parts/` 内部模块路径。

- 已覆盖的写回段（按 plan/selection 可选启用）：
  - **元件库模板**（`元件库/*.json`）：支持 `merge/overwrite`；当 base `.gil` 缺少目标 `type_code` 的模板样本时（空存档常见仅含 UI 模板），会从 seed `builtin_resources/seeds/template_instance_exemplars.gil` 获取“物件模板形态”的克隆原型（优先 `type_code=10005018`），避免“拿 UI 模板强改 type_code”导致结构不匹配；默认跳过占位模板（`metadata.ugc.placeholder=true`）。
    - base `.gil` 名称字段解码口径：从 dump-json 抽取模板名/实例名时，统一对 name 文本做归一化（支持 `"<binary_data> 0A .."` 与控制前缀误判形态），避免冲突扫描/同名判断把 `<binary_data>` 当作真实名字。
    - 写回模板后会同步补齐模板页签/索引段（`root4/6`）：将本次触及到的模板 `template_id_int` 注册到“未分类页签”的索引表（kind=400/100），避免新增模板在编辑器元件库列表中不可见/不稳定。
    - 模板 `metadata.custom_variable_file` 引用变量文件（`VARIABLE_FILE_ID`）时，会加载对应 `LEVEL_VARIABLES` 并写回模板自定义变量 group1（对齐真源：`root4/4/1[*].8(group_list).group1['11']['1']=variable_items`）。
    - 模板包含 `metadata.common_inspector.model.decorations` 时，会同步写回到 `.gil` 的装饰物段 `payload_root['27']`（root27）：
      - `root27.1`：装饰物定义（meta 40/50/502 = parent_template_id）
      - `root27.2`：装饰物挂载（meta 40/50/502 = parent_instance_id；field12.1 引用 `root27.1` 的 def_id）
      - 挂载的父实例 ID 会从 base `.gil` 的 root5/root8 中按 template_id 反查；若 base 内不存在父实例，会为“带 decorations 的模板”自举一个 root8 父实例（从 seed `builtin_resources/seeds/template_instance_exemplars.gil` 克隆同 type_code 的 exemplar），以便生成 `root27.2` 并在编辑器内可见。
        - 自举时优先令 `instance_id == template_id_int`（对齐“元件挂装饰物”真源样例）；若发生 ID 冲突则回退到稳定的 `0x4040xxxx` 段位 ID（low16<0x8000）。
        - 自举父实例时会同步写入 **preview transform 坐标**：root8 父实例（section6.id=1.transform.pos）与模板 entry（section7.id=1.transform.pos）保持一致；默认按真源样例的 anchor+step 做稳定分配，避免新增模板“都在原点/重叠/不可见”。
      - 同步补齐父实例引用：对写入/触及的父实例，在 meta(id=40).field50 写入 message `{501: <attachment_id 的 varint stream>}`（packed varint），确保挂载关系完整。
      - 同步补齐模板引用：对写入/触及的模板 entry（`root4/4/1`），在 meta(id=40).field50 写入 message `{501: <def_id 的 varint stream>}`（packed varint），对齐真源样例的“模板持有 definitions 引用表”。
      - 当写回模板 decorations 时会补齐 `payload_root['22']`（root22）声明：将 `ModelDisplay/PropertyAttachArchetypeModel` 等加入到 root22.1，并同步扩展 root22.2 的 `01` 掩码，避免编辑器侧缺失声明导致“不渲染/不可见”。
      - attachment_id 分配会避开 `.gil` 内其它段已经占用的 `0x400000xx`（例如 UI/布局索引等），减少跨段冲突风险。
      - 若本次写回确实触及到模板/装饰物（含 root8 父实例自举与 root6 页签索引补丁），会同步刷新 `payload_root['40']`（时间戳），避免官方侧潜在的缓存/刷新不一致导致“写入了但不可见”。
  - **实体摆放**（`实体摆放/*.json`）：支持 `merge/overwrite`；当所选 `instance_id` 在 base `.gil` 中不存在时，会按“克隆样本 entry 并替换关键字段”的策略新增写回（用于导出到空存档/增量补齐）。
    - base `.gil` 名称字段解码口径：同模板段；同名冲突识别以“归一化后的可读名称”为准。
    - `instance_id/template_id` 支持 **非数字**：写回 `.gil` 时会按 `.gia` 导出同口径映射到稳定的 `0x4040xxxx`（low16<0x8000）ID；新增时若发生哈希冲突会做 low16 bump。
    - 新增实例会优先按 `template_id` / `template_type_code(entry['8'])` 选择可克隆样本；若 base `.gil` 无可用样本，会回退到 `ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil` 的 seed exemplar（避免随意克隆导致“进游戏不可见”）。
    - 新增路径不强制要求提供 `metadata.ugc_guid_int`：若缺失则会从目标存档扫描已有实体 GUID，并按 **max+1** 顺序分配一个不冲突 GUID；如提供了 `metadata.guid` 也会作为 GUID 来源（用于保持与真源/既有引用一致）。
    - 当本次写回同时涉及“模板装饰物(root27) + 新增实例(root5/1)”时，实例写回阶段会基于已写入的 `root27.1(definitions)` 自动补齐 `root27.2(attachments)` 挂载（确保 decorations 能绑定到本次新增的 parent instance）。
    - 实体 `metadata.custom_variable_file` 引用变量文件（`VARIABLE_FILE_ID`）时，会加载对应 `LEVEL_VARIABLES` 并写回实例自定义变量 group1（对齐真源：`root4/5/1[*].7(group_list).group1['11']['1']=variable_items`）；跳过 `is_level_entity=true`（关卡实体变量仍由“关卡实体自定义变量”阶段单独管理）。
    - shape-editor 空画布载体（`template_id=shape_editor_empty__*`）：允许在未导出模板段的情况下新增到空存档；写回时按 builtin `template_type_code=10005018` 的真源形态写入 `entry['2']`/`entry['8']`。
      - 新增 `template_type_code=10005018` 的实例时会强制使用 canonical “空模型实体” exemplar（而不是从 seed/base 里随机挑同 type 的样本），并保证无 decorations 时 parent meta(id=40).field50 为 empty bytes（避免“新增实体自带特效/挂载引用”）。
      - 若实体摆放 JSON 存在 decorations（`metadata.common_inspector.model.decorations` 或 `metadata.shape_editor.canvas_payload.common_inspector.model.decorations`），则会将其写回到 `root27` 并**只挂载到该 parent_instance_id**（用于像素画/装饰物载体在游戏内可见）。
      - instance-level decorations 写回采用 **root5-style** 的 `root27.2` 挂载（对齐观测样本 `tmp_shape_editor_instance_decorations.gil`）：
        - root27 仅写 `2(attachments)`（不会新增 `1(definitions)`）
        - attachment entry 的 `field12` 固定写 empty bytes（`"<binary_data> "`），不写 `{1: def_id}` 引用
        - transform：`pos` 写 vec3 dict（省略 0 值字段）；`rot` 写 `<binary_data> ...`（零旋转为 empty bytes）；`scale` 写完整 vec3 dict（x/y/z 必须显式）
        - 写回时会先移除该 parent_instance_id 的旧挂载，再整批重建（并按 id 升序复用旧 id 以保持稳定）
        - 同步补齐父实例引用：在 parent instance（`root4/5/1`）的 meta(id=40).field50 写入 message `{501: <attachment_id 的 varint stream>}`，对齐真源样本中“无装饰物为 empty bytes / 有装饰物为 message”的形态。
  - **信号定义**（`管理配置/信号/**/*.py`）：写回 signal entries 与信号相关 node_defs；信号参数类型禁止字典（含别名字典）；支持按 `SIGNAL_ID` 过滤。
    - 空/极简 base + 0x6000/0x6080 口径下，默认**不写入**“占位无参信号”entry（仍会预留其 node_def_id/端口块以避免业务信号误占保留槽）；如需对齐旧样本可在 pipeline/CLI 显式开启写入。
  - **结构体定义**：
    - 优先：`管理配置/结构体定义/原始解析/struct_def_*.decoded.json`
    - 补充/回退：`管理配置/结构体定义/基础结构体/**/*.py` 与 `管理配置/结构体定义/局内存档结构体/*.py`（支持按 `STRUCT_ID` 过滤）
  - **节点图**（`节点图/**.py` Graph Code）：GraphCode → GraphModel(JSON) → 写回 `.gil` 节点图段；依赖模板样本库覆盖（覆盖不足会 fail-fast）；支持 `ui_key:`/`entity_key:`/`component_key:` 回填；中间 GraphModel 与摘要输出到 `ugc_file_tools/out/`。
  - **界面 UI**：
    - 优先：`管理配置/UI源码/__workbench_out__/*.ui_bundle.json`（Workbench bundle）
    - 次选：`管理配置/UI控件模板/原始解析/*.raw.json`（raw_template）
    - 空/极简 base 会 bootstrap 最小 UI 段后再写回；同名布局冲突支持 `overwrite/add/skip`。
    - 导出中心链路（项目存档→写回 `.gil`）当前默认不接入“固有控件（HUD）初始显隐覆盖”，避免 base `.gil` 的布局内缺少固有控件时 fail-fast 阻断整次导出（report 会标记 skipped）。
  - **注册表自定义变量**（可选）：按 `selected_custom_variable_refs`（owner_ref+variable_id）补齐写入输出 `.gil` 的 override_variables(group1)。
    - 声明真源：项目存档 `管理配置/关卡变量/自定义变量注册表.py`（AutoCustomVariableDeclaration，AST 静态提取，不执行代码）。
    - 语义：仅补齐缺失；同名但类型不同默认不覆盖（报告列出）；可覆盖时需显式开启 overwrite（默认关闭）。
    - owner 覆盖范围：关卡实体(level)、玩家(player)、以及第三方 owner（优先按 owner_display 匹配实体/模板 name 写回）。

- 统一入口：`python -X utf8 -m ugc_file_tools project import --dangerous ...`（以及 `import-ingame-save-structs` 等子命令）。

## 注意事项
- 输出 `.gil` 统一写入 `ugc_file_tools/out/`（不覆盖输入）；路径计算统一使用 `ugc_file_tools.repo_paths`。
- dump-json 口径兼容：DLL dump 与纯 Python dump 在“单值字段是否用 list 表达”等细节上可能不同，实现需兼容。
- fail-fast：不使用 `try/except`；结构/模板不符合预期直接抛错。
- 对外复用只走公开 API（无下划线），避免上层导入 `*_parts/` 内部模块导致边界坍塌。
- VarType/type_id 单一真源：结构体字段类型表以 `ugc_file_tools.struct_type_id_registry` 为准（如存在 genshin-ts 对照报告，可在运行前做一致性校验）。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

