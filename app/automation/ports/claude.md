## 目录用途
`app/automation/ports/`：自动化执行的“端口抽象层”。在视觉识别产出的端口快照之上，提供端口分类/筛选、端口中心挑选、端口有效类型推断，以及端口类型设置（含字典/变参/向量）等步骤化能力。

## 当前状态
- **数据结构与归一化**：`port_types.py` 定义识别结果模型；`_ports.py` 负责 kind/name/side 归一化与 flow/data/settings/select/warning 等高层分类，并提供几何工具与候选筛选入口。
- **端口挑选**：`port_picker.py` 以 `_ports.filter_*` 为单一候选入口，按名称/序号/索引/几何做固定优先级回退，必要时可“移出节点遮挡→重试识别”。
- **类型推断（无 UI）**：`port_type_inference.py` 汇总推断工具（泛型/别名字典/覆盖表/边索引）；有效类型解析优先走引擎侧 `engine.graph.port_type_effective_resolver`，`port_type_resolver.py` 仅做 executor 适配与缓存。
- **类型设置（有 UI）**：`port_type_steps.py` / `port_type_setter.py` 编排“定位 Settings 行→打开类型搜索→应用类型”，并提供字典键/值设置（`dict_port_type_steps.py`）与三维向量输入编排（`vector3_*`）。
- **动态端口**：`variadic_ports.py` / `dict_ports.py` 复用 `_add_ports_common.py` 的骨架实现“解析→计算 add_count→点击 +”。

## 注意事项
- 本目录不直接做视觉识别：端口枚举来自 `app.automation.vision` 或 `NodePortsSnapshotCache`，这里仅处理其结果。
- 端口类型覆盖的唯一入口为 `GraphModel.metadata["port_type_overrides"]`：解析/标准化统一走 `port_type_context`；对外公共 API 统一从 `port_type_inference.py` 导出，禁止跨模块直导内部子模块。
- 不使用 try/except 吞错；失败应以返回值/异常让上层决定重试与回退。
