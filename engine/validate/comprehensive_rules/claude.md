## 目录用途
- 存放存档级综合校验规则（Comprehensive Rules），包括关卡实体、模板/实体摆放挂载关系、管理配置、信号系统、结构体系统、资源库节点图等高层规则。
- 这些规则基于 `ComprehensiveValidator` 与 `ValidationPipeline` 运行，聚焦“包级/资源级一致性”，不处理节点图源码的语法与代码风格。
- 信号系统相关规则对外稳定入口为 `signal_rule.py`，其实现已拆分到 `signal/` 子包；结构体系统相关规则集中在 `struct_rule.py` 中，检查结构体节点绑定的结构体 ID 与字段名是否与当前结构体定义保持一致。
- 定义本身校验：
  - `signal_definition_rule.py`：信号定义文件的 payload 结构与参数类型合法性（不依赖节点图是否使用；**严禁字典类型信号参数**）。
  - `struct_definition_rule.py`：结构体定义文件的 payload 结构与 ID 类型默认值合法性（不依赖节点图是否使用），并额外校验“目录即分类”：
    - `管理配置/结构体定义/基础结构体/**.py` 必须为 `basic`
    - `管理配置/结构体定义/局内存档结构体/**.py` 必须为 `ingame_save`
    - 同时要求文件内 `STRUCT_TYPE` 常量与 `STRUCT_PAYLOAD.struct_type/struct_ype` 一致并与目录期望对齐（避免 UI 分类漂移与工具链歧义）。

## 当前状态
- 已实现的规则涵盖信号使用一致性（存在性、参数列表、常量类型与连线类型）、结构体节点绑定与字段一致性、关卡实体/模板/实体摆放挂载约束、管理配置完整性、资源库节点图元数据检查（不做节点图源码/图结构严格解析）以及复合节点结构检查等。
- 新增“资源系统”规则：
  - `guid_rule.py`：包内 GUID 唯一性、metadata.guid 格式（**1~10 位纯数字**）与缺失资源定位（禁止静默取第一条）。
  - `resource_id_uniqueness_rule.py`：项目存档目录内“代码级资源”的资源 ID 唯一性检查（重复 ID / 缺失 ID 常量），避免索引歧义导致的启动失败或运行期串用。
  - `level_variable_reference_rule.py`：存档索引中关卡变量引用（`VARIABLE_FILE_ID`）的存在性校验（严格：不再接受直接写 `variable_id`）。
  - `graph_level_variable_usage_rule.py`：挂载节点图中【自定义变量】相关节点的 `变量名`：
    - 若为常量，则必须为可解析的稳定 `variable_name`（严格模式下禁止填写 `variable_id`/旧展示文本）。
    - 若来自连线且无法静态解析，则跳过“引用存在性”强校验（降级为 warning）。
- 特殊视图约定：综合校验只将 `global_view` 视为聚合视图；不存在 `unclassified_view` 的编辑器入口（旧值残留时由上层回退到 `global_view` 或具体存档）。
- 规则通过 `build_rules(validator)` 统一注册，运行时会从 `validator` 上获取 `package`、`resource_manager`、`node_library` 等上下文信息。
- `management_rule.py` 除关卡变量等管理配置一致性外，也可用于对“代码级管理资源”做包级约束检查：例如结构体定义的命名长度（struct_name 最长 30，中文算2）等，产出的 issue 会携带 `management_section_key/management_item_id` 以支持 UI 一键跳转到对应管理条目。
- UI 工作流已收敛为“HTML 为真源、派生物入运行时缓存”；综合校验不再维护 `UI页面`（UIPage）一类“入口资源”的引用闭合规则。
- 规则中涉及“端口名/节点标题”的定位应优先复用 `engine.graph.common` 的集中常量（例如 `TARGET_ENTITY_PORT_NAME`、信号/结构体端口常量）；涉及语义节点识别时优先消费节点库 `NodeDef.semantic_id`（或通过 `engine.validate.node_semantics` 统一解析），避免散落硬编码导致漂移。
 - 复合节点校验聚焦“子图存在性、虚拟引脚映射引用有效性、以及虚拟输入端口冲突（被映射为虚拟输入后不应再被子图内部连线驱动）”；虚拟输出映射允许端口在子图内部继续被复用，以兼容“计算结果既参与内部逻辑又对外输出/流程出口锚定到分支节点”等常见写法。

