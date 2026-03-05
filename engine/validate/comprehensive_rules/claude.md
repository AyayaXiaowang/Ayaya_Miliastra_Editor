## 目录用途
项目存档级综合校验规则（Comprehensive Rules）实现集合：运行于 `ComprehensiveValidator` / `ValidationPipeline`，检查包级与资源级一致性（实体、模板/摆放、管理配置、结构体/信号、GUID/资源 ID、挂载节点图等）。

## 当前状态
- 规则通过 `__init__.py` 的 `build_rules(validator)` 统一注册并顺序执行。
- 信号相关入口为 `signal_rule.py`（实现拆分在 `signal/` 子包）；结构体相关规则集中在 `struct_rule.py` / `struct_definition_rule.py`。
- 资源系统相关规则覆盖 GUID 唯一性与格式、代码级资源 ID 唯一性、关卡变量引用与使用一致性等（见 `guid_rule.py`、`resource_id_uniqueness_rule.py`、`level_variable_reference_rule.py`、`graph_level_variable_usage_rule.py`）。
- 节点图挂载校验（`package_graph_mount_rule.py`）默认仅关注“被挂载引用的节点图是否在共享/当前存档目录且可解析”；存档内存在但未挂载的节点图不再产出告警（避免模板/测试图刷屏）。
- 自定义变量命名约束：管理配置关卡变量（`management.level_variables[*].variable_name`）与自定义变量注册表声明（`自定义变量注册表.py`）强制长度上限 **20 字符**（超长为 error）。
- 规则中如需读取“声明型代码资源”（例如 `自定义变量注册表.py`），应使用 AST 静态提取（`engine.resources.auto_custom_variable_registry`），避免 import 执行顶层代码与副作用。
- 自定义变量注册表的 `owner` 直接填实体/元件 ID 或 `player`/`level` 关键字（支持列表形式多 owner）；综合校验根据 owner 值在实体摆放/元件库中查找并校验变量文件引用一致性。

## 注意事项
- 本目录规则仅依赖 `engine.*`，禁止反向依赖 `app/*`、`plugins/*`、`assets/*`，也不要依赖任何未纳入仓库的本地脚本/工具链。
- Rule 的定位/修复建议应指向公开校验入口（`app.cli.graph_tools`），避免引用已移除的历史入口。
- 新规则尽量聚焦“图外/包级”问题，避免与源码级校验重复；不做静默兼容，遇到异常结构应直接抛错或产出明确 issue。

