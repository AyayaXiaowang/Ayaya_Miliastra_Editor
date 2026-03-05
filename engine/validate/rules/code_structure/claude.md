## 目录用途
存放“代码结构规范”（M2）相关的校验规则实现：每个模块聚焦一个主题（if 条件/事件入口/变量声明/必填入参/类型名与字面量等）。对外稳定入口为 `engine.validate.rules.code_structure_rules`（仅 re-export）。

## 当前状态
- 规则已按域拆分为多个小模块，降低单文件体积与耦合；实现仅依赖 `engine.*`，不依赖 `app/*` / `plugins/*`。
- 规则会按节点图文件推断 scope（server/client），并使用该 scope 下的节点库端口定义参与校验，避免同名节点跨作用域端口差异导致误报。
- 覆盖的核心约束包括：节点调用合法性（未知节点名/必填入参/已知节点必须显式传 `game`）、事件入口规范（`on_<事件名>` 命名与签名、`on_` 前缀方法严格校验）、变量/常量规范（Graph 变量声明、自定义变量名/目标实体、静态端口必须字面量或模块常量）、类型/ID 约束（中文类型名与转换以 `engine/type_registry.py` 为真源，数字 ID 复用 `engine.utils.id_digits.is_digits_1_to_10`，并支持 `ui_key/component/entity` 这类占位符的语法/存在性校验）。
- 变量名约束：自定义变量名（获取/设置自定义变量）与节点图变量名（GRAPH_VARIABLES / 获取/设置节点图变量）长度上限为 **20 字符**（超长直接报错）。
- 关键语义节点识别统一通过 `engine.validate.node_semantics`（语义 ID → 节点 key/alias/#scope 规约），并复用 `engine.graph.common` 的端口名常量，避免在规则内部硬编码标题字符串。

## 注意事项
- 新增规则请放入独立模块，并在 `engine.validate.rules.code_structure_rules` 的 re-export 列表中补齐，保证外部 import 路径稳定。
- 避免跨模块互相 import 形成环；共享逻辑优先抽到同目录 helper。