## 注意事项
- 本目录中的规则只能依赖引擎层模块（`engine.*`），禁止反向依赖应用层或插件层（`app.*` / `plugins.*` / `assets.*`），也禁止依赖任何未纳入仓库的内部工具链/本地脚本。
- 规则的“定位/修复建议”文本应指向 `app.cli.graph_tools`（或 release 的 `Ayaya_Miliastra_Editor_Tools.exe`），避免引用已移除的 tools 目录入口。
- 新规则应尽量聚焦“图外/包级”问题，避免与 `engine.validate.api.validate_files` 中的 M2/M3 源码规则重复。
- 在设计类型相关规则时，需遵守端口类型系统约定：基础类型、列表类型与“泛型家族”（如“泛型”“泛型列表”“泛型字典”）需要在规则中保持一致的判定逻辑，以避免产生误报。

## 目录用途
- 拆分自 `ComprehensiveValidator` 的项目存档级规则实现集合。
- 每个文件聚焦单一领域（关卡实体、模板、实体摆放、UI、复合节点等），提供 `BaseComprehensiveRule` 子类与协作函数。
- 通过 `build_rules()` 返回规则列表供 `ValidationPipeline` 顺序执行。

## 当前状态
- 规则逻辑按领域拆散，便于理解与维护；共用 `validator` 注入的上下文（package、resource_manager、graph 校验入口）。
- Graph 结构与端口检查由 `engine/validate/comprehensive_graph_checks.py` 统一提供，rule 代码只负责装配与业务判断；共享快照缓存通过 `helpers.get_graph_snapshot` 暴露，避免在多个规则中重复标准化节点/连线。
- `BaseComprehensiveRule` 统一在 `apply()` 中注入新增问题，子类仅需实现 `run(ctx)` 并返回 `ValidationIssue` 列表；若 `run()` 内部调用 `validator.validate_graph_*`，可以直接合并其返回的增量问题。
- `helpers.py` 提供模板/实体摆放/关卡实体/玩家模板（战斗预设-玩家模板）的节点图迭代器、组件兼容性与 EngineIssue→ValidationIssue 的转换工具；并在遍历时避免对“关卡实体”重复产出同一组节点图（实例集合中会排除关卡实体 instance_id），减少综合规则的重复扫描与重复报错风险。
- `helpers.convert_engine_issues_to_validation(...)` 会尽量保留 `code/file/graph_id/node_id/line_span` 等字段，并将规则侧的 `detail` 合并进 UI 侧的 detail，保证错误码与定位信息在上层展示/跳转时不丢失。
- 部分规则会结合包级视图与资源库目录扫描结果，检查存档与模板/实体摆放/节点图之间的资源归属和引用闭合情况，例如关卡实体是否存在、实体摆放引用的模板是否有效，以及存档目录下的节点图是否存在“未挂载/跨目录引用”等问题。

## 注意事项
- 规则实现禁止互相引用 UI 层；仅依赖 `engine.*` 内部模块。
- 若新增规则，请创建独立模块，继承 `BaseComprehensiveRule` 并在 `__init__.py` 的 `build_rules()` 中注册顺序。
- 规则应返回 `ValidationIssue` 列表，不记录历史，只描述当前目录用途与约束。
- 需要执行图校验时统一通过 `ComprehensiveValidator` 的公开接口（如 `validate_graph_cache_data`）触发，避免直接访问私有下划线方法。

