## 目录用途
- `custom_variables/` 是 `ugc_file_tools` 的**自定义变量纯逻辑域**：集中维护“变量引用解析/默认值归一化/类型推断/强约束规则/值 message 构造”等能力，供 UI 导入、节点图写回、模板导出与诊断复用。
- 目标：让变量相关规则具备**单一真源**，避免散落在 `ui_patchers/` 或导出器中导致口径漂移。

## 当前状态
- 计划提供以下子模块（均为纯逻辑，不做 I/O）：
  - `constants.py`：变量组 ID / 默认组名 / unbound sentinel 等跨域共享常量（单一真源）。
  - `web_ui_constants.py`：Web UI 导入侧“默认变量绑定/默认值”常量（进度条共享变量、道具展示按钮默认变量等）。
  - `web_ui_apply.py`：Web UI 导入侧的变量补齐规则（进度条/道具展示绑定引用 → 自动创建变量）。
  - `refs.py`：变量引用文本解析（`lv/ps/p1..p8/{1:lv.xxx}/.` 等），以及“标量变量名”强约束校验。
  - `defaults.py`：`variable_defaults` 归一化（含字典字段路径收敛）。
  - `specs.py`：自定义变量 spec（group/name/VarType/默认值）推断与显式类型标注解析；类型体系以 `engine/type_registry.py` 为真源（通过 bridge 加载）。
  - `value_message.py`：`.gil/.gia` 自定义变量条目中 `item['4']` 的值 message 构造（与 NodeGraph VarBase 区分）。
  - `apply.py`：将 spec 应用到 payload 的 override variables(group1)，负责“补齐缺失、不覆盖已存在”的工程化策略：
    - 实体条目：`root4/5/1[*].7`
    - 玩家模板（战斗预设）条目：同步写入 `root4/5/1(wrapper)[*].7` 与 `root4/4/1(template)[*].8`（按可解释结构特征识别，不依赖固定路径/模板名）。

## 注意事项
- 不使用 try/except；不吞异常，fail-fast。
- 不依赖 UI；不得导入 `ui_patchers/*` 或任何 PyQt6 相关模块。
- 类型真源：规范中文类型名/别名字典解析以 `engine/type_registry.py` 为唯一事实来源（通过 `ugc_file_tools.integrations.graph_generater.type_registry_bridge` 加载，避免 `import engine` 副作用）。
- 自定义变量名（`variable_name`）需遵守引擎硬约束：长度 **<=20 字符**；本目录的强约束/override 表 key 同样应保持合规。